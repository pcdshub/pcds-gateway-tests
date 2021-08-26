#!/usr/bin/env python
import os
import time
import unittest

import epics
import GatewayControl
import gwtests
import IOCControl


class TestDBEAlarm(unittest.TestCase):
    """Test alarm updates (client using DBE_ALARM flag) through the Gateway"""

    def setUp(self):
        gwtests.setup()
        self.iocControl = IOCControl.IOCControl()
        self.gatewayControl = GatewayControl.GatewayControl()
        self.iocControl.startIOC()
        self.gatewayControl.startGateway()
        os.environ["EPICS_CA_AUTO_ADDR_LIST"] = "NO"
        os.environ[
            "EPICS_CA_ADDR_LIST"
        ] = f"localhost:{gwtests.iocPort} localhost:{gwtests.gwPort}"
        epics.ca.initialize_libca()
        self.eventsReceived = 0
        self.severityUnchanged = 0
        self.lastSeverity = 4

    def tearDown(self):
        epics.ca.finalize_libca()
        self.gatewayControl.stop()
        self.iocControl.stop()

    def onChange(self, pvname=None, **kws):
        self.eventsReceived += 1
        if gwtests.verbose:
            print(pvname, " changed to ", kws["value"], kws["severity"])
        if self.lastSeverity == kws["severity"]:
            self.severityUnchanged += 1
        self.lastSeverity = kws["severity"]

    def testAlarmLevel(self):
        """
        DBE_ALARM monitor on an ai with two alarm levels - crossing the level
        generates updates
        """
        # gateway:passiveALRM has HIGH=5 (MINOR) and HIHI=10 (MAJOR)
        ioc = epics.PV("ioc:passiveALRM", auto_monitor=epics.dbr.DBE_ALARM)
        gw = epics.PV("gateway:passiveALRM", auto_monitor=epics.dbr.DBE_ALARM)
        gw.add_callback(self.onChange)
        ioc.get()
        gw.get()
        for val in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0]:
            ioc.put(val, wait=True)
        time.sleep(0.1)
        # We get 6 events: at connection (INVALID), at first write (NO_ALARM),
        # and at the level crossings MINOR-MAJOR-MINOR-NO_ALARM.
        assert (
            self.eventsReceived == 6
        ), f"events expected: 6; events received: {self.eventsReceived}"
        # Any updates with unchanged severity are an error
        assert (
            self.severityUnchanged == 0
        ), f"{self.severityUnchanged} events with no severity changes received"


if __name__ == "__main__":
    unittest.main(verbosity=2)
