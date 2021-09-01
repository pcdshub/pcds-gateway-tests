import contextlib
import dataclasses
import enum
import getpass
import logging
import os.path
import socket
from typing import Any, Optional

import caproto
import caproto.sync.client as ca_client
import numpy as np

from .compare import PCDSConfiguration

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PVInfo:
    name: str
    access: Optional[str] = None
    data_type: Optional[str] = None
    data_count: Optional[int] = None
    value: Optional[list[Any]] = None
    error: Optional[str] = None
    time_md: Optional[dict[str, Any]] = None
    control_md: Optional[dict[str, Any]] = None
    address: Optional[tuple[str, int]] = None


@contextlib.contextmanager
def bound_udp_socket(
    reusable_socket: Optional[socket.socket] = None,
    timeout: float = ca_client.common.GLOBAL_DEFAULT_TIMEOUT,
):
    """Create a bound UDP socket, optionally reusing the passed-in one."""
    if reusable_socket is not None:
        reusable_socket.settimeout(timeout)
        yield reusable_socket
        return

    udp_sock = caproto.bcast_socket()
    udp_sock.bind(("", 0))

    udp_sock.settimeout(timeout)
    yield udp_sock
    udp_sock.close()


@contextlib.contextmanager
def override_hostname_and_username(
    hostname: Optional[str] = None,
    username: Optional[str] = None
):
    """Optionally monkeypatch/override socket.gethostname and getpass.getuser."""
    orig_gethostname = socket.gethostname
    orig_getuser = getpass.getuser

    def get_host_name() -> str:
        host = hostname or orig_gethostname()
        logger.debug("Hostname will be: %s", host)
        return host

    def get_user() -> str:
        user = username or orig_getuser()
        logger.debug("Username will be: %s", user)
        return user

    try:
        getpass.getuser = get_user
        socket.gethostname = get_host_name
        yield
    finally:
        getpass.getuser = orig_getuser
        socket.gethostname = orig_gethostname


def _channel_cleanup(chan: caproto.ClientChannel):
    """Clean up the sync client channel."""
    try:
        if chan.states[caproto.CLIENT] is caproto.CONNECTED:
            ca_client.send(chan.circuit, chan.clear(), chan.name)
    finally:
        ca_client.sockets[chan.circuit].close()
        del ca_client.sockets[chan.circuit]
        del ca_client.global_circuits[(chan.circuit.address, chan.circuit.priority)]


def _basic_enum_name(value) -> str:
    """AccessRights.X -> X"""
    return str(value).split(".", 1)[1]


def caget_from_host(
    hostname: str,
    pvname: str,
    timeout: float = ca_client.common.GLOBAL_DEFAULT_TIMEOUT,
    priority: int = 0,
    udp_sock: Optional[socket.socket] = None,
    username: Optional[str] = None,
) -> PVInfo:
    """
    Read a Channel's access security settings for the given hostname.

    Not thread-safe.

    Parameters
    ----------
    hostname : str
        The host name to report when performing the caget.
    pvname : str
        The PV name to check.
    timeout : float, optional
        Default is 1 second.
    priority : 0, optional
        Virtual Circuit priority. Default is 0, lowest. Highest is 99.
    udp_sock : socket.socket, optional
        Optional re-usable UDP socket.
    username : str, optional
        The username to provide when performing the caget.

    Returns
    -------
    pv_info : PVInfo
    """

    chan = None
    pv_info = PVInfo(name=pvname)
    try:
        with bound_udp_socket(
            udp_sock, timeout=timeout
        ) as udp_sock, override_hostname_and_username(hostname, username):
            chan = ca_client.make_channel(pvname, udp_sock, priority, timeout)
            pv_info.access = _basic_enum_name(chan.access_rights)
            pv_info.data_type = _basic_enum_name(chan.native_data_type)
            pv_info.data_count = chan.native_data_count
            pv_info.address = chan.circuit.address
            control_value = ca_client._read(
                chan,
                timeout,
                data_type=ca_client.field_types["control"][chan.native_data_type],
                data_count=min((chan.native_data_count, 1)),
                force_int_enums=True,
                notify=True,
            )
            pv_info.control_md = control_value.metadata.to_dict()

            time_value = ca_client._read(
                chan,
                timeout,
                data_type=ca_client.field_types["time"][chan.native_data_type],
                data_count=min((chan.native_data_count, 1000)),
                force_int_enums=True,
                notify=True,
            )
            pv_info.time_md = time_value.metadata.to_dict()
            pv_info.value = time_value.data
    except TimeoutError:
        pv_info.error = "timeout"
    finally:
        if chan is not None:
            _channel_cleanup(chan)

    return pv_info


def _filter_data(data):
    """Filter data for byte strings and other non-JSON serializable items."""
    if isinstance(data, dict):
        return {
            key: _filter_data(value)
            for key, value in data.items()
        }

    if isinstance(data, np.ndarray):
        return data.tolist()

    if isinstance(data, (list, tuple)):
        return [_filter_data(item) for item in data]

    if isinstance(data, bytes):
        return str(data, "latin-1", "ignore")  # _EPICS_
    return data


def caget_many_from_host(hostname, *pvnames):
    with bound_udp_socket() as udp_sock:
        results = {}
        for pvname in pvnames:
            try:
                info = caget_from_host(hostname, pvname, udp_sock=udp_sock)
            except TimeoutError:
                info = PVInfo(
                    name=pvname,
                    error="timeout",
                )
            results[pvname] = _filter_data(dataclasses.asdict(info))

    return {
        "hostname": hostname,
        "pvs": results,
    }


class AccessBehavior(enum.IntEnum):
    DISCONNECTED = 0
    READ = 1
    WRITE = 2


def interpret_access(access):
    try:
        return AccessBehavior(access)
    except ValueError:
        pass
    try:
        return AccessBehavior[access]
    except KeyError:
        pass
    if access.startswith('WRITE'):
        return AccessBehavior.WRITE
    raise ValueError(f'Could not interpret {access} as an AccessBehavior.')


def promote_access(current, new):
    current = interpret_access(current)
    new = interpret_access(new)
    if new > current:
        return new
    else:
        return current


def demote_access(current, new):
    current = interpret_access(current)
    new = interpret_access(new)
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
        if match.rule.command == 'DENY':
            deny_matches[match.filename] = match
        elif 'ALLOW' in match.rule.command:
            allow_matches[match.filename] = match
        elif 'DENY FROM' in match.rule.command:
            if match.rule.command == f'DENY FROM {hostname}':
                # Short-circuit everything else
                # This sends out a NO_ACCESS event, rather than disconnected
                # Do not need to consider anything else
                return PVInfo(
                    name=pvinfo.name,
                    access="NO_ACCESS",
                )
        else:
            raise NotImplementedError(
                'Programmer did not know that match.rule.command could be '
                f'{match.rule.command}'
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
            if allow.rule.access is None:
                # Default behavior
                gateway_access_summary[filename] = AccessBehavior.READ
            else:
                # Look it up if not default
                access_group = config.access_security.groups[allow.rule.access.group]

                behavior = AccessBehavior.DISCONNECTED
                for rule in access_group.rules:
                    if rule.hosts is None:
                        behavior = promote_access(behavior, rule.options)
                    else:
                        hosts = set()
                        for host_group in rule.hosts:
                            hosts.update(config.access_security.hosts[host_group].hosts)
                        if hostname in hosts:
                            behavior = promote_access(behavior, rule.options)
                gateway_access_summary[filename] = behavior

    # Now we know how each gateway should respond to our PV. So what should we see?
    # Well, ideally we have exactly one or zero READ or WRITE, and the rest disconnected.
    # If we have two READ, two WRITE, one READ and one WRITE, etc. that is an error.
    # Otherwise just contstruct with the non-ambiguous item.
    gw_behavior = [(fn, bh) for (fn, bh) in gateway_access_summary.items()
                   if bh != AccessBehavior.DISCONNECTED]

    if len(gw_behavior) == 0:
        return PVInfo(
            name=pvinfo.name,
            error='timeout',
        )
    elif len(gw_behavior) == 1:
        # Demote our original access level if needed
        new_access = demote_access(pvinfo.access, gw_behavior[0][1])
        if new_access == AccessBehavior.WRITE:
            access_str = 'WRITE|READ'
        else:
            access_str = new_access.name
        # Omit the gateway address- not in scope here
        return PVInfo(
            name=pvinfo.name,
            access=access_str,
            data_type=pvinfo.data_type,
            data_count=pvinfo.data_count,
            value=pvinfo.value,
            error=pvinfo.error,
            time_md=pvinfo.time_md,
            control_md=pvinfo.control_md,
        )
    else:
        raise RuntimeError(f'Gateway configs are inconsistent: {gw_behavior}')


# TODO upstream to pcdsutils
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


# TODO upstream to pcdsutils
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


# TODO upstream to pcdsutils
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
