"""
CA Gateway test configuration.


Environment variables used:

    EPICS_BASE
    EPICS_HOST_ARCH
    VERBOSE
    VERBOSE_GATEWAY
    EPICS_EXTENSIONS
    IOC_EPICS_BASE or EPICS_BASE
"""

import os
import shutil

os.environ["PYEPICS_LIBCA"] = os.path.join(
    os.environ["EPICS_BASE"], "lib", os.environ["EPICS_HOST_ARCH"], "libca.so"
)

# CA ports to use
iocPort = 12782
gwPort = 12783

# Duration of standalong runs
gwRunDuration = 300
iocRunDuration = 300

# Gateway attributes
gwStatsPrefix = "gwtest"

gwExecutable = ""
gwDebug = 10

verbose = os.environ.get("VERBOSE", "").lower().startswith("y")

# Do we want debug logging from the gateway
verboseGateway = False
if "VERBOSE_GATEWAY" in os.environ:
    verboseGateway = True
    if os.environ["VERBOSE_GATEWAY"].isdigit():
        gwDebug = os.environ["VERBOSE_GATEWAY"]

hostArch = os.environ.get("EPICS_HOST_ARCH", os.environ.get("T_A"))
if hostArch is None:
    raise RuntimeError("EPICS_HOST_ARCH and T_A not set")

epics_extensions = os.environ.get("EPICS_EXTENSIONS", "")
gwExecutable = os.path.join(epics_extensions, "bin", hostArch, "gateway")

if not os.path.exists(gwExecutable):
    raise RuntimeError(
        f"Gateway executable {gwExecutable} does not exist; set GW_SITE_TOP."
    )

if "IOC_EPICS_BASE" in os.environ:
    iocExecutable = os.path.join(
        os.environ["IOC_EPICS_BASE"], "bin", hostArch, "softIoc"
    )
elif "EPICS_BASE" in os.environ:
    iocExecutable = os.path.join(os.environ["EPICS_BASE"], "bin", hostArch, "softIoc")
else:
    iocExecutable = shutil.which("softIoc")

if not iocExecutable or not os.path.exists(iocExecutable):
    raise RuntimeError(f"softIoc path {iocExecutable} does not exist")
