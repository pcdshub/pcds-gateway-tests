import logging
import socket

import pytest

from ..compare import get_missing_pvs
from ..config import PCDSConfiguration
from ..conftest import find_pvinfo_differences, prod_gw_addrs, prod_ioc_addrs
from ..util import (caget_from_host, correct_gateway_pvinfo,
                    predict_gateway_response)

HUTCHES = ['amo', 'rix', 'xpp', 'xcs', 'mfx', 'cxi', 'mec']
SUFFS = ['control', 'daq']
CLIENT_HOSTS = [f'{hutch}-{suff}' for hutch in HUTCHES for suff in SUFFS]

logger = logging.getLogger(__name__)
config = PCDSConfiguration.instance()
pvlists_by_happi_name = config.happi_info.get_pvlist_by_key()
missing_pvs = set(get_missing_pvs())


def compare_gets(pvname: str, hosts: list[str]):
    """
    Check if the gateway gives us the correct value.

    Must be run on a gateway machine.

    Gets a value from the IOC, and then from the gateway as
    various source hosts.
    """
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

    all_predicts = {}
    all_diffs = {}
    for host, pvinfo in gw_pvinfo.items():
        predicted_response = predict_gateway_response(
            config=config,
            pvname=pvname,
            hostname=host,
        )
        all_predicts[host] = predicted_response
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
    return all_diffs, all_predicts, true_pvinfo


def compare_gets_all_reasonable_hosts(pvname):
    # Try every host except the ones that pvname shares subnet with
    iocname = config.pv_to_ioc[pvname]
    hostname = config.ioc_to_host[iocname]
    pv_subnet = config.interface_config.subnet_from_hostname(hostname)

    hosts = [
        host for host in CLIENT_HOSTS
        if pv_subnet != config.interface_config.subnet_from_hostname(host)
    ]
    return compare_gets(pvname, hosts)


def assert_cagets(pvname):
    diffs, predicts, true_pvinfo = compare_gets_all_reasonable_hosts(pvname)
    for host, diff in diffs.items():
        assert not diff, (
            f'Unexpected difference (expected, actual) {diff} '
            f'for caget {pvname} on host {host}. '
            f'Gateway prediction was {predicts[host]}'
        )
    return diffs, predicts, true_pvinfo


@pytest.mark.parametrize("name", list(pvlists_by_happi_name))
def test_happi_devices(name):
    pvlist = pvlists_by_happi_name[name]
    for pvname in pvlist:
        if pvname in missing_pvs:
            logger.warning(f'Skip {pvname}, missing from pvlists.')
            continue
        _, _, pvinfo = assert_cagets(pvname)
        if pvinfo.error == 'timeout':
            logger.warning(f'Skip rest of {name}, disconnected PV')
            break
