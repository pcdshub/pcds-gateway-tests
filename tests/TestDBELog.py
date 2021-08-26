#!/usr/bin/env python
import os
import time
import unittest

import epics
import GatewayControl
import gwtests
import IOCControl


class TestDBELog(unittest.TestCase):
    """Test log/archive updates (client using DBE_LOG flag) through the Gateway"""

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
        self.diffInsideDeadband = 0
        self.lastValue = -99.9

    def tearDown(self):
        epics.ca.finalize_libca()
        self.gatewayControl.stop()
        self.iocControl.stop()

    def onChange(self, pvname=None, **kws):
        self.eventsReceived += 1
        if gwtests.verbose:
            print(pvname, " changed to ", kws["value"], kws["severity"])
        if (kws["value"] != 0.0) and (abs(self.lastValue - kws["value"]) <= 10.0):
            self.diffInsideDeadband += 1
        self.lastValue = kws["value"]

    def testLogDeadband(self):
        """DBE_LOG monitor on an ai with an ADEL - leaving the deadband generates events."""
        # gateway:passiveADEL has ADEL=10
        ioc = epics.PV("ioc:passiveADEL", auto_monitor=epics.dbr.DBE_LOG)
        gw = epics.PV("gateway:passiveADEL", auto_monitor=epics.dbr.DBE_LOG)
        gw.add_callback(self.onChange)
        ioc.get()
        gw.get()
        for val in range(35):
            ioc.put(val, wait=True)
        time.sleep(0.1)
        # We get 5 events: at connection, first put, then at 11 22 33
        assert self.eventsReceived == 5, "events expected: 5; events received: " + str(
            self.eventsReceived
        )
        # Any updates inside deadband are an error
        assert self.diffInsideDeadband == 0, (
            str(self.diffInsideDeadband) + " events with change <= deadband received"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
