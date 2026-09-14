import pytest


@pytest.mark.asyncio
async def test_health_liveness_reports_ok(client):
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"]


@pytest.mark.asyncio
async def test_health_readiness_reports_dependency_checks(client):
    response = await client.get("/health/ready")
    assert response.status_code in (200, 503)
    body = response.json()
    assert set(body["checks"].keys()) == {"database", "redis"}
    assert body["status"] in ("ok", "degraded")
    all_ok = all(value == "ok" for value in body["checks"].values())
    assert (body["status"] == "ok") == all_ok
    assert (response.status_code == 200) == all_ok


@pytest.mark.asyncio
async def test_health_response_carries_request_id_header(client):
    response = await client.get("/health")
    assert response.headers.get("X-Request-Id")


@pytest.mark.asyncio
async def test_request_id_header_is_echoed_back(client):
    response = await client.get("/health", headers={"X-Request-Id": "req_test_fixed"})
    assert response.headers["X-Request-Id"] == "req_test_fixed"
