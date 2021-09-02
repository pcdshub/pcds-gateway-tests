import dataclasses
import socket

from ..config import PCDSConfiguration
from ..conftest import (compare_structures, find_differences, prod_gw_addrs,
                        prod_ioc_addrs)
from ..util import caget_from_host, correct_gateway_pvinfo


def compare_gets(pvname: str, hosts: list[str]):
    """
    Check if the gateway gives us the correct value.

    Must be run on a gateway machine.

    Gets a value from the IOC, and then from the gateway as
    various source hosts.
    """
    config = PCDSConfiguration.instance()
    gw_pvinfo = {}

    with prod_ioc_addrs(config):
        true_pvinfo = caget_from_host(
            hostname=socket.gethostname(),
            pvname=pvname,
        )
    with prod_gw_addrs(config):
        for host in hosts:
            gw_pvinfo[host] = caget_from_host(
                hostname=host,
                pvname=pvname,
            )

    all_diffs = {}
    for host, pvinfo in gw_pvinfo.items():
        answer = correct_gateway_pvinfo(
            config=config,
            pvinfo=true_pvinfo,
            hostname=host,
        )
        all_diffs[host] = list(find_differences(
            dataclasses.asdict(answer),
            dataclasses.asdict(pvinfo),
            skip_keys=['address'],
            )
        )
        if all_diffs[host]:
            print(f'Issue for {host}:')
            print('\t' + compare_structures(
                dataclasses.asdict(answer),
                dataclasses.asdict(pvinfo),
                desc1='Expected',
                desc2='Gateway',
                )
            )

    return all_diffs
