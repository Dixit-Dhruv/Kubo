from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from docker.client import DockerClient
from docker.errors import DockerException, ImageNotFound, NotFound
from docker.models.containers import Container

from kubo_compute.catalog import ComputeProfile


class ProviderFailureCode(StrEnum):
    DOCKER_UNAVAILABLE = "docker_unavailable"
    IMAGE_PULL_FAILED = "image_pull_failed"
    CONTAINER_CREATE_FAILED = "container_create_failed"
    CONTAINER_NOT_FOUND = "container_not_found"
    CONTAINER_START_FAILED = "container_start_failed"
    CONTAINER_STOP_FAILED = "container_stop_failed"
    CONTAINER_INSPECT_FAILED = "container_inspect_failed"
    CONTAINER_DELETE_FAILED = "container_delete_failed"


class ProviderError(RuntimeError):
    def __init__(self, code: ProviderFailureCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ContainerState:
    container_id: str
    status: str
    exit_code: int | None


class ComputeProvider(Protocol):
    def create(self, compute_id: UUID, image_reference: str, profile: ComputeProfile) -> str: ...

    def start(self, container_id: str) -> None: ...

    def stop(self, container_id: str) -> None: ...

    def inspect(self, container_id: str) -> ContainerState: ...

    def delete(self, container_id: str) -> None: ...


class DockerProvider:
    def __init__(self, client: DockerClient) -> None:
        self._client = client

    def create(self, compute_id: UUID, image_reference: str, profile: ComputeProfile) -> str:
        try:
            image = self._client.images.get(image_reference)
        except ImageNotFound:
            try:
                image = self._client.images.pull(image_reference)
            except DockerException:
                raise ProviderError(
                    ProviderFailureCode.IMAGE_PULL_FAILED,
                    "The approved compute image could not be loaded.",
                ) from None
        except DockerException:
            raise ProviderError(
                ProviderFailureCode.IMAGE_PULL_FAILED,
                "The approved compute image could not be loaded.",
            ) from None

        try:
            container = self._client.containers.create(
                image=image.id,
                name=f"kubo-{compute_id.hex}",
                detach=True,
                labels={"kubo.compute_id": str(compute_id)},
                nano_cpus=profile.cpu_millicores * 1_000_000,
                mem_limit=profile.memory_bytes,
                storage_opt={"size": str(profile.ephemeral_storage_bytes)},
                network_mode="none",
                privileged=False,
            )
        except DockerException:
            raise ProviderError(
                ProviderFailureCode.CONTAINER_CREATE_FAILED,
                "Docker could not create the container with its configured resource limits.",
            ) from None
        return container.id

    def start(self, container_id: str) -> None:
        container = self._get_container(container_id)
        try:
            container.start()
        except DockerException:
            raise ProviderError(
                ProviderFailureCode.CONTAINER_START_FAILED,
                "Docker could not start the container.",
            ) from None

    def stop(self, container_id: str) -> None:
        container = self._get_container(container_id)
        try:
            container.stop()
        except DockerException:
            raise ProviderError(
                ProviderFailureCode.CONTAINER_STOP_FAILED,
                "Docker could not stop the container.",
            ) from None

    def inspect(self, container_id: str) -> ContainerState:
        container = self._get_container(container_id)
        try:
            container.reload()
        except DockerException:
            raise ProviderError(
                ProviderFailureCode.CONTAINER_INSPECT_FAILED,
                "Docker could not inspect the container.",
            ) from None

        state = container.attrs["State"]
        return ContainerState(
            container_id=container.id,
            status=state["Status"],
            exit_code=state.get("ExitCode"),
        )

    def delete(self, container_id: str) -> None:
        try:
            container = self._client.containers.get(container_id)
        except NotFound:
            return
        except DockerException:
            raise ProviderError(
                ProviderFailureCode.DOCKER_UNAVAILABLE,
                "Docker could not retrieve the container for cleanup.",
            ) from None

        try:
            container.remove()
        except NotFound:
            return
        except DockerException:
            raise ProviderError(
                ProviderFailureCode.CONTAINER_DELETE_FAILED,
                "Docker could not remove the container.",
            ) from None

    def _get_container(self, container_id: str) -> Container:
        try:
            return self._client.containers.get(container_id)
        except NotFound:
            raise ProviderError(
                ProviderFailureCode.CONTAINER_NOT_FOUND,
                "The compute container was not found.",
            ) from None
        except DockerException:
            raise ProviderError(
                ProviderFailureCode.DOCKER_UNAVAILABLE,
                "Docker could not retrieve the container.",
            ) from None
