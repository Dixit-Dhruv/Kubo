from unittest.mock import Mock
from uuid import UUID

import pytest
from docker.errors import DockerException, ImageNotFound, NotFound

from kubo_compute.catalog import ComputeProfile
from kubo_compute.providers import ContainerState, DockerProvider, ProviderError, ProviderFailureCode

IMAGE_DIGEST = "a" * 64
COMPUTE_ID = UUID("3f42c50d-627b-4b99-b2a3-df7b762318f2")
PROFILE = ComputeProfile(
    cpu_millicores=500,
    memory_bytes=536870912,
    ephemeral_storage_bytes=1073741824,
)


def test_docker_provider_applies_limits_and_disables_networking_until_attachment():
    client = Mock()
    client.images.get.return_value.id = "sha256:image-id"
    client.containers.create.return_value.id = "container-id"
    client.containers.get.side_effect = NotFound("missing")
    provider = DockerProvider(client)
    image_reference = f"registry.example.com/kubo/web@sha256:{IMAGE_DIGEST}"

    container_id = provider.create(COMPUTE_ID, image_reference, PROFILE)

    assert container_id == "container-id"
    client.images.get.assert_called_once_with(image_reference)
    client.images.pull.assert_not_called()
    client.containers.create.assert_called_once_with(
        image="sha256:image-id",
        name=f"kubo-{COMPUTE_ID.hex}",
        detach=True,
        labels={"kubo.compute_id": str(COMPUTE_ID)},
        nano_cpus=500_000_000,
        mem_limit=536870912,
        storage_opt={"size": "1073741824"},
        network_mode="none",
        privileged=False,
    )


def test_docker_provider_pulls_missing_digest_pinned_image():
    client = Mock()
    client.images.get.side_effect = ImageNotFound("missing")
    client.images.pull.return_value.id = "sha256:image-id"
    client.containers.create.return_value.id = "container-id"
    client.containers.get.side_effect = NotFound("missing")
    provider = DockerProvider(client)
    image_reference = f"registry.example.com/kubo/web@sha256:{IMAGE_DIGEST}"

    provider.create(COMPUTE_ID, image_reference, PROFILE)

    client.images.pull.assert_called_once_with(image_reference)


def test_docker_provider_fails_without_storage_limit_when_create_is_rejected():
    client = Mock()
    client.images.get.return_value.id = "sha256:image-id"
    client.containers.create.side_effect = DockerException("storage option is unsupported")
    client.containers.get.side_effect = NotFound("missing")
    provider = DockerProvider(client)
    image_reference = f"registry.example.com/kubo/web@sha256:{IMAGE_DIGEST}"

    with pytest.raises(ProviderError) as error:
        provider.create(COMPUTE_ID, image_reference, PROFILE)

    assert error.value.code == ProviderFailureCode.CONTAINER_CREATE_FAILED
    assert "unsupported" not in str(error.value)
    assert client.containers.create.call_count == 1
    assert client.containers.create.call_args.kwargs["storage_opt"] == {"size": "1073741824"}


def test_docker_provider_reuses_matching_container_after_worker_restart():
    client = Mock()
    client.images.get.return_value.id = "sha256:image-id"
    container = Mock()
    container.id = "container-id"
    container.attrs = {
        "Config": {
            "Image": "sha256:image-id",
            "Labels": {"kubo.compute_id": str(COMPUTE_ID)},
        },
        "HostConfig": {
            "NanoCpus": PROFILE.cpu_millicores * 1_000_000,
            "Memory": PROFILE.memory_bytes,
            "StorageOpt": {"size": str(PROFILE.ephemeral_storage_bytes)},
        },
    }
    client.containers.get.return_value = container

    container_id = DockerProvider(client).create(
        COMPUTE_ID,
        f"registry.example.com/kubo/web@sha256:{IMAGE_DIGEST}",
        PROFILE,
    )

    assert container_id == "container-id"
    client.containers.create.assert_not_called()
    container.reload.assert_called_once_with()


def test_docker_provider_maps_lifecycle_and_inspection_calls():
    client = Mock()
    container = Mock()
    container.id = "container-id"
    container.attrs = {"State": {"Status": "running", "ExitCode": 0}}
    client.containers.get.return_value = container
    provider = DockerProvider(client)

    provider.start("container-id")
    provider.stop("container-id")
    state = provider.inspect("container-id")
    provider.delete("container-id")

    assert state == ContainerState(container_id="container-id", status="running", exit_code=0)
    container.start.assert_called_once_with()
    container.stop.assert_called_once_with()
    container.reload.assert_called_once_with()
    container.remove.assert_called_once_with()


def test_docker_provider_treats_missing_container_delete_as_success():
    client = Mock()
    client.containers.get.side_effect = NotFound("missing")

    DockerProvider(client).delete("container-id")

    client.containers.get.assert_called_once_with("container-id")
