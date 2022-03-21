pcds-gateway-tests
==================

Collection of tools to perform PCDS-specific gateway testing.


tests/
======

For starters, a pytest conversion of [ca-gateway
tests](https://github.com/slac-epics/ca-gateway/tree/R2.1.2.0-1.branch/testTop/pyTestsApp)

These tests are called the "process" tests in this repository and are located
in ``gateway_tests/process/``.  Tests which are tied to PCDS's production
configuration are referred to as "prod config" tests and are located in
``gateway_tests/prod_config``.

Test Requirements
-----------------

* Python 3.9+ (type annotations will fail on earlier versions)
* [caproto](https://github.com/caproto/caproto)
* [numpy](https://numpy.org/)
* [pyepics](https://github.com/pyepics/pyepics)
* [pytest-xdist](https://github.com/pytest-dev/pytest-xdist) (*)
* [pytest](https://github.com/pytest-dev/pytest)

For production configuration tests, the following dependencies are also
required:

* [apischema](https://github.com/wyfo/apischema/)
* [whatrecord](https://github.com/pcdshub/whatrecord/)

(*) This is important to run each test in a separate process.  pyepics does
not handle ``epics.PV`` and context clearing well, so you may get segfaults
otherwise.

Individual fixtures that use ``epics`` to determine support of gateway features
should be done carefully by performing their task in a separate process to
avoid interfering with the test suite (see ``conftest.prop_supported`` for an
example).

Test environment
----------------

Tests can be run from the latest PCDS Python environment.  To use it, source
the following script with bash:

```bash
$ source /cds/group/pcds/pyps/conda/pcds_conda
```

For more information, see
https://confluence.slac.stanford.edu/display/PCDS/PCDS+Conda+Python+Environments

Process tests
-------------

To run just the process tests, ensure the Python environment contains the
minimum requirements.

This should work as-is:

```bash
$ make process-tests PYTEST_OPTIONS=""
```

Or customize the gateway process/host arch you are testing with environment
settings and ``PYTEST_OPTIONS``:

```bash
$ export EPICS_HOST_ARCH=rhel7-x86_64
$ export GATEWAY_ROOT=/cds/group/pcds/epics/extensions/gateway/R2.1.2.0-1.2.0/
$ make process-tests PYTEST_OPTIONS="-k simple"
* Running gateway process tests with options: -k simple
GATEWAY_ROOT=/cds/group/pcds/epics/extensions/gateway/R2.1.2.0-1.2.0/ \
                pytest -v --forked gateway_tests/process \
                                -k simple
```

You can also just use ``pytest`` directly, as indicated by the ``make`` output
above.  Just be sure you use ``--forked`` mode when running more than one
test.  The test suite will fail all subsequent tests after the first one
otherwise.  This is largely due to working around pyepics's flimsy support
for clearing and creating new CA contexts and not something we really have
control over.


Included process tests
----------------------

* ``CS studio``: VALUE|ALARM with time structure, PROPERTY with control
  structure
* ``DBE_ALARM``: alarm severity transitions are accurate
* ``DBE_LOG``: archive deadband settings respected
* ``DBE_PROPERTY``: HIHI/LOLO/HI/LO changes result in monitor events
* ``DBE_VALUE``: simply ensure monitors are consistent
* ``enum_property_cache``: PV property cache for enum data (2 xfails; did not
  dig into details); stale enum data check (passes)
* ``enum_undefined_timestamp``: SLAC-reported timestamp issue of undefined
  timestamps for enum PVs.
* ``property_cache``: EGU, limit, etc. updated and then verified valid using a
  CTRL request
* ``structures``: CTRL metadata identical in monitor events
* ``waveform_with_max_ca_array_bytes``: gateway segfault check when IOC
  ``EPICS_CA_MAX_ARRAY_BYTES`` is set too low

Additional SLAC-created tests:

* ``enum_undefined_timestamp``: SLAC-reported timestamp issue of undefined
  timestamps for enum PVs now easily reproduces the issue. Additional test for
  this lingering issue.
* ``subscriptions``: verify subscription metadata for the matrix of settings
  below, upon connection and after performing a number of caputs
  * ``DBE_{VALUE,LOG,ALARM,PROPERTY}`` (and a mix thereof) CTRL and TIME types
  * Records used in the test suite
* ``permissions``: validate that access security groups work as expected
  * Allow by host/user (*), deny by specific IP (DENY FROM), blanket deny
* ``logging``: verify caPutLog behavior
  * For provided records, perform a caput and verify the log output is valid.
    Similarly, check the TCP output

Included production configuration tests
---------------------------------------

New production tests

* Base a new test suite on our production PCDS configuration
* Gather data from whatrecord
  * Python-parsed gateway configuration (.pvlist) and access security (.acf)
    happi database device mapping to PVs
* Add in pertinent test suite information
  * Map PV to IOC -> IOC to host -> host to subnet
  * Per gateway-host interface information
* With all of the above, run on a gateway host to check
   * Access rights are correct according to the configuration
   * PV metadata is accurate from the gateway versus the IOC
* Produce human-readable results of any discrepancies

Notes on tests
--------------

* ``test_undefined_timestamp`` does not sufficiently trigger the issue it
  intends to.  It needs revisiting.
* For the process tests, each test spawns its own gateway instance and its own
  IOC instance.
* The default test database has a prefix of ``ioc:``, but tests may communicate
  to the same PV through the gateway instance by swapping that prefix for
  ``gateway:``.  This is a fundamental pattern reused in many tests here.
  The gateway configurations (``gateway_tests/process/pvlist*.txt``) include
  this alias rule which does this: ``gateway:\(.*\)  ALIAS ioc:\1``.
* PCRE and BRE pvlist configurations for the gateway are available and may be
  configured by way of the ``GATEWAY_PVLIST`` environment variable.
* The gateway process and the IOC process work on different
  ``EPICS_CA_SERVER_PORT`` settings, making communicating with one or the other
  a matter of environment variable configuration.
* Though we use pytest-xdist, the port configuration here does not allow for
  parallel testing, so do not use ``-n`` values of ``>= 2``.

https://confluence.slac.stanford.edu/display/PCDS/Gateway+testing+by+way+of+pcds-gateway-tests
