from unittest.mock import Mock
from uuid import UUID

import httpx
import pytest
from fastapi import HTTPException

from kubo_compute.iam_client import IAMClient

USER_ID = UUID("8c07034d-15ae-46cb-846b-fdb9911e637b")
ORGANIZATION_ID = UUID("089b3a23-afb4-4a6d-819a-5e7fdbac0084")


def response(status_code: int, payload: dict[str, str]) -> Mock:
    result = Mock()
    result.status_code = status_code
    result.json.return_value = payload
    return result


def test_authentication_validates_the_user_token_through_iam():
    client = IAMClient("http://iam", "service-secret")
    client._client = Mock()
    client._client.get.return_value = response(200, {"id": str(USER_ID)})

    assert client.authenticate("user-secret") == USER_ID
    client._client.get.assert_called_once_with(
        "http://iam/api/v1/users/me",
        headers={"Authorization": "Bearer user-secret"},
    )


def test_invalid_user_token_is_401_but_iam_outage_is_503():
    client = IAMClient("http://iam", "service-secret")
    client._client = Mock()
    client._client.get.return_value = response(401, {})
    with pytest.raises(HTTPException) as unauthorized:
        client.authenticate("expired")
    assert unauthorized.value.status_code == 401

    client._client.get.side_effect = httpx.ConnectError("unavailable")
    with pytest.raises(HTTPException) as unavailable:
        client.authenticate("user-secret")
    assert unavailable.value.status_code == 503


def test_authorization_validates_service_identity_then_organization_action():
    client = IAMClient("http://iam", "service-secret")
    client._client = Mock()
    client._client.post.side_effect = [
        response(200, {"service_id": "compute-api"}),
        response(200, {"authorized": True}),
    ]

    client.authorize(ORGANIZATION_ID, USER_ID, "compute:create")

    assert client._client.post.call_args_list[0].args[0] == (
        "http://iam/internal/v1/service-auth/authorize"
    )
    assert client._client.post.call_args_list[0].kwargs["json"] == {"scope": "iam:authorize"}
    assert client._client.post.call_args_list[1].kwargs["json"] == {
        "organization_id": str(ORGANIZATION_ID),
        "user_id": str(USER_ID),
        "action": "compute:create",
    }


def test_authorization_maps_role_denial_and_service_auth_failure():
    client = IAMClient("http://iam", "service-secret")
    client._client = Mock()
    client._client.post.side_effect = [
        response(200, {"service_id": "compute-api"}),
        response(403, {}),
    ]
    with pytest.raises(HTTPException) as denied:
        client.authorize(ORGANIZATION_ID, USER_ID, "compute:stop")
    assert denied.value.status_code == 403

    client._client.post.side_effect = [response(401, {})]
    with pytest.raises(HTTPException) as unavailable:
        client.authorize(ORGANIZATION_ID, USER_ID, "compute:stop")
    assert unavailable.value.status_code == 503


def test_authorization_fails_closed_on_malformed_success_response():
    client = IAMClient("http://iam", "service-secret")
    client._client = Mock()
    client._client.post.side_effect = [
        response(200, {"service_id": "compute-api"}),
        response(200, {"authorized": False}),
    ]

    with pytest.raises(HTTPException) as unavailable:
        client.authorize(ORGANIZATION_ID, USER_ID, "compute:read")

    assert unavailable.value.status_code == 503
