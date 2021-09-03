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

from .config import PCDSConfiguration

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
    AMBIGUOUS = 0
    NO_ACCESS = 1
    DISCONNECTED = 2
    READ = 3
    WRITE = 4


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


@dataclasses.dataclass
class GatewayResponse:
    """
    How one particular gateway should respond to a request.
    """
    gateway_procname: str
    gateway_hostname: str
    client_hostname: str
    pvname: str
    access: AccessBehavior


@dataclasses.dataclass
class GatewayResponseSummary(GatewayResponse):
    """
    How the gateway network should respond to a request.

    Contains the dominating gateway information if unambiguous.
    If access is AccessBehavior.AMBIGUOUS, then two gateways
    will respond! As such, any ambiguous fields will be
    empty strings and you'll need to investigate the responses
    list.
    """
    subnet_responses: dict[str, GatewayResponse]
    other_responses: dict[str, GatewayResponse]


def predict_gateway_response(
    config: PCDSConfiguration,
    pvname: str,
    hostname: str,
) -> GatewayResponseSummary:
    """
    Predict how the gateways should respond to a request.

    Parameters
    ----------
    config : PCDSConfiguration
        All of the configuration info about the deployed environment.
    pvname : str
        The PV name to check the rules for.
    hostname : str
        The hostname we make the request from.

    Returns
    -------
    summary : GatewayResponseSummary
        Contains the relevant rules, metadata, and results for
        the request.
    """
    # Collect the responses from each gateway
    subnet_responses = {}
    other_responses = {}

    # First, we need to know which subnet the PV is on.
    try:
        ioc_name = config.pv_to_ioc[pvname.split('.')[0]]
    except KeyError:
        raise ValueError(f'Did not find ioc name to match PV {pvname}')
    try:
        pv_hostname = config.ioc_to_host[ioc_name]
    except KeyError:
        raise ValueError(f'Did not find hostname to match ioc {ioc_name}')
    subnet = config.interface_config.subnet_from_hostname(pv_hostname)

    # With the subnet, we can determine which gateway rules are relevant.
    # Only the lowest down in each pvlist file is relevant.
    for match in config.gateway_config.get_matches(pvname).matches:
        gateway_procname = os.path.basename(match.filename).split('.')[0]
        # Edge case: people leaving old pvlists in the config
        if gateway_procname.endswith('old'):
            continue
        if match.rule.command == 'DENY':
            # DENY_FROM sends a NO_ACCESS
            if hostname in match.rule.hosts:
                access = AccessBehavior.NO_ACCESS
            # DENY pretends like the PV is disconnected
            else:
                access = AccessBehavior.DISCONNECTED
        elif match.rule.command == 'ALLOW':
            # Default behavior is read-only
            if match.rule.access is None:
                access = AccessBehavior.READ
            else:
                access_group = config.access_security.groups[
                    match.rule.access.group
                ]
                access = AccessBehavior.DISCONNECTED
                for rule in access_group.rules:
                    if rule.hosts is None:
                        access = promote_access(access, rule.options)
                    else:
                        hosts = set()
                        for host_group in rule.hosts:
                            hosts.update(
                                config.access_security.hosts[host_group].hosts
                            )
                        if hostname in hosts:
                            access = promote_access(access, rule.options)
        else:
            raise NotImplementedError(
                'Programmer did not know that match.rule.command could be '
                f'{match.rule.command}'
                )
        response = GatewayResponse(
            gateway_procname=gateway_procname,
            # TODO map gateway processes to hosts
            gateway_hostname='',
            client_hostname=hostname,
            pvname=pvname,
            access=access,
        )
        # Overwrite any previous rules from that file
        # Only the last rule matters!
        if gateway_procname.startswith(subnet):
            subnet_responses[gateway_procname] = response
        else:
            other_responses[gateway_procname] = response

    # OK, now we combine our responses and predict the overall result.
    # Focus only on subnet_responses, but keep other_responses for debug.
    # We must have one or zero of READ, WRITE, and NO_ACCESS
    # If we have two or more, this is ambiguous.
    # If we have zero, the overall access is disconnected.
    connected_responses = [
        response for response in subnet_responses.values()
        if response.access != AccessBehavior.DISCONNECTED
    ]
    # First case: all disconnected.
    if len(connected_responses) == 0:
        chosen_gwproc = ''
        chosen_gwhost = ''
        overall_access = AccessBehavior.DISCONNECTED
    # Second case: only one option
    elif len(connected_responses) == 1:
        chosen_gwproc = connected_responses[0].gateway_procname
        chosen_gwhost = connected_responses[0].gateway_hostname
        overall_access = connected_responses[0].access
    # Last case: more than one option
    else:
        chosen_gwproc = ''
        chosen_gwhost = ''
        overall_access = AccessBehavior.AMBIGUOUS

    return GatewayResponseSummary(
        gateway_procname=chosen_gwproc,
        gateway_hostname=chosen_gwhost,
        client_hostname=hostname,
        pvname=pvname,
        access=overall_access,
        subnet_responses=subnet_responses,
        other_responses=other_responses,
    )


def correct_gateway_pvinfo(
    response_summary: GatewayResponseSummary,
    pvinfo: PVInfo
) -> PVInfo:
    """
    Determine what the gateway should have give, relative to what the IOC gave us.

    This should be mostly the same, but potentially with a modified access field
    or possibly disconnected.

    Parameters
    ----------
    response_summary : GatewayResponseSummary
        A summary of the gateway should behave for a specific PV.
    pvinfo : PVInfo
        The pv info retrieved from the IOC.

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
    # Handle the AMBIGUOUS, NO_ACCESS, and DISCONNECTED states first
    if response_summary.access == AccessBehavior.AMBIGUOUS:
        raise RuntimeError('Ambiguous access behavior!')
    if response_summary.access == AccessBehavior.NO_ACCESS:
        return PVInfo(
            name=pvinfo.name,
            access='NO_ACCESS',
        )
    if response_summary.access == AccessBehavior.DISCONNECTED:
        return PVInfo(
            name=pvinfo.name,
            error='timeout',
        )

    # The gateway should serve our PV!
    # Demote our original access level if needed
    new_access = demote_access(pvinfo.access, response_summary.access)
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
