"""Validation helpers for typed gateway scalar values."""

from .const import UINT_MAX
from .models import WanStatus

_CONNECTED_WAN_STATUSES = frozenset({"connected", "online", "up"})
_DISCONNECTED_WAN_STATUSES = frozenset(
    {
        "disconnected",
        "dormant",
        "down",
        "error",
        "lowerlayerdown",
        "notpresent",
        "offline",
    }
)


def _parse_nonnegative_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Invalid {name}: {value!r}")
    return value


def _parse_uptime(value: object) -> int:
    return _parse_nonnegative_integer(value, "uptime")


def _parse_dsl_rate(value: object) -> int | None:
    rate = _parse_nonnegative_integer(value, "DSL current rate")
    if rate > UINT_MAX:
        raise ValueError(f"Invalid DSL current rate: {value!r}")
    return None if rate == UINT_MAX else rate


def _parse_wan_status(value: object) -> WanStatus:
    if not isinstance(value, str):
        raise ValueError(f"Invalid WAN status: {value!r}")

    normalized = "".join(character for character in value.casefold() if character.isalnum())
    connected: bool | None = None
    if normalized in _CONNECTED_WAN_STATUSES:
        connected = True
    elif normalized in _DISCONNECTED_WAN_STATUSES:
        connected = False

    return WanStatus(raw_status=value, connected=connected)
