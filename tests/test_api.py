"""Tests ligeros sin cargar modelos GPU (no arranca lifespan pesado)."""

from __future__ import annotations


def test_api_key_repository_env_only():
    from app.infrastructure.api_key_repository import ApiKeyRepository

    r = ApiKeyRepository(None, frozenset({"secret1", "secret2"}))
    assert r.is_valid("secret1")
    assert not r.is_valid("wrong")
    assert r.has_auth_configured()


def test_api_key_repository_empty_means_open():
    from app.infrastructure.api_key_repository import ApiKeyRepository

    r = ApiKeyRepository(None, frozenset())
    assert not r.has_auth_configured()
    assert not r.is_valid("anything")


def test_openapi_includes_v1_routes():
    from app.main import app

    schema = app.openapi()
    paths = schema["paths"]
    assert "/v1/upload" in paths
    assert "/v1/generate" in paths
    assert "/health" in paths


def test_generate_documents_seed_in_openapi():
    from app.main import app

    gen = app.openapi()["paths"]["/v1/generate"]["post"]
    # Query `seed` aparece en parameters o en el schema serializado
    assert "seed" in str(gen)
