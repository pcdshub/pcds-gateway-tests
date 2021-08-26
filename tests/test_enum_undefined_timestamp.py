#!/usr/bin/env python
import logging
import time

import conftest
import epics

logger = logging.getLogger(__name__)


@conftest.standard_test_environment_decorator
def test_undefined_timestamp():
    """Two caget on an mbbi - both timestamps should be defined."""
    gateway_events_received = 0
    ioc_events_received = 0

    def on_change_gateway(pvname=None, **kws):
        nonlocal gateway_events_received
        gateway_events_received += 1
        timestamp_str = "<undefined>"
        timestamp = kws.get("timestamp")
        if timestamp != epics.dbr.EPICS2UNIX_EPOCH:
            timestamp_str = time.ctime(timestamp)
        logger.info(f' GW update: {pvname} changed to {kws["value"]} at {timestamp_str}')

    def on_change_ioc(pvname=None, **kws):
        nonlocal ioc_events_received
        ioc_events_received += 1
        timestamp_str = "<undefined>"
        timestamp = kws.get("timestamp")
        if timestamp != epics.dbr.EPICS2UNIX_EPOCH:
            timestamp_str = time.ctime(timestamp)
        logger.info(f'IOC update: {pvname} changed to {kws["value"]} at {timestamp_str}')

    ioc_pv = epics.PV("ioc:HUGO:ENUM", auto_monitor=None)
    ioc_pv.wait_for_connection()
    ioc_pv.add_callback(on_change_ioc)

    gateway_pv = epics.PV("gateway:HUGO:ENUM", auto_monitor=None)
    gateway_pv.wait_for_connection()
    gateway_pv.add_callback(on_change_gateway)
    ioc_value = ioc_pv.get()
    gateway_value = gateway_pv.get()

    # Verify timestamp and value match
    assert ioc_value == gateway_value, f"ioc = {ioc_value} !=\ngw = {gateway_value}"

    # Now get the gateway value again and make sure the timestamp is not undefined
    gateway_pv.get()
    if ioc_pv.status != epics.dbr.AlarmStatus.UDF:
        assert gateway_pv.status != epics.dbr.AlarmStatus.UDF, "2nd CA get is undefined!"
    assert gateway_pv.timestamp != 0, "2nd CA get timestamp is undefined!"
    assert ioc_value == gateway_value
