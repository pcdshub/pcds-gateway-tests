#!/usr/bin/env python
import os
import sys
import time
import unittest

import GatewayControl
import gwtests
import IOCControl
from epics import ca, dbr


class TestStructures(unittest.TestCase):
    """
    Testing structures going through the Gateway
    Set up a connection directly and through the Gateway - change a property -
    check consistency of data
    """

    def setUp(self):
        gwtests.setup()
        self.iocControl = IOCControl.IOCControl()
        self.gatewayControl = GatewayControl.GatewayControl()
        self.iocControl.startIOC()
        self.gatewayControl.startGateway()
        self.propSupported = False
        self.eventsReceivedIOC = 0
        self.eventsReceivedGW = 0
        os.environ["EPICS_CA_AUTO_ADDR_LIST"] = "NO"
        os.environ[
            "EPICS_CA_ADDR_LIST"
        ] = f"localhost:{gwtests.iocPort} localhost:{gwtests.gwPort}"
        ca.initialize_libca()

    def tearDown(self):
        ca.finalize_libca()
        self.gatewayControl.stop()
        self.iocControl.stop()

    def onChangeIOC(self, pvname=None, **kws):
        self.eventsReceivedIOC += 1
        self.iocStruct = kws
        if gwtests.verbose:
            fmt = "New IOC Value for %s value=%s, kw=%s\n"
            sys.stdout.write(fmt % (pvname, str(kws["value"]), repr(kws)))
            sys.stdout.flush()

    def onChangeGW(self, pvname=None, **kws):
        self.eventsReceivedGW += 1
        self.gwStruct = kws
        if gwtests.verbose:
            fmt = "New GW Value for %s value=%s, kw=%s\n"
            sys.stdout.write(fmt % (pvname, str(kws["value"]), repr(kws)))
            sys.stdout.flush()

    def compareStructures(self):
        are_diff = False
        diffs = []
        for k in list(self.iocStruct.keys()):
            if k != "chid" and (self.iocStruct[k] != self.gwStruct[k]):
                are_diff = True
                diffs.append(
                    "Element '{}' : GW has '{}', IOC has '{}'".format(
                        k, str(self.gwStruct[k]), str(self.iocStruct[k])
                    )
                )
        return are_diff, diffs

    @unittest.skipIf(
        os.environ.get("BASE") == "3.14",
        "updates of CTRL structures are buggy in 3.14 PCAS",
    )
    def testCtrlStruct_ValueMonitor(self):
        """
        Monitor PV (value events) through GW - change value and properties
        directly - check CTRL structure consistency
        """
        diffs = []

        # gwcachetest is an ai record with full set of alarm limits: -100 -10 10 100
        gw = ca.create_channel("gateway:gwcachetest")
        connected = ca.connect_channel(gw, timeout=0.5)
        assert connected, "Could not connect to gateway channel " + ca.name(gw)
        (gw_cbref, gw_uaref, gw_eventid) = ca.create_subscription(
            gw, mask=dbr.DBE_VALUE, use_ctrl=True, callback=self.onChangeGW
        )
        ioc = ca.create_channel("ioc:gwcachetest")
        connected = ca.connect_channel(ioc, timeout=0.5)
        assert connected, "Could not connect to ioc channel " + ca.name(ioc)
        (ioc_cbref, ioc_uaref, ioc_eventid) = ca.create_subscription(
            ioc, mask=dbr.DBE_VALUE, use_ctrl=True, callback=self.onChangeIOC
        )

        # set value on IOC
        ioc_value = ca.create_channel("ioc:gwcachetest")
        ca.put(ioc_value, 10.0, wait=True)
        time.sleep(0.1)

        assert (
            self.eventsReceivedIOC == self.eventsReceivedGW
        ), "After setting value, no. of received updates differ: GW {}, IOC {}".format(
            str(self.eventsReceivedGW), str(self.eventsReceivedIOC)
        )

        (are_diff, diffs) = self.compareStructures()
        assert (
            not are_diff
        ), "At update {} (change value), received structure updates differ:\n\t{}".format(
            str(self.eventsReceivedIOC), "\n\t".join(diffs)
        )

        # set property on IOC
        ioc_hihi = ca.create_channel("ioc:gwcachetest.HIHI")
        ca.put(ioc_hihi, 123.0, wait=True)
        ca.put(ioc_value, 11.0, wait=True)  # trigger update
        time.sleep(0.1)

        assert (
            self.eventsReceivedIOC == self.eventsReceivedGW
        ), "After setting property, no. of received updates differ: GW {}, IOC {}".format(
            str(self.eventsReceivedGW), str(self.eventsReceivedIOC)
        )

        (are_diff, diffs) = self.compareStructures()
        assert (
            are_diff
        ), "At update {} (change property), received structure updates differ:\n\t{}".format(
            str(self.eventsReceivedIOC), "\n\t".join(diffs)
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
