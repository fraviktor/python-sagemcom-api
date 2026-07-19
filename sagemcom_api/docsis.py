"""Validation helpers for DOCSIS channel collections."""

from collections.abc import Callable, Mapping
from math import isfinite
from typing import Protocol, TypeVar, cast

from .models import DocsisDownstreamChannel, DocsisUpstreamChannel


def _required_integer(item: Mapping[str, object], field: str) -> int:
    value = item.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Invalid DOCSIS {field}: {value!r}")
    return value


def _required_boolean(item: Mapping[str, object], field: str) -> bool:
    value = item.get(field)
    if not isinstance(value, bool):
        raise ValueError(f"Invalid DOCSIS {field}: {value!r}")
    return value


def _optional_integer(item: Mapping[str, object], field: str) -> int | None:
    if field not in item or item[field] is None:
        return None
    return _required_integer(item, field)


def _optional_float(item: Mapping[str, object], field: str) -> float | None:
    if field not in item or item[field] is None:
        return None
    value = item[field]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Invalid DOCSIS {field}: {value!r}")
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError(f"Invalid DOCSIS {field}: {value!r}")
    return normalized


def _optional_string(item: Mapping[str, object], field: str) -> str | None:
    if field not in item or item[field] is None:
        return None
    value = item[field]
    if not isinstance(value, str):
        raise ValueError(f"Invalid DOCSIS {field}: {value!r}")
    return value.strip() or None


def _parse_downstream(item: Mapping[str, object]) -> DocsisDownstreamChannel:
    snr_field = "SNR" if "SNR" in item else "snr"
    return DocsisDownstreamChannel(
        uid=_required_integer(item, "uid"),
        channel_id=_required_integer(item, "channel_id"),
        lock_status=_required_boolean(item, "lock_status"),
        frequency=_optional_float(item, "frequency"),
        bandwidth=_optional_integer(item, "band_width"),
        symbol_rate=_optional_integer(item, "symbol_rate"),
        modulation=_optional_string(item, "modulation"),
        snr=_optional_float(item, snr_field),
        power_level=_optional_float(item, "power_level"),
        unerrored_codewords=_optional_integer(item, "unerrored_codewords"),
        correctable_codewords=_optional_integer(item, "correctable_codewords"),
        uncorrectable_codewords=_optional_integer(item, "uncorrectable_codewords"),
    )


def _parse_upstream(item: Mapping[str, object]) -> DocsisUpstreamChannel:
    return DocsisUpstreamChannel(
        uid=_required_integer(item, "uid"),
        channel_id=_required_integer(item, "channel_id"),
        lock_status=_required_boolean(item, "lock_status"),
        frequency=_optional_float(item, "frequency"),
        symbol_rate=_optional_integer(item, "symbol_rate"),
        modulation=_optional_string(item, "modulation"),
        power_level=_optional_float(item, "power_level"),
        frequency31=_optional_string(item, "frequency31"),
        modulation31=_optional_string(item, "modulation31"),
        profile_id31=_optional_string(item, "profile_id31"),
    )


class _Channel(Protocol):
    @property
    def uid(self) -> int:
        """Return the channel's internal identity."""
        ...


_ChannelT = TypeVar("_ChannelT", bound=_Channel)


def _parse_collection(
    value: object,
    parser: Callable[[Mapping[str, object]], _ChannelT],
) -> list[_ChannelT]:
    if not isinstance(value, list):
        raise ValueError(f"Invalid DOCSIS collection: {type(value).__name__}")

    channels: list[_ChannelT] = []
    seen_uids: set[int] = set()
    for item in value:
        if not isinstance(item, Mapping):
            continue
        try:
            channel = parser(cast(Mapping[str, object], item))
        except ValueError:
            continue
        if channel.uid in seen_uids:
            raise ValueError(f"Duplicate DOCSIS channel uid: {channel.uid}")
        seen_uids.add(channel.uid)
        channels.append(channel)

    if value and not channels:
        raise ValueError("DOCSIS collection contains no valid channels")
    return channels


def _parse_downstream_channels(value: object) -> list[DocsisDownstreamChannel]:
    """Validate a downstream collection while skipping malformed siblings."""
    return _parse_collection(value, _parse_downstream)


def _parse_upstream_channels(value: object) -> list[DocsisUpstreamChannel]:
    """Validate an upstream collection while skipping malformed siblings."""
    return _parse_collection(value, _parse_upstream)
