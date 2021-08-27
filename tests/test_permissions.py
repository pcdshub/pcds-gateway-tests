#!/usr/bin/env python
import dataclasses
import logging
import textwrap
from typing import Optional

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


# Keep the header with regex rules separate; \\ is a pain to deal with in
# strings.
pvlist_header = r"""
EVALUATION ORDER ALLOW, DENY
gateway:\(.*\)  ALIAS ioc:\1
ioc:.*          DENY
gwtest:.*       ALLOW
"""

pvlist_footer = r"""
"""


def with_pvlist_header(pvlist_rules: str) -> str:
    """Add on the 'standard' pvlist header to the provided rules."""
    return "\n".join((pvlist_header, textwrap.dedent(pvlist_rules), pvlist_footer))


@dataclasses.dataclass
class AccessCheck:
    hostname: str
    pvname: str
    access: str
    username: Optional[str] = None


try:
    with open(conftest.site_access, "rt") as fp:
        full_access_rights = fp.read()
except FileNotFoundError:
    full_access_rights = None


def check_permissions(
    access_contents: str, pvlist_contents: str, access_checks: list[AccessCheck]
):
    pvlist_contents = with_pvlist_header(pvlist_contents)
    with conftest.custom_environment(access_contents, pvlist_contents):
        for access_check in access_checks:
            result = util.caget_from_host(
                access_check.hostname, access_check.pvname,
                username=access_check.username
            )
            assert access_check.access == result.access, str(access_check)


@have_requirements
@pytest.mark.parametrize(
    "access_contents",
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
            id="minimal",
        ),
        pytest.param(
            full_access_rights,
            id="full",
            marks=pytest.mark.skipif(
                not full_access_rights, reason="Full access rights file missing?"
            )
        ),
    ]
)
@pytest.mark.parametrize(
    "pvlist_contents, access_checks",
    [
        pytest.param(
            """
            gateway:HUGO:ENUM  ALIAS ioc:HUGO:ENUM RWMFX
            gateway:HUGO:AI    ALIAS ioc:HUGO:AI DEFAULT
            """,
            [
                AccessCheck("mfx-control", "gateway:HUGO:ENUM", "WRITE|READ"),
                AccessCheck("mfx-console", "gateway:HUGO:ENUM", "WRITE|READ"),
                AccessCheck("anyhost", "gateway:HUGO:ENUM", "READ"),
                AccessCheck("mfx-control", "gateway:HUGO:AI", "READ"),
                AccessCheck("mfx-console", "gateway:HUGO:AI", "READ"),
                AccessCheck("anyhost", "gateway:HUGO:AI", "READ"),
            ],
            id="test"
        ),
    ],
)
def test_permissions_by_host(
    access_contents: str, pvlist_contents: str, access_checks: list[AccessCheck]
):
    check_permissions(access_contents, pvlist_contents, access_checks)


@have_requirements
@pytest.mark.parametrize(
    "access_contents",
    [
        pytest.param(
            """\
            UAG(testusers) {usera,userb}
            ASG(DEFAULT) {
                RULE(1,READ)
            }

            ASG(RWTESTUSERS) {
                RULE(1,READ)
                RULE(1,WRITE,TRAPWRITE){
                  UAG(testusers)
                }
            }
            """,
            id="minimal",
        ),
    ]
)
@pytest.mark.parametrize(
    "pvlist_contents, access_checks",
    [
        pytest.param(
            """
            gateway:HUGO:ENUM  ALIAS ioc:HUGO:ENUM RWTESTUSERS
            gateway:HUGO:AI    ALIAS ioc:HUGO:AI DEFAULT
            """,
            [
                AccessCheck("mfx-control", "gateway:HUGO:ENUM", "WRITE|READ", username="usera"),
                AccessCheck("mfx-console", "gateway:HUGO:ENUM", "READ", username="userc"),
                AccessCheck("anyhost", "gateway:HUGO:ENUM", "WRITE|READ", username="userb"),
                AccessCheck("mfx-control", "gateway:HUGO:AI", "READ", username="userc"),
                AccessCheck("mfx-console", "gateway:HUGO:AI", "READ", username="usera"),
                AccessCheck("anyhost", "gateway:HUGO:AI", "READ", username="usera"),
            ],
            id="test"
        ),
    ],
)
def test_permissions_by_user(
    access_contents: str, pvlist_contents: str, access_checks: list[AccessCheck]
):
    check_permissions(access_contents, pvlist_contents, access_checks)
