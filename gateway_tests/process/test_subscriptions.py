import copy
import functools
import logging
import math
import time
from typing import Any

import pytest
from epics import ca, dbr

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

value_masks = pytest.mark.parametrize(
    "mask",
    [
        pytest.param(dbr.DBE_VALUE, id="DBE_VALUE"),
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
        # "auto",      # <-- updates based on auto:cnt
        # "auto:cnt",  # <-- updates periodically
        "enumtest",
        "gwcachetest",
        "passive0",
        "passiveADEL",
        "passiveADELALRM",
        "passiveALRM",
        "passiveMBBI",
        "passivelongin",
        "bigpassivewaveform",
        "fillingaai",
        "fillingaao",
        "fillingcompress",
        "fillingwaveform",
        "passivewaveform",
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
        event_list.append(copy.deepcopy(kwargs))

    with conftest.ca_subscription_pair(
        pvname,
        ioc_callback=functools.partial(on_change, ioc_events),
        gateway_callback=functools.partial(on_change, gateway_events),
        form=form,
        mask=mask,
    ):
        time.sleep(0.1)

    compare_subscription_events(
        gateway_events,
        form,
        ioc_events,
        strict=False,
    )


def compare_subscription_events(
    gateway_events: list[dict],
    form: str,
    ioc_events: list[dict],
    strict: bool = True,
):
    """
    Compare subscription events.
    """
    for event_idx, (gateway_event, ioc_event) in enumerate(
        zip(gateway_events, ioc_events), 1
    ):
        # assert gateway_event == ioc_event
        if form == "ctrl":
            # Ignore timestamp for control events, if it made its way into the
            # dictionary somehow.
            gateway_event = dict(gateway_event)
            ioc_event = dict(ioc_event)
            gateway_event.pop("timestamp", None)
            ioc_event.pop("timestamp", None)

        differences = conftest.compare_structures(gateway_event, ioc_event)
        if differences:
            raise RuntimeError(
                f"Differences in event {event_idx} of {len(ioc_events)}:\n"
                f"{differences}"
            )
        logger.info(
            "Event %d is identical, with value=%s timestamp=%s",
            event_idx,
            gateway_event.get("value"),
            gateway_event.get("timestamp")
        )

    if len(gateway_events) == 2 and len(ioc_events) == 1:
        differences = conftest.compare_structures(
            gateway_events[0], gateway_events[1],
            desc1="event 0", desc2="event 1",
        )
        if not differences:
            if strict:
                raise RuntimeError("Duplicate initial event received")

            logger.warning(
                "Partial passed test - gateway behaves slightly differently.  "
                "Gateway duplicates initial subscription callback for this mask."
            )
            return

        if all(
            isinstance(value1, (int, float))
            and math.isnan(value1)
            and value2 == 0.0
            for key, value1, value2 in conftest.find_differences(
                gateway_events[0], gateway_events[1]
            )
        ):
            if strict:
                raise RuntimeError(f"NaN event and then 0.0 event:\n{differences}")
                return

            logger.warning(
                "Partial passed test - gateway behaves slightly differently.  "
                "Gateway duplicated sub callback with NaN then 0.0 for some "
                "values."
            )
            return
        else:
            raise RuntimeError(f"Differences in events:\n{differences}")

    assert len(gateway_events) == len(ioc_events), (
        f"Gateway events = {len(gateway_events)}, "
        f"but IOC events = {len(ioc_events)}."
    )


@pytest.mark.parametrize(
    "pvname, values",
    [
        pytest.param("HUGO:AI", [0.2, 1.2]),
        pytest.param("HUGO:ENUM", [1, 2]),
        pytest.param("enumtest", [1, 2]),
        pytest.param("gwcachetest", [-20, 0, 20]),
        pytest.param("passive0", [1, 21]),
        pytest.param("passiveADEL", [1, 20]),
        pytest.param("passiveADELALRM", [1, 20]),
        pytest.param("passiveALRM", [1, 5, 10]),
        pytest.param("passiveMBBI", [1, 2]),
        pytest.param("passivelongin", [1, 2]),
        pytest.param("bigpassivewaveform", [[1, 2, 3], [4, 5, 6]]),
        # pytest.param("fillingaai", []),
        # pytest.param("fillingaao", []),
        # pytest.param("fillingcompress", []),
        # pytest.param("fillingwaveform", []),
        # pytest.param("passivewaveform", []),
    ]
)
@forms
@value_masks
@conftest.standard_test_environment_decorator
def test_subscription_with_put(pvname: str, mask: int, form: str, values: list[Any]):
    """
    Putting a value to the IOC and compare subscription events.

    For the provided pv name, mask, and form (ctrl/time), do we receive the same
    subscription updates after putting values to the IOC?
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
    ) as (ioc_ch, gateway_ch):
        _wait_event(gateway_events, ioc_events, count=1, timeout=0.2)
        # Throw away initial events; we care what happens from now on
        del gateway_events[:]
        del ioc_events[:]
        for value in values:
            ca.put(ioc_ch, value)
            _wait_event(gateway_events, ioc_events)
        time.sleep(0.1)

    compare_subscription_events(
        gateway_events,
        form,
        ioc_events,
        strict=True,
    )


def _wait_event(*lists: list[dict], count: int = 1, timeout: float = 0.1):
    """
    Wait for each list to get an updated event.
    """
    end_time = time.time() + timeout
    waiting_for = tuple(len(lst) + count for lst in lists)
    while time.time() < end_time:
        lengths = tuple(len(lst) for lst in lists)
        if lengths == waiting_for:
            break
    return lengths
