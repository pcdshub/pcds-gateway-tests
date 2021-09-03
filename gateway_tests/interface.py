"""
Classes for understanding PCDS gateway interfaces.
"""
import dataclasses
import functools
import pathlib
import re
import socket

IP_VARIABLE = re.compile(r"^export\s+([^= ]*)\s*=\s*(\d+\.\d+\.\d+\.\d+).*$")
INTERFACE = re.compile(r"(.*)_IF(\d\d)")
BROADCAST = re.compile(r"(.*)_BC")
IGNORE_SUBNETS = ['mcc', 'mcc1', 'mcc2']


@dataclasses.dataclass
class SubnetInfo:
    name: str
    mask: str
    bcaddr: str

    def contains_ip(self, ipaddr: str) -> bool:
        """
        True if the given IP is on this subnet.
        """
        return self.bcaddr == get_bcaddr(ipaddr, self.mask)


@dataclasses.dataclass
class InterfaceInfo:
    name: str
    ipaddr: str
    subnet: SubnetInfo

    def can_ping(self, ipaddr: str) -> bool:
        """
        True if this interface should be able to ping the ipaddr.
        """
        return self.subnet.contains_ip(ipaddr)


class InterfaceConfig:
    hosts: dict[str, dict[str, InterfaceInfo]]
    subnets: dict[str, SubnetInfo]

    def __init__(self, epicscagp):
        self._epicscagp = pathlib.Path(epicscagp)
        self.reread_epicscagp()

    def reread_epicscagp(self):
        self.hosts = {}
        self.subnets = {}

        with self._epicscagp.open('r') as fd:
            lines = [line.strip() for line in fd.read().splitlines()]

        # setup the subnet definitions first
        for line in lines:
            match = IP_VARIABLE.match(line)
            if match:
                var, bcaddr = match.groups()
                match = BROADCAST.match(var)
                if match:
                    subnet, = match.groups()
                    subnet = subnet.lower()
                    if subnet not in IGNORE_SUBNETS:
                        self.subnets[subnet] = SubnetInfo(
                            name=subnet,
                            mask='',
                            bcaddr=bcaddr,
                            )

        # now set up the host interface definitions
        for line in lines:
            match = IP_VARIABLE.match(line)
            if match:
                var, ipaddr = match.groups()
                match = INTERFACE.match(var)
                if match:
                    subnet, ifnum = match.groups()
                    subnet = subnet.lower()
                    if subnet not in IGNORE_SUBNETS:
                        host = f'pscag{ifnum}'
                        try:
                            host_info = self.hosts[host]
                        except KeyError:
                            host_info = {}
                            self.hosts[host] = host_info
                        host_info[subnet] = InterfaceInfo(
                            name=subnet,
                            ipaddr=ipaddr,
                            subnet=self.subnets[subnet],
                            )

        # backfill the subnet masks
        for host_info in self.hosts.values():
            for if_info in host_info.values():
                if not if_info.subnet.mask:
                    if_info.subnet.mask = get_mask(
                        if_info.ipaddr,
                        if_info.subnet.bcaddr,
                        )

        # remove subnets with no associated gateway interfaces
        for name, info in list(self.subnets.items()):
            if not info.mask:
                del self.subnets[name]

    @functools.lru_cache(maxsize=1000)
    def subnet_from_ip(self, ipaddr: str) -> str:
        for name, info in self.subnets.items():
            if info.contains_ip(ipaddr):
                return name
        raise ValueError(f'Recieved non-pcds ip address {ipaddr}')

    @functools.lru_cache(maxsize=1000)
    def subnet_from_hostname(self, hostname: str) -> str:
        ipaddr = socket.gethostbyname(hostname)
        return self.subnet_from_ip(ipaddr)


def get_mask(ipaddr: str, bcaddr: str) -> str:
    guesses = ['255.255.252.0', '255.255.255.0']
    for guessaddr in guesses:
        if get_bcaddr(ipaddr, guessaddr) == bcaddr:
            return guessaddr
    raise ValueError(
        'Could not find a valid netmask for '
        f'ip={ipaddr}, bc={bcaddr}')


def get_bcaddr(ipaddr: str, mask: str) -> str:
    ipint = ip_to_int(ipaddr)
    maskint = ip_to_int(mask)
    bcint = ipint | ~ maskint
    bcaddr = ip_to_str(bcint)
    return bcaddr


def ip_to_str(ipaddr: int) -> str:
    octets = []
    for _ in range(4):
        octets.append(str(ipaddr & 255))
        ipaddr = ipaddr >> 8
    return '.'.join(reversed(octets))


def ip_to_int(ipaddr: str) -> int:
    retval = 0
    for octet in ipaddr.split('.'):
        retval = retval << 8
        retval += int(octet)
    return retval
