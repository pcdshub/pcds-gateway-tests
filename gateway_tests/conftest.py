"""
CA Gateway test configuration.


Environment variables used:

    EPICS_BASE
    EPICS_HOST_ARCH
    GATEWAY_PVLIST
    GATEWAY_ROOT
    IOC_EPICS_BASE or EPICS_BASE
    VERBOSE
    VERBOSE_GATEWAY

"""

import contextlib
import functools
import logging
import math
import os
import pathlib
import shutil
import subprocess
import tempfile
import textwrap
import time
from concurrent.futures import ProcessPoolExecutor
from typing import Any, ContextManager, Generator, Optional, Protocol

import epics
import pytest

logger = logging.getLogger(__name__)

libca_so = os.path.join(
    os.environ["EPICS_BASE"], "lib", os.environ["EPICS_HOST_ARCH"], "libca.so"
)
if "PYEPICS_LIBCA" not in os.environ and os.path.exists(libca_so):
    os.environ["PYEPICS_LIBCA"] = libca_so

MODULE_PATH = pathlib.Path(__file__).parent.resolve()

# CA ports to use
default_ioc_port = 12782
default_gw_port = 12783
default_access = os.environ.get(
    "GATEWAY_ACCESS", str(MODULE_PATH / "process" / "default_access.txt")
)
default_pvlist = os.environ.get(
    "GATEWAY_PVLIST", str(MODULE_PATH / "process" / "pvlist_bre.txt")
)
test_ioc_db = os.environ.get(
    "TEST_DB", str(MODULE_PATH / "process" / "test.db")
)
site_access = os.environ.get(
    "GATEWAY_SITE_ACCESS", "/cds/group/pcds/gateway/config/pcds-access.acf"
)

verbose = os.environ.get("VERBOSE", "").lower().startswith("y")

# Do we want debug logging from the gateway
if "VERBOSE_GATEWAY" not in os.environ:
    verbose_gateway = False
    gateway_debug_level = 10
else:
    verbose_gateway = True
    try:
        gateway_debug_level = int(os.environ["VERBOSE_GATEWAY"])
    except ValueError:
        gateway_debug_level = 10


hostArch = os.environ.get("EPICS_HOST_ARCH", os.environ.get("T_A"))
if hostArch is None:
    raise RuntimeError("EPICS_HOST_ARCH and T_A not set")

try:
    gateway_executable = os.path.join(
        os.environ["GATEWAY_ROOT"], "bin", hostArch, "gateway"
    )
except KeyError:
    raise RuntimeError("Set GATEWAY_ROOT to point to the gateway to test") from None

if not os.path.exists(gateway_executable):
    raise RuntimeError(
        f"Gateway executable {gateway_executable} does not exist; set GW_SITE_TOP."
    )

if "IOC_EPICS_BASE" in os.environ:
    ioc_executable = os.path.join(
        os.environ["IOC_EPICS_BASE"], "bin", hostArch, "softIoc"
    )
elif "EPICS_BASE" in os.environ:
    ioc_executable = os.path.join(os.environ["EPICS_BASE"], "bin", hostArch, "softIoc")
else:
    ioc_executable = shutil.which("softIoc")

if not ioc_executable or not os.path.exists(ioc_executable):
    raise RuntimeError(f"softIoc path {ioc_executable} does not exist")


@contextlib.contextmanager
def run_process(
    cmd: list[str],
    env: dict[str, str],
    verbose: bool = False,
    interactive: bool = False,
    startup_time: float = 0.5,
):
    """Run ``cmd`` and yield a subprocess.Popen instance."""
    logger.info("Running: %s (verbose=%s)", " ".join(cmd), verbose)

    with open(os.devnull, "wb") as dev_null:
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=dev_null if not verbose else None,
            stderr=subprocess.STDOUT,
        )
        # Arbitrary startup time
        time.sleep(startup_time)
        try:
            yield proc
        finally:
            if interactive:
                logger.debug("Exiting interactive process %s", cmd[0])
                proc.stdin.close()
            else:
                logger.debug("Terminating non-interactive process %s", cmd[0])
                proc.terminate()
            proc.wait()


@contextlib.contextmanager
def run_ioc(
    *arglist: str,
    startup_time: float = 0.5,
    db_file: Optional[str] = test_ioc_db,
    dbd_file: Optional[str] = None,
    ioc_port: int = default_ioc_port,
) -> ContextManager[subprocess.Popen]:
    """
    Starts a test IOC process with the provided configuration.

    Parameters
    ----------
    *arglist : str
        Extra arguments to pass to the IOC process.

    startup_time : float, optional
        Time to wait for the IOC to be ready.

    db_file : str, optional
        Path to the IOC database.  Defaults to ``test_ioc_db``.

    dbd_file : str, optional
        Path to the IOC database definition.  Defaults to using the database
        definition provided with epics-base/softIoc.

    ioc_port : int, optional
        The IOC port number to listen on - defaults to ``default_ioc_port``.
    """
    env = dict(os.environ)
    env["EPICS_CA_SERVER_PORT"] = str(ioc_port)
    env["EPICS_CA_ADDR_LIST"] = "localhost"
    env["EPICS_CA_AUTO_ADDR_LIST"] = "NO"
    # IOC_ environment overrides
    for v in list(os.environ.keys()):
        if v.startswith("IOC_"):
            env[v.replace("IOC_", "", 1)] = os.environ[v]

    cmd = [ioc_executable]
    if dbd_file is not None:
        cmd.extend(["-D", dbd_file])

    if db_file is not None:
        cmd.extend(["-d", db_file])

    cmd.extend(arglist)

    with run_process(cmd, env, verbose=verbose, interactive=True) as proc:
        yield proc


@contextlib.contextmanager
def run_gateway(
    *extra_args: str,
    access: str = default_access,
    pvlist: str = default_pvlist,
    ioc_port: int = default_ioc_port,
    gateway_port: int = default_gw_port,
    verbose: bool = verbose_gateway,
    stats_prefix: str = "gwtest",
) -> ContextManager[subprocess.Popen]:
    """
    Starts a gateway process with the provided configuration.

    Parameters
    ----------
    *extra_args : str
        Extra arguments to pass to the gateway process.

    access : str, optional
        The access rights file.  Defaults to ``default_access``.

    pvlist : str, optional
        The pvlist filename.  Defaults to ``default_pvlist``.

    ioc_port : int, optional
        The IOC port number - defaults to ``default_ioc_port``.

    gateway_port : int, optional
        The gateway port number - defaults to ``default_gw_port``.

    verbose : bool, optional
        Configure the gateway to output verbose information.

    stats_prefix : str, optional
        Gateway statistics PV prefix.
    """
    cmd = [
        gateway_executable,
        "-sip", "localhost",
        "-sport", str(gateway_port),
        "-cip", "localhost",
        "-cport", str(ioc_port),
        "-access", access,
        "-pvlist", pvlist,
        "-archive",
        "-prefix", stats_prefix,
    ]
    cmd.extend(extra_args)

    if verbose:
        cmd.extend(["-debug", str(gateway_debug_level)])

    with run_process(cmd, os.environ, verbose=verbose, interactive=False) as proc:
        yield proc


@contextlib.contextmanager
def local_channel_access(
    *ports: int
):
    """
    Configures environment variables to only talk to the provided ports.

    Parameters
    ----------
    *ports : int
        The integer port numbers to configure for EPICS_CA_ADDR_LIST. If not
        provided, defaults to ``[default_ioc_port, default_gw_port]``.
    """
    if not len(ports):
        ports = [default_ioc_port, default_gw_port]

    address_list = " ".join(f"localhost:{port}" for port in ports)
    with context_set_env("EPICS_CA_AUTO_ADDR_LIST", "NO"):
        with context_set_env("EPICS_CA_ADDR_LIST", address_list):
            epics.ca.initialize_libca()
            try:
                yield
            finally:
                # This may lead to instability - probably should only run one test per
                # process
                epics.ca.clear_cache()
                epics.ca.finalize_libca()
                time.sleep(0.2)


@contextlib.contextmanager
def context_set_env(key: str, value: Any):
    """Context manager to set - and then reset - an environment variable."""
    orig_value = os.environ.get(key, None)
    try:
        os.environ[key] = str(value)
        yield orig_value
    finally:
        if orig_value is not None:
            os.environ[key] = orig_value


@contextlib.contextmanager
def gateway_channel_access_env():
    """Set the environment up for communication solely with the spawned gateway."""
    with context_set_env("EPICS_CA_AUTO_ADDR_LIST", "NO"):
        with context_set_env("EPICS_CA_ADDR_LIST", f"localhost:{default_gw_port}"):
            yield


@contextlib.contextmanager
def ioc_channel_access_env():
    """Set the environment up for communication solely with the spawned IOC."""
    with context_set_env("EPICS_CA_AUTO_ADDR_LIST", "NO"):
        with context_set_env("EPICS_CA_ADDR_LIST", f"localhost:{default_ioc_port}"):
            yield


@contextlib.contextmanager
def standard_test_environment(
    access: str = default_access,
    pvlist: str = default_pvlist,
    db_file: str = test_ioc_db,
    dbd_file: Optional[str] = None,
):
    """
    Standard test environment, using already-existing access rights, pvlist,
    and database files.

    Parameters
    ----------
    access : str, optional
        The access rights filename.  Defaults to ``default_access``.

    pvlist : str, optional
        The pvlist filename.  Defaults to ``default_pvlist``.

    db_file : str, optional
        Path to the IOC database.  Defaults to ``test_ioc_db``.

    dbd_file : str, optional
        Path to the IOC database definition.  Defaults to using the database
        definition provided with epics-base/softIoc.
    """
    with run_gateway(access=access, pvlist=pvlist):
        with run_ioc(db_file=db_file, dbd_file=dbd_file):
            with local_channel_access():
                yield


def standard_test_environment_decorator(
    func=None,
    access: str = default_access,
    pvlist: str = default_pvlist,
    db_file: str = test_ioc_db,
    dbd_file: Optional[str] = None,
):
    """
    Standard test environment as a decorator for a test function, using
    already-existing access rights, pvlist, and database files.

    Parameters
    ----------
    access : str, optional
        The access rights filename.  Defaults to ``default_access``.

    pvlist : str, optional
        The pvlist filename.  Defaults to ``default_pvlist``.

    db_file : str, optional
        Path to the IOC database.  Defaults to ``test_ioc_db``.

    dbd_file : str, optional
        Path to the IOC database definition.  Defaults to using the database
        definition provided with epics-base/softIoc.
    """
    def wrapper(func):
        @functools.wraps(func)
        def wrapped(*args, **kwargs):
            with standard_test_environment(
                access=access, pvlist=pvlist, db_file=db_file, dbd_file=dbd_file
            ):
                return func(*args, **kwargs)
        return wrapped

    if func is not None:
        return wrapper(func)

    return wrapper


@contextlib.contextmanager
def custom_environment(
    access_contents: str,
    pvlist_contents: str,
    db_contents: str = "",
    db_file: Optional[str] = test_ioc_db,
    dbd_file: Optional[str] = None,
    encoding: str = "latin-1",
):
    """
    Run a gateway and an IOC in a custom environment, specifying the raw
    contents of the access control file and the pvlist.

    Parameters
    ----------
    access_contents : str, optional
        The gateway access control configuration contents.

    pvlist_contents : str, optional
        The gateway pvlist configuration contents.

    db_contents : str, optional
        Additional database text to add to ``db_file``, if specified.

    db_file : str, optional
        Path to the IOC database.  Defaults to ``test_ioc_db``.  This is loaded
        in addition to ``db_contents``, if specified.

    dbd_file : str, optional
        Path to the IOC database definition.  Defaults to using the database
        definition provided with epics-base/softIoc.
    """
    with tempfile.NamedTemporaryFile() as access_fp:
        access_fp.write(textwrap.dedent(access_contents).encode(encoding))
        access_fp.flush()

        with tempfile.NamedTemporaryFile() as pvlist_fp:
            pvlist_fp.write(textwrap.dedent(pvlist_contents).encode(encoding))
            pvlist_fp.flush()

            with tempfile.NamedTemporaryFile() as dbfile_fp:
                if db_file is not None:
                    with open(db_file, "rt") as fp:
                        existing_db_contents = fp.read()
                    db_contents = "\n".join(
                        (existing_db_contents, textwrap.dedent(db_contents))
                    )

                dbfile_fp.write(textwrap.dedent(db_contents).encode(encoding))
                dbfile_fp.flush()

                logger.info(
                    "Access rights:\n%s",
                    textwrap.indent(access_contents, '    ')
                )
                logger.info(
                    "PVList:\n%s",
                    textwrap.indent(pvlist_contents, '    ')
                )
                with run_gateway(access=access_fp.name, pvlist=pvlist_fp.name):
                    with run_ioc(db_file=dbfile_fp.name, dbd_file=dbd_file):
                        with local_channel_access():
                            yield


def custom_environment_decorator(
    func=None,
    access_contents: str = "",
    pvlist_contents: str = "",
    db_contents: str = "",
    db_file: Optional[str] = test_ioc_db,
    dbd_file: Optional[str] = None,
):
    """
    Custom test environment, as a test function decorator.

    Parameters
    ----------
    access_contents : str, optional
        The gateway access control configuration contents.

    pvlist_contents : str, optional
        The gateway pvlist configuration contents.

    db_contents : str, optional
        Additional database text to add to ``db_file``, if specified.

    db_file : str, optional
        Path to the IOC database.  Defaults to ``test_ioc_db``.  This is loaded
        in addition to ``db_contents``, if specified.

    dbd_file : str, optional
        Path to the IOC database definition.  Defaults to using the database
        definition provided with epics-base/softIoc.
    """
    def wrapper(func):
        @functools.wraps(func)
        def wrapped(*args, **kwargs):
            with custom_environment(
                access_contents=access_contents,
                pvlist_contents=pvlist_contents,
                db_contents=db_contents,
                db_file=db_file,
                dbd_file=dbd_file,
            ):
                return func(*args, **kwargs)
        return wrapped

    if func is not None:
        return wrapper(func)

    return wrapper


class PyepicsCallback(Protocol):
    def __call__(self, pvname: str = "", value: Any = None, **kwargs) -> None:
        ...


def get_pv_pair(
    pvname: str, *,
    ioc_prefix: str = "ioc:",
    gateway_prefix: str = "gateway:",
    ioc_callback: Optional[PyepicsCallback] = None,
    gateway_callback: Optional[PyepicsCallback] = None,
    **kwargs
) -> tuple[epics.PV, epics.PV]:
    """
    Get a PV pair - a direct PV and a gateway PV.

    Parameters
    ----------
    pvname : str
        The PV name suffix, not including "ioc:" or "gateway:".

    ioc_prefix : str, optional
        The prefix to add for direct IOC communication.

    gateway_prefix : str, optional
        The prefix to add for gateway communication.

    ioc_callback : callable, optional
        A callback function to use for value updates of the IOC PV.

    gateway_callback : callable, optional
        A callback function to use for value updates of the gateway PV.

    **kwargs :
        Keyword arguments are passed to both ``epics.PV()`` instances.

    Returns
    -------
    ioc_pv : epics.PV
        The direct IOC PV.

    gateway_pv : epics.PV
        The gateway PV.
    """
    ioc_pv = epics.PV(ioc_prefix + pvname, **kwargs)
    if ioc_callback is not None:
        ioc_pv.add_callback(ioc_callback)
    ioc_pv.wait_for_connection()

    gateway_pv = epics.PV(gateway_prefix + pvname, **kwargs)
    if gateway_callback is not None:
        gateway_pv.add_callback(gateway_callback)
    gateway_pv.wait_for_connection()
    return (ioc_pv, gateway_pv)


class GatewayStats:
    """
    Gateway statistics interface.

    Instantiate and call ``.update()`` to retrieve the number of virtual
    circuits through ``.vctotal``, for example.
    """
    vctotal: Optional[int] = None
    pvtotal: Optional[int] = None
    connected: Optional[int] = None
    active: Optional[int] = None
    inactive: Optional[int] = None

    def __init__(self, prefix="gwtest:"):
        self._vctotal = epics.ca.create_channel(f"{prefix}vctotal")
        self._pvtotal = epics.ca.create_channel(f"{prefix}pvtotal")
        self._connected = epics.ca.create_channel(f"{prefix}connected")
        self._active = epics.ca.create_channel(f"{prefix}active")
        self._inactive = epics.ca.create_channel(f"{prefix}inactive")
        self.update()

    def update(self):
        """Update gateway statistics."""
        self.vctotal = epics.ca.get(self._vctotal)
        self.pvtotal = epics.ca.get(self._pvtotal)
        self.connected = epics.ca.get(self._connected)
        self.active = epics.ca.get(self._active)
        self.inactive = epics.ca.get(self._inactive)


def get_prop_support():
    """Is DBE_PROPERTY supported?"""
    events_received_ioc = 0

    def on_change_ioc(**kwargs):
        nonlocal events_received_ioc
        events_received_ioc += 1

    with standard_test_environment():
        ioc = epics.PV("ioc:passive0", auto_monitor=epics.dbr.DBE_PROPERTY)
        ioc.add_callback(on_change_ioc)
        ioc.get()

        pvhigh = epics.PV("ioc:passive0.HIGH", auto_monitor=None)
        pvhigh.put(18.0, wait=True)
        time.sleep(0.05)

    return events_received_ioc == 2


@pytest.fixture(scope="module")
def prop_supported() -> bool:
    """Is DBE_PROPERTY supported?"""
    with ProcessPoolExecutor() as exec:
        future = exec.submit(get_prop_support)

    return future.result()


def find_differences(
    struct1: dict, struct2: dict, skip_keys: Optional[list[str]] = None
) -> Generator[tuple[str, Any, Any], None, None]:
    """
    Compare two "structures" and yield keys and values which differ.

    Parameters
    ----------
    struct1 : dict
        The first structure to compare.  Pairs with the user-friendly ``desc1``
        description. This is a pyepics-provided dictionaries of information
        such as timestamp, value, alarm status, and so on.

    struct2 : dict
        The second structure to compare.  Pairs with the user-friendly
        ``desc2`` description.

    skip_keys : list of str, optional
        List of keys to skip when comparing.  Defaults to ['chid'].

    Yields
    ------
    key : str
        The key that differs.

    value1 :
        The value from struct1.

    value1 :
        The value from struct2.
    """
    if skip_keys is None:
        skip_keys = ['chid']

    for key in sorted(set(struct1).union(struct2)):
        if key not in skip_keys:
            try:
                value1 = struct1[key]
            except KeyError:
                raise RuntimeError(f"Missing key {key} in first struct")

            try:
                value2 = struct2[key]
            except KeyError:
                raise RuntimeError(f"Missing key {key} in second struct")

            if hasattr(value2, "tolist"):
                value2 = tuple(value2.tolist())
            if hasattr(value1, "tolist"):
                value1 = tuple(value1.tolist())

            try:
                if math.isnan(value1) and math.isnan(value2):
                    # nan != nan, remember?
                    continue
            except TypeError:
                ...

            if value2 != value1:
                yield key, value1, value2


def compare_structures(struct1, struct2, desc1="Gateway", desc2="IOC") -> str:
    """
    Compare two "structures" and return a human-friendly message showing the
    difference.

    Identical structures will return an empty string.

    Parameters
    ----------
    struct1 : dict
        The first structure to compare.  Pairs with the user-friendly ``desc1``
        description. This is a pyepics-provided dictionaries of information
        such as timestamp, value, alarm status, and so on.

    struct2 : dict
        The second structure to compare.  Pairs with the user-friendly
        ``desc2`` description.

    desc1 : str
        User-friendly description of ``struct1``, by default referring to
        the gateway.

    desc2 : str
        User-friendly description of ``struct2``, by default referring to
        the IOC.
    """
    differences = []
    for key, value1, value2 in find_differences(struct1, struct2):
        differences.append(
            f"Element '{key}' : {desc1} has '{value1}', but "
            f"{desc2} has '{value2}'"
        )
    return "\n\t".join(differences)


@contextlib.contextmanager
def ca_subscription(
    pvname: str,
    callback: PyepicsCallback,
    mask: int = epics.dbr.DBE_VALUE,
    form: str = "time",
    count: int = 0,
    timeout: float = 0.5,
) -> ContextManager[int]:
    """
    Create a low-level channel and subscription for a provided pvname.

    Yields channel identifier.

    Parameters
    ----------
    pvname : str
        The PV name suffix, not including "ioc:" or "gateway:".

    callback : callable
        A callback function to use for value updates.

    mask : int, optional
        The DBE mask to use for subscriptions.

    form : {"native", "time", "ctrl"}, optional
        The form to request.

    count : int, optional
        The number of elements to request.

    timeout : float, optional
        The timeout in seconds for connection.

    Yields
    ------
    channel : int
        The Channel Access client channel ID.
    """
    event_id = None
    chid = epics.ca.create_channel(pvname)
    try:
        connected = epics.ca.connect_channel(chid, timeout=timeout)
        assert connected, f"Could not connect to channel: {pvname}"

        (_, _, event_id) = epics.ca.create_subscription(
            chid,
            mask=mask,
            use_time=form == "time",
            use_ctrl=form == "ctrl",
            callback=callback,
            count=count,
        )
        yield chid
    finally:
        if event_id is not None:
            epics.ca.clear_subscription(event_id)
        epics.ca.clear_channel(chid)


@contextlib.contextmanager
def ca_subscription_pair(
    pvname: str,
    ioc_callback: PyepicsCallback,
    gateway_callback: PyepicsCallback,
    mask: int = epics.dbr.DBE_VALUE,
    form: str = "time",
    count: int = 0,
    timeout: float = 0.5,
    ioc_prefix: str = "ioc:",
    gateway_prefix: str = "gateway:",
) -> ContextManager[tuple[int, int]]:
    """
    Create low-level channels + subscriptions for IOC and gateway PVs.

    Parameters
    ----------
    pvname : str
        The PV name suffix, not including "ioc:" or "gateway:".

    ioc_callback : callable
        A callback function to use for value updates of the IOC PV.

    gateway_callback : callable
        A callback function to use for value updates of the gateway PV.

    mask : int, optional
        The DBE mask to use for subscriptions.

    form : {"native", "time", "ctrl"}, optional
        The form to request.

    count : int, optional
        The number of elements to request.

    timeout : float, optional
        The timeout in seconds for connection.

    ioc_prefix : str, optional
        The prefix to add for direct IOC communication.

    gateway_prefix : str, optional
        The prefix to add for gateway communication.

    Yields
    ------
    ioc_channel : int
        The IOC Channel Access client channel ID.

    gateway_channel : int
        The gateway Channel Access client channel ID.
    """
    with ca_subscription(
        ioc_prefix + pvname,
        ioc_callback,
        mask=mask,
        form=form,
        count=count,
        timeout=timeout,
    ) as ioc_channel:
        with ca_subscription(
            gateway_prefix + pvname,
            gateway_callback,
            mask=mask,
            form=form,
            count=count,
            timeout=timeout,
        ) as gateway_channel:
            yield ioc_channel, gateway_channel


def pyepics_caget(
    pvname: str,
    form: str = "time",
    count: int = 0,
    timeout: float = 0.5,
) -> dict[str, Any]:
    """
    Use low-level pyepics.ca to get data from a PV.

    Parameters
    ----------
    pvname : str
        The PV name.

    form : {"native", "time", "ctrl"}
        The form to request.

    count : int
        The number of elements to request.

    Returns
    -------
    data : dict
        The PV data, with keys such as "timestamp" or "value".
    """
    chid = epics.ca.create_channel(pvname)
    try:
        connected = epics.ca.connect_channel(chid, timeout=timeout)
        assert connected, f"Could not connect to channel: {pvname}"

        if form in ("time", "ctrl"):
            ftype = epics.ca.promote_type(
                chid, use_time=form == "time", use_ctrl=form == "ctrl"
            )
        elif form == "native":
            ftype = epics.ca.field_type(chid)
        else:
            raise ValueError(f"Unsupported form={form}")

        return epics.ca.get_with_metadata(chid, ftype=ftype, count=count, timeout=timeout)
    finally:
        epics.ca.clear_channel(chid)


def pyepics_caget_pair(
    pvname: str,
    form: str = "time",
    count: int = 0,
    timeout: float = 0.5,
    ioc_prefix: str = "ioc:",
    gateway_prefix: str = "gateway:",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Use low-level pyepics.ca to get data from a direct PV and a gateway PV.

    Parameters
    ----------
    pvname : str
        The PV name suffix, not including "ioc:" or "gateway:".

    form : {"native", "time", "ctrl"}
        The form to request.

    count : int
        The number of elements to request.

    ioc_prefix : str, optional
        The prefix to add for direct IOC communication.

    gateway_prefix : str, optional
        The prefix to add for gateway communication.

    Returns
    -------
    ioc_data : dict
        The direct IOC PV data.

    gateway_data : dict
        The gateway PV data.
    """
    return (
        pyepics_caget(
            pvname=ioc_prefix + pvname,
            form=form,
            count=count,
            timeout=timeout,
        ),
        pyepics_caget(
            pvname=gateway_prefix + pvname,
            form=form,
            count=count,
            timeout=timeout,
        ),
    )
