pcds-gateway-tests
==================

Collection of tools to perform PCDS-specific gateway testing.


tests/
======

For starters, a pytest conversion of [ca-gateway
tests](https://github.com/slac-epics/ca-gateway/tree/R2.1.2.0-1.branch/testTop/pyTestsApp)


Test Requirements
-----------------

* pytest
* pytest-xdist (*)


(*) This is important to run each test in a separate process.  pyepics does
not handle ``epics.PV`` and context clearing well, so you may get segfaults
otherwise.

Individual fixtures that use ``epics`` to determine support of gateway features
should be done carefully by performing their task in a separate process to
avoid interfering with the test suite (see ``conftest.prop_supported`` for an
example).
