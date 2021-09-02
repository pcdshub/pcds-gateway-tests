import logging
import socket

from ..config import PCDSConfiguration
from ..conftest import find_pvinfo_differences, prod_gw_addrs, prod_ioc_addrs
from ..util import (caget_from_host, correct_gateway_pvinfo,
                    predict_gateway_response)

logger = logging.getLogger(__name__)

HUTCHES = ['amo', 'rix', 'xpp', 'xcs', 'mfx', 'cxi', 'mec']
SUFFS = ['control', 'daq']
CLIENT_HOSTS = [f'{hutch}-{suff}' for hutch in HUTCHES for suff in SUFFS]


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
    with prod_ioc_addrs(config):
        post_pvinfo = caget_from_host(
            hostname=socket.gethostname(),
            pvname=pvname,
        )
    sanity_diff = {
        key: (value1, value2) for key, value1, value2 in
        find_pvinfo_differences(true_pvinfo, post_pvinfo)
    }
    if sanity_diff:
        logger.warning(
            f'{pvname} updated during compare_gets, '
            'ignoring fields that changed.'
        )

    all_diffs = {}
    for host, pvinfo in gw_pvinfo.items():
        predicted_response = predict_gateway_response(
            config=config,
            pvname=pvname,
            hostname=host,
        )
        answer = correct_gateway_pvinfo(
            response_summary=predicted_response,
            pvinfo=true_pvinfo,
        )
        all_diffs[host] = list(
            find_pvinfo_differences(
                answer,
                pvinfo,
                skip_keys=['address'] + list(sanity_diff.keys())
            )
        )
    return all_diffs
