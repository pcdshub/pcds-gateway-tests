import epics

from .. import conftest


@conftest.standard_test_environment_decorator
def test_basic():
    pv = epics.get_pv("ioc:auto:cnt")
    assert pv.get() == 0.0
