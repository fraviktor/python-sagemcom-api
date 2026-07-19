"""Tests for mutable client session-state lifecycle."""

import json

import pytest

from sagemcom_api.client import SagemcomClient
from sagemcom_api.enums import EncryptionMethod
from sagemcom_api.exceptions import AuthenticationException, InvalidSessionException


def _client_for_responses(mock_session_factory, responses):
    session = mock_session_factory(responses)
    client = SagemcomClient(
        host="192.168.1.1",
        username="admin",
        password="admin",
        authentication_method=EncryptionMethod.MD5,
        session=session,
    )
    return client, session


def _set_authenticated_state(client):
    client._session_id = 12345
    client._server_nonce = "server-nonce"
    client._request_id = 9
    client._current_nonce = 123
    client._auth_key = "auth-key"


def _assert_logged_out_state(client):
    assert client._session_id == 0
    assert client._server_nonce == ""
    assert client._request_id == -1
    assert client._current_nonce is None
    assert client._auth_key is None


@pytest.mark.asyncio
async def test_reboot_resets_session_state(mock_session_factory, reboot_success_response):
    """Test successful reboot returns its value and clears local state."""
    client, session = _client_for_responses(mock_session_factory, [reboot_success_response])
    _set_authenticated_state(client)

    assert await client.reboot() == "true"

    _assert_logged_out_state(client)
    assert session.post.call_count == 1
    request = json.loads(session.post.call_args.kwargs["data"]["req"])["request"]
    assert request["actions"] == [
        {
            "id": 0,
            "method": "reboot",
            "xpath": "Device",
            "parameters": {"source": "GUI"},
        }
    ]


@pytest.mark.asyncio
async def test_reboot_failure_resets_session_state(mock_session_factory, login_auth_error_response):
    """Test a failed reboot preserves its error and still clears local state."""
    client, _ = _client_for_responses(mock_session_factory, [login_auth_error_response])
    _set_authenticated_state(client)

    with pytest.raises(AuthenticationException):
        await client.reboot()

    _assert_logged_out_state(client)


@pytest.mark.asyncio
async def test_login_after_reboot_starts_clean(
    mock_session_factory,
    reboot_success_response,
    login_success_response,
):
    """Test the same client can start a clean login after reboot."""
    client, session = _client_for_responses(mock_session_factory, [reboot_success_response, login_success_response])
    _set_authenticated_state(client)

    await client.reboot()
    assert await client.login() is True

    login_request = json.loads(session.post.call_args_list[1].kwargs["data"]["req"])["request"]
    assert login_request["id"] == 0
    assert login_request["session-id"] == 0
    assert client._session_id == 12345
    assert client._server_nonce == "abcdef1234567890"


@pytest.mark.asyncio
async def test_invalid_session_response_resets_all_request_state(mock_session_factory, login_invalid_session_response):
    """Test invalid-session handling uses the complete state reset."""
    client, _ = _client_for_responses(mock_session_factory, [login_invalid_session_response])
    _set_authenticated_state(client)

    with pytest.raises(InvalidSessionException):
        await client.get_value_by_xpath("Device/DeviceInfo/UpTime")

    _assert_logged_out_state(client)


@pytest.mark.asyncio
async def test_logout_resets_all_request_state(mock_session_factory, logout_success_response):
    """Test successful logout restores the same unauthenticated defaults."""
    client, _ = _client_for_responses(mock_session_factory, [logout_success_response])
    _set_authenticated_state(client)

    await client.logout()

    _assert_logged_out_state(client)


@pytest.mark.asyncio
async def test_encryption_discovery_resets_request_state(mock_session_factory, login_success_response):
    """Test encryption discovery does not leave an authenticated local session."""
    client, _ = _client_for_responses(mock_session_factory, [login_success_response])

    assert await client.get_encryption_method() is EncryptionMethod.MD5

    _assert_logged_out_state(client)
