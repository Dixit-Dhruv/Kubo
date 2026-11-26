from uuid import UUID

import httpx
from fastapi import HTTPException, status


class IAMClient:
    def __init__(self, base_url: str, service_token: str, timeout: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._service_token = service_token
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def authenticate(self, user_token: str) -> UUID:
        try:
            response = self._client.get(
                f"{self._base_url}/api/v1/users/me",
                headers={"Authorization": f"Bearer {user_token}"},
            )
        except httpx.RequestError as exc:
            raise self._unavailable() from exc

        if response.status_code == status.HTTP_401_UNAUTHORIZED:
            raise self._unauthorized()
        if response.status_code != status.HTTP_200_OK:
            raise self._unavailable()
        try:
            return UUID(response.json()["id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise self._unavailable() from exc

    def authorize(self, organization_id: UUID, user_id: UUID, action: str) -> None:
        if not self._service_token:
            raise self._unavailable()
        headers = {"Authorization": f"Bearer {self._service_token}"}
        try:
            service_response = self._client.post(
                f"{self._base_url}/internal/v1/service-auth/authorize",
                headers=headers,
                json={"scope": "iam:authorize"},
            )
        except httpx.RequestError as exc:
            raise self._unavailable() from exc
        if service_response.status_code != status.HTTP_200_OK:
            raise self._unavailable()
        try:
            if service_response.json()["service_id"] != "compute-api":
                raise self._unavailable()
        except (KeyError, TypeError, ValueError) as exc:
            raise self._unavailable() from exc

        try:
            response = self._client.post(
                f"{self._base_url}/internal/v1/user-auth/authorize",
                headers=headers,
                json={
                    "organization_id": str(organization_id),
                    "user_id": str(user_id),
                    "action": action,
                },
            )
        except httpx.RequestError as exc:
            raise self._unavailable() from exc

        if response.status_code == status.HTTP_403_FORBIDDEN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient organization permissions.",
            )
        if response.status_code == status.HTTP_404_NOT_FOUND:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found.",
            )
        if response.status_code != status.HTTP_200_OK:
            raise self._unavailable()
        try:
            if response.json()["authorized"] is not True:
                raise self._unavailable()
        except (KeyError, TypeError, ValueError) as exc:
            raise self._unavailable() from exc

    @staticmethod
    def _unauthorized() -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    @staticmethod
    def _unavailable() -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="IAM authorization is unavailable.",
        )
