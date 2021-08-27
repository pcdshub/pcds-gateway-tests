#!/usr/bin/env python
import logging
import time

import conftest
import epics

logger = logging.getLogger(__name__)


def timestamp_to_string(timestamp: float) -> str:
    if timestamp == epics.dbr.EPICS2UNIX_EPOCH:
        return "<undefined>"
    return time.ctime(timestamp)


@conftest.standard_test_environment_decorator
def test_undefined_timestamp():
    """Two caget on an mbbi - both timestamps should be defined."""
    gateway_events_received = 0
    ioc_events_received = 0

    def on_change_gateway(pvname=None, value=None, timestamp=None, **kwargs):
        nonlocal gateway_events_received
        gateway_events_received += 1
        logger.info(
            f' GW update: {pvname} changed to {value} at %s',
            timestamp_to_string(timestamp)
        )

    def on_change_ioc(pvname=None, value=None, timestamp=None, **kwargs):
        nonlocal ioc_events_received
        ioc_events_received += 1
        logger.info(
            f'IOC update: {pvname} changed to {value} at %s',
            timestamp_to_string(timestamp)
        )

    ioc_pv, gateway_pv = conftest.get_pv_pair(
        "HUGO:ENUM",
        auto_monitor=None,
        ioc_callback=on_change_ioc,
        gateway_callback=on_change_gateway,
    )

    ioc_value = ioc_pv.get()
    gateway_value = gateway_pv.get()

    # Verify timestamp and value match
    assert ioc_value == gateway_value, f"ioc = {ioc_value} != gw = {gateway_value}"

    # Now get the gateway value again and make sure the timestamp is not undefined
    gateway_pv.get()
    if ioc_pv.status != epics.dbr.AlarmStatus.UDF:
        assert gateway_pv.status != epics.dbr.AlarmStatus.UDF, "2nd CA get is undefined!"
    assert gateway_pv.timestamp != 0, "2nd CA get timestamp is undefined!"
    assert ioc_value == gateway_value
