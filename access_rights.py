import json
import socket
import sys
from typing import Optional

import caproto
import caproto.sync.client as client

GETHOSTNAME = socket.gethostname


def check_access_security(
    host_name: str,
    pv_name: str,
    timeout: float = client.common.GLOBAL_DEFAULT_TIMEOUT,
    priority: int = 0,
    udp_sock: Optional[socket.socket] = None,
) -> caproto.AccessRightsResponse:
    """
    Read a Channel's access security settings for the given hostname.

    Not thread-safe.

    Parameters
    ----------
    host_name : str
        The host name to check.
    pv_name : str
        The PV name to check.
    timeout : float, optional
        Default is 1 second.
    priority : 0, optional
        Virtual Circuit priority. Default is 0, lowest. Highest is 99.

    Returns
    -------
    response : AccessRightsResponse
    """

    def get_host_name():
        return host_name

    close_udp = udp_sock is None
    if udp_sock is None:
        udp_sock = caproto.bcast_socket()
        udp_sock.bind(("", 0))
    try:
        socket.gethostname = get_host_name
        udp_sock.settimeout(timeout)
        chan = client.make_channel(pv_name, udp_sock, priority, timeout)
    finally:
        socket.gethostname = GETHOSTNAME
        if close_udp:
            udp_sock.close()

    try:
        return chan.access_rights
    finally:
        try:
            if chan.states[caproto.CLIENT] is caproto.CONNECTED:
                client.send(chan.circuit, chan.clear(), chan.name)
        finally:
            client.sockets[chan.circuit].close()
            del client.sockets[chan.circuit]
            del client.global_circuits[(chan.circuit.address, chan.circuit.priority)]


def main():
    host_name, *pvnames = sys.argv[1:]
# caproto.config_caproto_logging(level="DEBUG")

    udp_sock = caproto.bcast_socket()
    udp_sock.bind(("", 0))

    access = {}
    try:
        for pvname in pvnames:
            try:
                rights = check_access_security(host_name, pvname, udp_sock=udp_sock)
                access[pvname] = str(rights).split(".")[1]
            except TimeoutError:
                access[pvname] = "timeout"
    finally:
        udp_sock.close()

    return {
        "hostname": host_name,
        "access": access
    }


if __name__ == '__main__':
    results = main()
    print(json.dumps(results, indent=4))
