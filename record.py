import contextlib
import dataclasses
import getpass
import json
import socket
import sys
from typing import Any, Optional

import caproto
import caproto.sync.client as client
import numpy as np


@dataclasses.dataclass
class CorePVInfo:
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
    timeout: float = client.common.GLOBAL_DEFAULT_TIMEOUT,
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

    def get_host_name():
        return hostname or orig_gethostname()

    def get_user():
        return username or orig_getuser()

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
            client.send(chan.circuit, chan.clear(), chan.name)
    finally:
        client.sockets[chan.circuit].close()
        del client.sockets[chan.circuit]
        del client.global_circuits[(chan.circuit.address, chan.circuit.priority)]


def _basic_enum_name(value) -> str:
    """AccessRights.X -> X"""
    return str(value).split(".", 1)[1]


def check_basics(
    hostname: str,
    pvname: str,
    timeout: float = client.common.GLOBAL_DEFAULT_TIMEOUT,
    priority: int = 0,
    udp_sock: Optional[socket.socket] = None,
    username: Optional[str] = None,
) -> CorePVInfo:
    """
    Read a Channel's access security settings for the given hostname.

    Not thread-safe.

    Parameters
    ----------
    hostname : str
        The host name to check.
    pvname : str
        The PV name to check.
    timeout : float, optional
        Default is 1 second.
    priority : 0, optional
        Virtual Circuit priority. Default is 0, lowest. Highest is 99.

    Returns
    -------
    response : AccessRightsResponse
    """

    chan = None
    try:
        with bound_udp_socket(udp_sock, timeout=timeout):
            with override_hostname_and_username(hostname, username):
                chan = client.make_channel(pvname, udp_sock, priority, timeout)
                control_value = client._read(
                    chan,
                    timeout,
                    data_type=client.field_types['control'][chan.native_data_type],
                    data_count=min((chan.native_data_count, 1)),
                    force_int_enums=True,
                    notify=True,
                )
                time_value = client._read(
                    chan,
                    timeout,
                    data_type=client.field_types['time'][chan.native_data_type],
                    data_count=min((chan.native_data_count, 1000)),
                    force_int_enums=True,
                    notify=True,
                )
                return CorePVInfo(
                    name=pvname,
                    access=_basic_enum_name(chan.access_rights),
                    data_type=_basic_enum_name(chan.native_data_type),
                    data_count=chan.native_data_count,
                    value=time_value.data,
                    time_md=time_value.metadata.to_dict(),
                    control_md=control_value.metadata.to_dict(),
                    address=chan.circuit.address,
                )
    finally:
        if chan is not None:
            _channel_cleanup(chan)


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


def main():
    hostname, *pvnames = sys.argv[1:]
# caproto.config_caproto_logging(level="DEBUG")

    with bound_udp_socket() as udp_sock:
        results = {}
        for pvname in pvnames:
            try:
                info = check_basics(hostname, pvname, udp_sock=udp_sock)
            except TimeoutError:
                info = CorePVInfo(
                    name=pvname,
                    error="timeout",
                )
            results[pvname] = _filter_data(dataclasses.asdict(info))

    return {
        "hostname": hostname,
        "pvs": results,
    }


if __name__ == '__main__':
    results = main()
    print(json.dumps(results, indent=4))
