"""Pure validation of possible Ariston thermostat/DHW commands.

NOT wired to the API or to Home Assistant service calls. This module is
an audited staging area for future opt-in writes, not a control mechanism.
"""

from __future__ import annotations

import math
from typing import Any

from .model import as_temperature
from .states import enum_code


class CommandRejected(ValueError):
    """Cannot safely construct a command using the available cloud snapshot."""


# Zone must be explicitly pinned, rather than inferred from a parsed string.
_ALLOWED_SETPOINTS: dict[str, tuple[int, float, float]] = {
    "ZoneDesiredTemp": (1, 10.0, 30.0),
    "ZoneComfortTemp": (1, 10.0, 30.0),
    "ZoneEconomyTemp": (1, 10.0, 30.0),
    "DhwTemp": (0, 35.0, 65.0),
    "DhwTimeProgComfortTemp": (0, 35.0, 65.0),
    "DhwTimeProgEconomyTemp": (0, 35.0, 65.0),
}


def build_setpoint_request(
    snapshot: dict[str, dict[str, Any]],
    features: dict[str, Any],
    item_id: str,
    new_value: float,
) -> dict[str, Any] | None:
    """Build the /dataItems/<plant>/set JSON body with strict safety guards.

    The server's min/max are mandatory; local hard caps are a second guard.
    The old value comes exclusively from a fresh authenticated read.
    Unchanged requests return None instead of generating a duplicate POST.
    """
    if item_id not in _ALLOWED_SETPOINTS:
        raise CommandRejected("This cloud property cannot be modified")
    zone, hard_min, hard_max = _ALLOWED_SETPOINTS[item_id]
    if not isinstance(features, dict) or not features:
        raise CommandRejected("Cloud device features have not been read")
    record = snapshot.get(item_id)
    if not isinstance(record, dict):
        raise CommandRejected("The target property is not present")
    old_value = as_temperature(record)
    if old_value is None:
        raise CommandRejected("No valid previous value for cloud compare-and-set")
    if isinstance(new_value, bool):
        raise CommandRejected("Boolean is not a temperature")
    try:
        new = float(new_value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CommandRejected("Invalid temperature") from exc
    if not math.isfinite(new):
        raise CommandRejected("Temperature must be finite")

    # Never invent device-specific limits: reject absent or invalid metadata.
    lower = record.get("min")
    upper = record.get("max")
    if lower is None or upper is None or isinstance(lower, bool) or isinstance(upper, bool):
        raise CommandRejected("Device temperature limits are unavailable")
    try:
        lower, upper = float(lower), float(upper)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CommandRejected("Invalid device temperature limits") from exc
    if not all(math.isfinite(value) for value in (lower, upper)) or lower >= upper:
        raise CommandRejected("Invalid device temperature limits")
    if not max(hard_min, lower) <= new <= min(hard_max, upper):
        raise CommandRejected("Temperature outside validated device limits")
    if old_value == new:
        return None

    step = record.get("step")
    if step is not None:
        if isinstance(step, bool):
            raise CommandRejected("Invalid device step")
        try:
            resolution = float(step)
        except (ValueError, TypeError, OverflowError) as exc:
            raise CommandRejected("Invalid device step") from exc
        if not math.isfinite(resolution) or resolution <= 0:
            raise CommandRejected("Invalid device step")
        multiple = (new - lower) / resolution
        if abs(multiple - round(multiple)) > 1e-5:
            raise CommandRejected("Requested temperature is not on a supported step")

    # A manual target is not meaningful while Cube S follows its own weekly
    # program; schedule overrides need separate, explicitly verified logic.
    if item_id == "ZoneDesiredTemp":
        if enum_code(snapshot.get("ZoneMode")) != 2:
            raise CommandRejected("Manual heating mode is required")
        if enum_code(snapshot.get("PlantMode")) not in (1, 2):
            raise CommandRejected("The plant is not in a heating mode")

    return {
        "items": [{
            "id": item_id, "zone": zone,
            "prevValue": old_value, "value": new,
        }],
        "features": features,
    }
