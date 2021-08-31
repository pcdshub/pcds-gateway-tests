import functools
import logging
import time

import pytest
from epics import dbr

from .. import conftest

logger = logging.getLogger(__name__)

masks = pytest.mark.parametrize(
    "mask",
    [
        pytest.param(dbr.DBE_VALUE, id="DBE_VALUE"),
        pytest.param(dbr.DBE_LOG, id="DBE_LOG"),
        pytest.param(dbr.DBE_ALARM, id="DBE_ALARM"),
        pytest.param(dbr.DBE_PROPERTY, id="DBE_PROPERTY"),
        pytest.param(dbr.DBE_VALUE | dbr.DBE_PROPERTY, id="DBE_VALUE|DBE_PROPERTY"),
        pytest.param(dbr.DBE_VALUE | dbr.DBE_LOG, id="DBE_VALUE|DBE_LOG"),
        pytest.param(dbr.DBE_VALUE | dbr.DBE_ALARM, id="DBE_VALUE|DBE_ALARM"),
    ]
)

forms = pytest.mark.parametrize(
    "form",
    [
        "ctrl",
        "time",
    ]
)


@pytest.mark.parametrize(
    "pvname",
    [
        "HUGO:AI",
        "HUGO:ENUM",
        "auto",
        "auto:cnt",
        "enumtest",
        "gwcachetest",
        "passive0",
        "passiveADEL",
        "passiveADELALRM",
        "passiveALRM",
        "passiveMBBI",
        "passivelongin",
        "bigpassivewaveform",
        # "fillingaai",
        # "fillingaao",
        # "fillingcompress",
        # "fillingwaveform",
        # "passivewaveform",
    ]
)
@masks
@forms
@conftest.standard_test_environment_decorator
def test_subscription_on_connection(pvname: str, mask: int, form: str):
    """
    Basic subscription test.

    For the provided pv name, mask, and form (ctrl/time), do we receive the same
    subscription updates on connection to the gateway/IOC?
    """
    gateway_events = []
    ioc_events = []

    def on_change(event_list, pvname=None, chid=None, **kwargs):
        event_list.append(kwargs)

    with conftest.ca_subscription_pair(
        pvname,
        ioc_callback=functools.partial(on_change, ioc_events),
        gateway_callback=functools.partial(on_change, gateway_events),
        form=form,
        mask=mask,
    ):
        time.sleep(0.1)

    compare_subscription_events(
        gateway_events, ioc_events,
        strict=False
    )


def compare_subscription_events(
    gateway_events: list[dict],
    ioc_events: list[dict],
    strict: bool = True,
):
    """
    Compare subscription events.
    """
    for gateway_event, ioc_event in zip(gateway_events, ioc_events):
        # assert gateway_event == ioc_event
        differences = conftest.compare_structures(gateway_event, ioc_event)
        if differences:
            raise RuntimeError(f"Differences in events:\n{differences}")

    if len(gateway_events) == 2 and len(ioc_events) == 1:
        differences = conftest.compare_structures(
            gateway_events[0], gateway_events[1],
            desc1="event 0", desc2="event 1",
        )
        if differences:
            raise RuntimeError(f"Differences in events:\n{differences}")

        if strict:
            raise RuntimeError("Duplicate initial event received")

        logger.warning(
            "Partial passed test - gateway behaves slightly differently.  "
            "Gateway duplicates initial subscription callback for this mask."
        )
        return

    assert len(gateway_events) == len(ioc_events), (
        f"Gateway events = {len(gateway_events)}, "
        f"but IOC events = {len(ioc_events)}."
    )
