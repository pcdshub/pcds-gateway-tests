import logging

import pytest

from ..compare import get_missing_pvs
from ..config import PCDSConfiguration
from .conftest import assert_cagets

MAX_PV_CHECKS_PER_DEVICE = 100

logger = logging.getLogger(__name__)
config = PCDSConfiguration.instance()
pvlists_by_happi_name = config.happi_info.get_pvlist_by_key()
missing_pvs = set(get_missing_pvs())


@pytest.mark.parametrize("name", list(pvlists_by_happi_name))
def test_happi_devices(name):
    pvlist = pvlists_by_happi_name[name]
    pvs_checked = 0
    for pvname in pvlist:
        if pvname in missing_pvs:
            logger.warning(f'Skip {pvname}, missing from pvlists.')
            continue
        _, _, pvinfo = assert_cagets(pvname)
        pvs_checked += 1
        if pvinfo.error == 'timeout':
            logger.warning(f'Skip rest of {name}, disconnected PV')
            break
        if pvs_checked >= MAX_PV_CHECKS_PER_DEVICE:
            break
    assert pvs_checked > 0, f'Ran test for {name} without checking any PVs'
