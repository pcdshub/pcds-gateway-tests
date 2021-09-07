import logging
import os

import pytest

from ..config import PCDSConfiguration
from .conftest import assert_cagets, get_extra_pvs

ENV_VAR = 'PYTEST_GATEWAY_SUBNETS'

logger = logging.getLogger(__name__)
config = PCDSConfiguration.instance()

try:
    env_var = os.environ[ENV_VAR]
    subnets = env_var.split(' ')
    subnets = [subnet.lower() for subnet in subnets]
except Exception:
    subnets = []
    logger.error(f'Issues with env variable {ENV_VAR}')

if 'test_the_tests' in subnets:
    pvlist = [
        'IM1K0:XTES:MMS',
        'IM1K0:XTES:CAM:IMAGE1:ArrayData',
    ]
elif subnets:
    pvlist = []
    for pvname, iocname in config.pv_to_ioc.items():
        try:
            hostname = config.ioc_to_host[iocname]
            subnet = config.interface_config.subnet_from_hostname(hostname)
            if subnet in subnets:
                pvlist.append(pvname)
        except Exception:
            logger.error(f'Skip {pvname}, issue resolving subnet.')
else:
    pvlist = list(config.pv_to_ioc.keys())

extra_pvs = get_extra_pvs(pvlist)


@pytest.mark.parametrize("pvname", pvlist + extra_pvs)
def test_subnet_pvs(pvname):
    assert_cagets(pvname, skip_disconnected=True)
