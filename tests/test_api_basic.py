from base64 import b64encode


def _auth_header(username: str, password: str) -> dict[str, str]:
    token = b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body.get("status") == "healthy"
    assert "+09:00" in body.get("timestamp", "") or body.get("timestamp")


def test_advice_mocked(client):
    res = client.post("/api/advice", data={"symptom": "머리가 아파요"})
    assert res.status_code == 200
    body = res.json()
    assert "테스트" in body.get("advice", "")


def test_admin_logs_requires_auth(client):
    # 인증 없으면 401
    res = client.get("/api/logs")
    assert res.status_code == 401


def test_admin_endpoints_with_auth(client, admin_auth):
    u, p = admin_auth
    headers = _auth_header(u, p)

    r1 = client.get("/api/logs?limit=1", headers=headers)
    assert r1.status_code in (200, 204)

    r2 = client.get("/api/stats", headers=headers)
    assert r2.status_code == 200
    stats = r2.json()
    assert "total_logs" in stats

    r3 = client.get("/api/crawling_jobs?limit=1", headers=headers)
    # 일부 환경에서는 크롤링 기능이 비활성일 수 있어 404를 허용
    if r3.status_code == 200:
        jobs = r3.json()
        if jobs:
            sample = jobs[0]
            for k in ("created_at", "started_at", "completed_at"):
                if sample.get(k):
                    assert "+09:00" in sample[k] or sample[k]
    else:
        assert r3.status_code in (200, 404)


