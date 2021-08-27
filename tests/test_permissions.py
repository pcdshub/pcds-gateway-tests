#!/usr/bin/env python
import logging

import conftest
import pytest

try:
    import util
except ImportError as ex:
    have_requirements = pytest.mark.skip(reason=f"Missing dependencies: {ex}")
else:
    def have_requirements(func):
        return func


logger = logging.getLogger(__name__)


@have_requirements
@pytest.mark.parametrize(
    "access_contents, pvlist_contents",
    [
        pytest.param(
            """\
            HAG(mfxhosts) {mfx-control,mfx-console}
            ASG(DEFAULT) {
                RULE(1,READ)
            }

            ASG(RWMFX) {
                RULE(1,READ)
                RULE(1,WRITE,TRAPWRITE){
                  HAG(mfxhosts)
                }
            }
            """,
            """\
            EVALUATION ORDER ALLOW, DENY
            .*HUGO:ENUM ALLOW RWMFX
            .*HUGO:AI ALLOW DEFAULT
            """,
            id="initial_test"
        )
    ]
)
def test_permissions_by_host(access_contents, pvlist_contents):
    with conftest.custom_environment(access_contents, pvlist_contents):
        for host in ["mfx-control", "mfx-console", "psbuild-rhel7"]:
            logger.error("from %s %s", host, util.caget_from_host(host, "ioc:HUGO:ENUM"))
            logger.error("from %s %s", host, util.caget_from_host(host, "ioc:HUGO:AI"))
