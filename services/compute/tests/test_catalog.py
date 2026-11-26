import json

import pytest
from pydantic import ValidationError

from kubo_compute.catalog import ComputeProfile, ImageCatalog, ProfileCatalog

IMAGE_DIGEST = "a" * 64


def test_loads_operator_catalog_with_digest_pinned_images(tmp_path):
    catalog_path = tmp_path / "image-catalog.json"
    expected_reference = f"registry.example.com/kubo/web@sha256:{IMAGE_DIGEST}"
    catalog_path.write_text(
        json.dumps({"images": {"approved-web": expected_reference}}),
        encoding="utf-8",
    )

    catalog = ImageCatalog.load(catalog_path)

    assert catalog.resolve("approved-web") == expected_reference
    assert catalog.resolve("unlisted") is None


@pytest.mark.parametrize(
    ("key", "reference"),
    [
        ("Approved-Web", f"registry.example.com/kubo/web@sha256:{IMAGE_DIGEST}"),
        ("approved-web", "registry.example.com/kubo/web:latest"),
        ("approved-web", f"registry.example.com/kubo/web@sha256:{'a' * 63}"),
    ],
)
def test_rejects_invalid_keys_and_unpinned_or_invalid_references(key, reference):
    with pytest.raises(ValidationError):
        ImageCatalog(images={key: reference})


def test_rejects_unknown_catalog_fields_and_empty_catalog():
    with pytest.raises(ValidationError):
        ImageCatalog.model_validate(
            {
                "images": {
                    "approved-web": f"registry.example.com/kubo/web@sha256:{IMAGE_DIGEST}"
                },
                "defaults": {},
            }
        )

    with pytest.raises(ValidationError):
        ImageCatalog(images={})


def test_loads_operator_profiles_with_explicit_resource_limits(tmp_path):
    catalog_path = tmp_path / "profiles.json"
    expected_profile = {
        "cpu_millicores": 500,
        "memory_bytes": 536870912,
        "ephemeral_storage_bytes": 1073741824,
    }
    catalog_path.write_text(
        json.dumps({"profiles": {"small": expected_profile}}),
        encoding="utf-8",
    )

    catalog = ProfileCatalog.load(catalog_path)

    assert catalog.resolve("small") == ComputeProfile(**expected_profile)
    assert catalog.resolve("unlisted") is None


@pytest.mark.parametrize(
    "profile",
    [
        {"cpu_millicores": 0, "memory_bytes": 1, "ephemeral_storage_bytes": 1},
        {"cpu_millicores": 1, "memory_bytes": 0, "ephemeral_storage_bytes": 1},
        {"cpu_millicores": 1, "memory_bytes": 1, "ephemeral_storage_bytes": 0},
    ],
)
def test_rejects_profiles_without_positive_limits(profile):
    with pytest.raises(ValidationError):
        ComputeProfile(**profile)


def test_profile_catalog_rejects_invalid_keys_and_empty_catalog():
    limits = {
        "cpu_millicores": 500,
        "memory_bytes": 536870912,
        "ephemeral_storage_bytes": 1073741824,
    }
    with pytest.raises(ValidationError):
        ProfileCatalog(profiles={"Small": ComputeProfile(**limits)})

    with pytest.raises(ValidationError):
        ProfileCatalog(profiles={})
