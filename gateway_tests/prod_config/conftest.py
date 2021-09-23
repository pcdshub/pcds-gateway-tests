"""
Test fixtures and utilities specific to prod testing
"""
import logging
import socket
import subprocess
import time
import uuid

import pytest

from ..config import PCDSConfiguration
from ..conftest import (find_pvinfo_differences, interpret_pvinfo_differences,
                        prod_gw_addrs, prod_ioc_addrs, pvinfo_diff_report)
from ..util import (caget_from_host, correct_gateway_pvinfo,
                    predict_gateway_response)

HUTCHES = ['tmo', 'rix', 'xpp', 'xcs', 'mfx', 'cxi', 'mec']
SUFFS = ['control', 'daq']
CLIENT_HOSTS = [f'{hutch}-{suff}' for hutch in HUTCHES for suff in SUFFS]

logger = logging.getLogger(__name__)
config = PCDSConfiguration.instance()
our_host = socket.gethostname()
disconnected_iocs = set()
online_hosts = set()
offline_hosts = set()


def maybe_skip_host(hostname):
    skip = False
    if hostname in offline_hosts:
        skip = True
    elif hostname in online_hosts:
        return
    else:
        skip = not ping(hostname)
    if skip:
        offline_hosts.add(hostname)
        pytest.skip(f'Host {hostname} is offline.')
    else:
        online_hosts.add(hostname)


def ping(hostname):
    return subprocess.call(['ping', '-c', '1', str(hostname)]) == 0


class DisconnectedError(Exception):
    ...


def compare_gets(pvname: str, hosts: list[str], skip_disconnected=False):
    """
    Check if the gateway gives us the correct value.

    Must be run on a gateway machine.

    Gets a value from the IOC, and then from the gateway as
    various source hosts.
    """
    gw_pvinfo = {}

    with prod_ioc_addrs(config):
        true_pvinfo = caget_from_host(
            hostname=our_host,
            pvname=pvname,
        )
    if skip_disconnected and true_pvinfo.error == 'timeout':
        raise DisconnectedError(f'{pvname} is disconnected. Aborting.')
    with prod_gw_addrs(config):
        for host in hosts:
            gw_pvinfo[host] = caget_from_host(
                hostname=host,
                pvname=pvname,
            )
    with prod_ioc_addrs(config):
        post_pvinfo = caget_from_host(
            hostname=our_host,
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


def get_iocname(pvname):
    base_pvname = pvname.split('.')[0]
    return config.pv_to_ioc[base_pvname]


def compare_gets_all_reasonable_hosts(pvname, skip_disconnected=False):
    # Try every host except the ones that pvname shares subnet with
    iocname = get_iocname(pvname)
    hostname = config.ioc_to_host[iocname]
    pv_subnet = config.interface_config.subnet_from_hostname(hostname)

    hosts = [
        host for host in CLIENT_HOSTS
        if pv_subnet != config.interface_config.subnet_from_hostname(host)
    ]
    return compare_gets(pvname, hosts, skip_disconnected=skip_disconnected)


def assert_cagets(pvname, skip_disconnected=False):
    if skip_disconnected:
        try:
            iocname = get_iocname(pvname)
        except KeyError:
            iocname = None
        if iocname in disconnected_iocs:
            pytest.skip(f'IOC {iocname} is disconnected.')
        try:
            hostname = config.ioc_to_host[iocname]
        except KeyError:
            hostname = None
        maybe_skip_host(hostname)
    try:
        diffs, predicts, true_pvinfo = compare_gets_all_reasonable_hosts(
            pvname,
            skip_disconnected=skip_disconnected,
            )
    except DisconnectedError:
        if skip_disconnected:
            if iocname is not None:
                disconnected_iocs.add(iocname)
            pytest.skip(f'PV {pvname} is disconnected.')
    for host, diff in diffs.items():
        assert not diff, interpret_pvinfo_differences(diff, pvname)
    return diffs, predicts, true_pvinfo


def get_extra_pvs(pvlist):
    extra_pvs = []
    for pvname in pvlist:
        if pvname.endswith(':ArrayData'):
            extra_pvs.append(f'{pvname}.NORD')
    return extra_pvs


@pytest.fixture(scope='module')
def diff_report():
    yield
    filename = f'diff_report_{int(time.time())}_{str(uuid.uuid4())[-8:]}.json'
    pvinfo_diff_report(config, filename)
