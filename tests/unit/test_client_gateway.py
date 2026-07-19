"""Tests for typed gateway scalar reads."""

import copy
import json
from unittest.mock import AsyncMock

import pytest

from sagemcom_api.client import SagemcomClient
from sagemcom_api.enums import EncryptionMethod
from sagemcom_api.exceptions import AccessRestrictionException, UnknownPathException
from sagemcom_api.models import WanStatus


def _client_for_response(mock_session_factory, response):
    session = mock_session_factory([response])
    client = SagemcomClient(
        host="192.168.1.1",
        username="admin",
        password="admin",
        authentication_method=EncryptionMethod.MD5,
        session=session,
    )
    return client, session


def _set_response_value(response, value):
    response["reply"]["actions"][0]["callbacks"][0]["parameters"]["value"] = value


def _assert_single_get_action(session, xpath):
    request = json.loads(session.post.call_args.kwargs["data"]["req"])
    assert request["request"]["actions"] == [
        {
            "id": 0,
            "method": "getValue",
            "xpath": xpath,
            "options": {},
        }
    ]


@pytest.mark.asyncio
async def test_get_uptime(mock_session_factory, uptime_response):
    """Test uptime is returned as a validated integer from one action."""
    client, session = _client_for_response(mock_session_factory, uptime_response)

    assert await client.get_uptime() == 3600
    _assert_single_get_action(session, "Device/DeviceInfo/UpTime")


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [True, -1, 1.5, "3600", None])
async def test_get_uptime_rejects_malformed_value(mock_session_factory, uptime_response, value):
    """Test uptime rejects booleans, negative values, and coercion."""
    response = copy.deepcopy(uptime_response)
    _set_response_value(response, value)
    client, _ = _client_for_response(mock_session_factory, response)

    with pytest.raises(ValueError, match="Invalid uptime"):
        await client.get_uptime()


@pytest.mark.asyncio
async def test_get_uptime_accepts_zero(mock_session_factory, uptime_response):
    """Test zero uptime remains valid immediately after startup."""
    response = copy.deepcopy(uptime_response)
    _set_response_value(response, 0)
    client, _ = _client_for_response(mock_session_factory, response)

    assert await client.get_uptime() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_status", "connected"),
    [
        ("connected", True),
        ("ONLINE", True),
        (" Up ", True),
        ("disconnected", False),
        ("Dormant", False),
        ("down", False),
        ("error", False),
        ("Lower-Layer Down", False),
        ("NotPresent", False),
        ("offline", False),
        ("initializing", None),
        ("vendor-specific", None),
        ("", None),
        ("   ", None),
    ],
)
async def test_get_wan_status_normalizes_known_values(mock_session_factory, wan_status_response, raw_status, connected):
    """Test WAN status preserves raw text and normalizes connectivity."""
    response = copy.deepcopy(wan_status_response)
    _set_response_value(response, raw_status)
    client, _ = _client_for_response(mock_session_factory, response)

    assert await client.get_wan_status() == WanStatus(raw_status=raw_status, connected=connected)


@pytest.mark.asyncio
async def test_get_wan_status_uses_one_action(mock_session_factory, wan_status_response):
    """Test the WAN helper reads only the confirmed interface path."""
    client, session = _client_for_response(mock_session_factory, wan_status_response)

    await client.get_wan_status()

    _assert_single_get_action(session, "Device/IP/Interfaces/Interface[Alias='IP_DATA']/Status")


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, True, 1, {}])
async def test_get_wan_status_rejects_non_string(mock_session_factory, wan_status_response, value):
    """Test malformed WAN values are not reported as disconnected."""
    response = copy.deepcopy(wan_status_response)
    _set_response_value(response, value)
    client, _ = _client_for_response(mock_session_factory, response)

    with pytest.raises(ValueError, match="Invalid WAN status"):
        await client.get_wan_status()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "xpath"),
    [
        ("get_dsl_downstream_rate", "Device/DSL/Channels/Channel[@uid='1']/DownstreamCurrRate"),
        ("get_dsl_upstream_rate", "Device/DSL/Channels/Channel[@uid='1']/UpstreamCurrRate"),
    ],
)
async def test_get_dsl_rate(mock_session_factory, dsl_rate_response, method_name, xpath):
    """Test each DSL current-rate helper performs one independent action."""
    client, session = _client_for_response(mock_session_factory, dsl_rate_response)

    assert await getattr(client, method_name)() == 100000
    _assert_single_get_action(session, xpath)


@pytest.mark.asyncio
@pytest.mark.parametrize(("value", "expected"), [(4294967295, None), (0, 0)])
async def test_get_dsl_rate_handles_sentinel_and_zero(mock_session_factory, dsl_rate_response, value, expected):
    """Test unavailable sentinel and a real zero rate remain distinct."""
    response = copy.deepcopy(dsl_rate_response)
    _set_response_value(response, value)
    client, _ = _client_for_response(mock_session_factory, response)

    assert await client.get_dsl_downstream_rate() == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [True, -1, 1.5, "100000", None, 4294967296])
async def test_get_dsl_rate_rejects_malformed_value(mock_session_factory, dsl_rate_response, value):
    """Test DSL rates reject booleans, negative values, and coercion."""
    response = copy.deepcopy(dsl_rate_response)
    _set_response_value(response, value)
    client, _ = _client_for_response(mock_session_factory, response)

    with pytest.raises(ValueError, match="Invalid DSL current rate"):
        await client.get_dsl_downstream_rate()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "exception"),
    [
        ("get_uptime", UnknownPathException()),
        ("get_wan_status", AccessRestrictionException()),
    ],
)
async def test_gateway_scalar_reads_propagate_typed_path_errors(
    mock_session_factory,
    uptime_response,
    method_name,
    exception,
):
    """Test unsupported and restricted paths remain distinct typed failures."""
    client, _ = _client_for_response(mock_session_factory, uptime_response)
    client._get_raw_value_by_xpath = AsyncMock(side_effect=exception)

    with pytest.raises(type(exception)):
        await getattr(client, method_name)()
