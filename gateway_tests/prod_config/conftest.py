# Goals:
# Go through a bunch of real PVs
# Get them from the IOC and through the gateway
# Figure out exactly what the gateway should have said
# Take several samples
import dataclasses
import enum
import os.path

from ..compare import PCDSConfiguration
from ..util import PVInfo


class AccessBehavior(enum.IntEnum):
    DISCONNECTED = 0
    READ = 1
    WRITE = 2


def promote_access(current, new):
    if new > current:
        return new
    else:
        return current


def demote_access(current, new):
    if new < current:
        return new
    else:
        return current


def correct_gateway_pvinfo(config: PCDSConfiguration, pvinfo: PVInfo,
                           hostname: str) -> PVInfo:
    """
    Determine what the gateway should have given based on what the IOC gave us.

    This should be mostly the same, but potentially with a modified access field
    or possibly disconnected.

    Parameters
    ----------
    config : PCDSConfiguration
        All of the configuration info about the deployed env.
    pvinfo : PVInfo
        The pv info retrieved from the IOC.
    hostname : str
        The host we are testing on (or spoofing for)

    Returns
    -------
    gwinfo : PVInfo
        The pv info we should see from the gateway if all is well. Note that this
        will not fill in the pvinfo address field for the gateway.
    """
    # If we timed out, the gateway should also time out
    if pvinfo.error == 'timeout':
        return pvinfo

    # Otherwise, we need to determine which access rules apply.
    # First, we need to know which subnet the PV is on.
    subnet = get_pcds_subnet(pvinfo.address[0])

    # With the subnet, we can determine which gateway rules are relevant.
    # Only the lowest down in each pvlist file is relevant.
    filenames = set()
    deny_matches = {}
    allow_matches = {}
    for match in config.gateway_config.get_matches(pvinfo.name).matches:
        if not os.path.basename(match.filename).startswith(subnet):
            continue
        filenames.add(match.filename)
        if match.command == 'DENY':
            deny_matches[match.filename] = match
        elif match.command.contains('ALLOW'):
            allow_matches[match.filename] = match
        elif match.command.contains('DENY FROM'):
            if match.command == f'DENY FROM {hostname}':
                # Short-circuit everything else
                # This sends out a NO_ACCESS event, rather than disconnected
                # Do not need to consider anything else
                return PVInfo(
                    name=pvinfo.name,
                    access="NO_ACCESS",
                )
        else:
            raise NotImplementedError(
                'Programmer did not know that match.command could be '
                f'{match.command}'
                )

    # Next we see what each relevant file says about our PV
    gateway_access_summary = {}
    for filename in filenames:
        deny = deny_matches.get(filename, None)
        allow = allow_matches.get(filename, None)

        if deny is not None:
            # DENY makes it look disconnected
            gateway_access_summary[filename] = AccessBehavior.DISCONNECTED
        elif allow is not None:
            # Now we need to evaluate the access rule for our host
            if allow.access is None:
                # Default behavior
                gateway_access_summary[filename] = AccessBehavior.READ
            else:
                # Look it up if not default
                access_group = config.access_security.groups[allow.access.group]

                behavior = AccessBehavior.DISCONNECTED
                for rule in access_group.rules:
                    if rule.hosts is None:
                        behavior = promote_access(behavior, AccessBehavior(rule.options))
                    else:
                        hosts = set()
                        for host_group in rule.hosts:
                            hosts.update(config.access_security.hosts[host_group].hosts)
                        if hostname in hosts:
                            behavior = promote_access(behavior, AccessBehavior(rule.options))
                gateway_access_summary[filename] = behavior

    # Now we know how each gateway should respond to our PV. So what should we see?
    # Well, ideally we have exactly one or zero READ or WRITE, and the rest disconnected.
    # If we have two READ, two WRITE, one READ and one WRITE, etc. that is an error.
    # Otherwise just contstruct with the non-ambiguous item.
    gw_behavior = [(fn, bh) for (fn, bh) in gateway_access_summary.items()
                   if bh != AccessBehavior.DISCONNECTED]

    if len(gw_behavior == 0):
        return PVInfo(
            name=pvinfo.name,
            error='timeout',
        )
    elif len(gw_behavior == 1):
        # Demote our original access level if needed
        new_access = demote_access(AccessBehavior(pvinfo.access), gw_behavior[0][1])
        # Omit the gateway address- not in scope here
        return PVInfo(
            name=pvinfo.name,
            access=new_access.name,
            data_type=pvinfo.data_type,
            data_count=pvinfo.data_count,
            value=pvinfo.value,
            error=pvinfo.error,
            time_md=pvinfo.time_md,
            control_md=pvinfo.control_md,
        )
    else:
        raise RuntimeError(f'Gateway configs are inconsistent: {gw_behavior}')


@dataclasses.dataclass
class InterfaceInfo:
    name: str
    ipaddr: str
    mask: str

    def can_ping(self, ipaddr: str) -> bool:
        """
        True if this interface should be able to ping the ipaddr
        """
        def split_ints(octets):
            return (int(num) for num in octets.split('.'))
        my_ip = split_ints(self.ipaddr)
        full_mask = split_ints(self.mask)
        your_ip = split_ints(ipaddr)
        for mine, mask, yours in zip(my_ip, full_mask, your_ip):
            if mine & mask != yours & mask:
                return False
        return True


PSCAG01_IFS = [
    InterfaceInfo(
        name='cxi',
        ipaddr='172.21.68.10',
        mask='255.255.252.0',
        ),
    InterfaceInfo(
        name='det',
        ipaddr='172.21.58.10',
        mask='255.255.255.0',
    ),
    InterfaceInfo(
        name='dev',
        ipaddr='134.79.165.10',
        mask='255.255.255.0',
    ),
    InterfaceInfo(
        name='drp',
        ipaddr='172.21.156.10',
        mask='255.255.252.0',
    ),
    InterfaceInfo(
        name='kfe',
        ipaddr='172.21.92.10',
        mask='255.255.252.0',
    ),
    InterfaceInfo(
        name='las',
        ipaddr='172.21.160.10',
        mask='255.255.252.0',
    ),
    InterfaceInfo(
        name='lfe',
        ipaddr='172.21.88.10',
        mask='255.255.252.0',
    ),
    InterfaceInfo(
        name='mcc',
        ipaddr='172.21.40.10',
        mask='255.255.255.192',
    ),
    InterfaceInfo(
        name='mec',
        ipaddr='172.21.76.10',
        mask='255.255.255.192',
    ),
    InterfaceInfo(
        name='mfx',
        ipaddr='172.21.72.10',
        mask='255.255.252.0',
    ),
    InterfaceInfo(
        name='rix',
        ipaddr='172.21.140.10',
        mask='255.255.252.0',
    ),
    InterfaceInfo(
        name='srv',
        ipaddr='172.21.32.154',
        mask='255.255.255.0',
    ),
    InterfaceInfo(
        name='tmo',
        ipaddr='172.21.132.10',
        mask='255.255.252.0',
    ),
    InterfaceInfo(
        name='tst',
        ipaddr='172.21.148.10',
        mask='255.255.252.0',
    ),
    InterfaceInfo(
        name='xcs',
        ipaddr='172.21.80.10',
        mask='255.255.252.0',
    ),
    InterfaceInfo(
        name='xpp',
        ipaddr='172.21.84.10',
        mask='255.255.252.0',
    ),
    InterfaceInfo(
        name='ued',
        ipaddr='172.21.36.10',
        mask='255.255.252.0',
    ),
]


def get_pcds_subnet(ipaddr: str) -> str:
    """
    Return the name of the pcds subnet based on the ip address.

    Parameters
    ----------
    ipaddr : str
        IP address as a string, e.g. '127.0.0.1'

    Returns
    -------
    subnet : str
        Subnet name as a string, e.g. 'lfe'
    """
    for if_info in PSCAG01_IFS:
        if if_info.can_ping(ipaddr):
            return if_info.name
    raise ValueError(f'Recieved non-pcds ip address {ipaddr}.')
