from __future__ import annotations


def test_api_responses_are_never_cached(client):
    response = client.get("/api/me")
    assert response.headers["cache-control"] == "private, no-store"


def test_static_assets_keep_their_existing_cache_policy(client):
    assert client.get("/styles.css").headers.get("cache-control") != "private, no-store"
    assert client.get("/script.js").headers.get("cache-control") != "private, no-store"
    assert client.get("/version.js").headers["cache-control"] == "no-store"
