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

* Python 3.8+
* pytest
* pytest-xdist (*)
* [pyepics](https://github.com/pyepics/pyepics)
* [caproto](https://github.com/caproto/caproto)

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


Notes on tests
--------------

* ``test_undefined_timestamp`` does not sufficiently trigger the issue it
  intends to.  It needs revisiting.
