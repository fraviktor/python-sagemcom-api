"""Tests for typed DOCSIS channel collection reads."""

import copy
import json
from unittest.mock import AsyncMock

import pytest

from sagemcom_api.client import SagemcomClient
from sagemcom_api.enums import EncryptionMethod
from sagemcom_api.exceptions import UnknownPathException
from sagemcom_api.models import DocsisDownstreamChannel, DocsisUpstreamChannel


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


def _assert_single_collection_action(session, xpath):
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
async def test_get_docsis_downstream_channels(mock_session_factory, docsis_downstream_response):
    """Test a downstream collection is read once and returned as typed models."""
    client, session = _client_for_response(mock_session_factory, docsis_downstream_response)

    channels = await client.get_docsis_downstream_channels()

    assert channels == [
        DocsisDownstreamChannel(
            uid=0,
            channel_id=6,
            lock_status=True,
            frequency=386000000.0,
            bandwidth=8,
            symbol_rate=6952,
            modulation="Qam256",
            snr=41.0,
            power_level=8.6,
            unerrored_codewords=1000,
            correctable_codewords=3,
            uncorrectable_codewords=1,
        )
    ]
    assert session.post.call_count == 1
    _assert_single_collection_action(session, "Device/Docsis/CableModem/Downstreams")


@pytest.mark.asyncio
async def test_get_docsis_upstream_channels(mock_session_factory, docsis_upstream_response):
    """Test an upstream collection is read once and returned as typed models."""
    client, session = _client_for_response(mock_session_factory, docsis_upstream_response)

    channels = await client.get_docsis_upstream_channels()

    assert channels == [
        DocsisUpstreamChannel(
            uid=0,
            channel_id=3,
            lock_status=True,
            frequency=23800000.0,
            symbol_rate=5120,
            modulation="atdma",
            power_level=39.299999,
            frequency31=None,
            modulation31="OFDMA",
            profile_id31="2",
        )
    ]
    assert session.post.call_count == 1
    _assert_single_collection_action(session, "Device/Docsis/CableModem/Upstreams")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method_name,fixture_name", [("get_docsis_downstream_channels", "downstream"), ("get_docsis_upstream_channels", "upstream")]
)
async def test_get_docsis_channels_preserves_empty_collection(
    request,
    mock_session_factory,
    method_name,
    fixture_name,
):
    """Test an empty collection is supported and remains an empty list."""
    response = copy.deepcopy(request.getfixturevalue(f"docsis_{fixture_name}_response"))
    _set_response_value(response, [])
    client, _ = _client_for_response(mock_session_factory, response)

    assert await getattr(client, method_name)() == []


@pytest.mark.asyncio
async def test_get_docsis_channels_accepts_missing_optional_and_snr_alias(mock_session_factory, docsis_downstream_response):
    """Test optional fields may be absent and normalized SNR is accepted."""
    response = copy.deepcopy(docsis_downstream_response)
    _set_response_value(
        response,
        [{"uid": 2, "channel_id": 7, "lock_status": False, "snr": 39.5, "extra": True}],
    )
    client, _ = _client_for_response(mock_session_factory, response)

    assert await client.get_docsis_downstream_channels() == [DocsisDownstreamChannel(uid=2, channel_id=7, lock_status=False, snr=39.5)]


@pytest.mark.asyncio
async def test_get_docsis_channels_skips_malformed_sibling(mock_session_factory, docsis_downstream_response):
    """Test an isolated malformed channel does not hide a valid sibling."""
    response = copy.deepcopy(docsis_downstream_response)
    _set_response_value(
        response,
        [
            {"uid": True, "channel_id": 1, "lock_status": True},
            {"uid": 2, "channel_id": 2, "lock_status": False},
        ],
    )
    client, _ = _client_for_response(mock_session_factory, response)

    channels = await client.get_docsis_downstream_channels()

    assert [channel.uid for channel in channels] == [2]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        ["invalid", {"uid": "bad", "channel_id": 1, "lock_status": True}],
        [{"uid": 1, "channel_id": 1}],
        [{"uid": 1, "channel_id": 1, "lock_status": True, "frequency": True}],
        [{"uid": 1, "channel_id": 1, "lock_status": True, "frequency": float("nan")}],
        [{"uid": 1, "channel_id": 1, "lock_status": True, "symbol_rate": "6952"}],
    ],
)
async def test_get_docsis_channels_rejects_invalid_collection(mock_session_factory, docsis_downstream_response, value):
    """Test malformed collections and numeric values are rejected."""
    response = copy.deepcopy(docsis_downstream_response)
    _set_response_value(response, value)
    client, _ = _client_for_response(mock_session_factory, response)

    with pytest.raises(ValueError):
        await client.get_docsis_downstream_channels()


@pytest.mark.asyncio
async def test_get_docsis_channels_rejects_duplicate_uids(mock_session_factory, docsis_upstream_response):
    """Test duplicate channel UIDs cannot provide stable identity."""
    response = copy.deepcopy(docsis_upstream_response)
    _set_response_value(
        response,
        [
            {"uid": 1, "channel_id": 1, "lock_status": True},
            {"uid": 1, "channel_id": 2, "lock_status": True},
        ],
    )
    client, _ = _client_for_response(mock_session_factory, response)

    with pytest.raises(ValueError, match="Duplicate DOCSIS channel uid"):
        await client.get_docsis_upstream_channels()


@pytest.mark.asyncio
async def test_get_docsis_channels_propagates_unknown_path(mock_session_factory, docsis_downstream_response):
    """Test an unsupported plural collection remains a typed path error."""
    client, _ = _client_for_response(mock_session_factory, docsis_downstream_response)
    error = {"description": "XMO_UNKNOWN_PATH_ERR"}
    client.get_value_by_xpath = AsyncMock(side_effect=UnknownPathException(error))

    with pytest.raises(UnknownPathException) as exc_info:
        await client.get_docsis_downstream_channels()

    assert exc_info.value.args == (error,)
