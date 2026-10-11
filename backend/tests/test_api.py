from __future__ import annotations

import pytest

CONTRACT = {"label", "confidence", "anomaly_score", "risk_level", "top_features", "model_version"}


def post_flows(client, flows):
    r = client.post("/api/flows", json={"flows": flows})
    assert r.status_code == 200, r.text
    return r.json()


def test_health_and_contract(client, make_flow):
    assert client.get("/api/health/ready").json()["ok"]
    f = make_flow("dos_flood")
    r = client.post("/api/detect", json={"module": "network", "features": f["features"]})
    assert r.status_code == 200
    assert CONTRACT <= set(r.json())


def test_flood_is_detected_blocked_and_undoable(client, make_flow):
    flows = [make_flow("dos_flood", seed=i) for i in range(5)]
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "hello"
        res = post_flows(client, flows)
        assert res["alerts"] == 5
        assert res["blocked_sources"] == [flows[0]["src_ip"]]
        types = set()
        for _ in range(4):
            types.add(ws.receive_json()["type"])
        assert {"new_detection", "defense_action"} <= types

    incidents = client.get("/api/incidents").json()
    assert len(incidents) == 1 and incidents[0]["detection_count"] == 5
    assert incidents[0]["status"] == "mitigated"

    [action] = client.get("/api/actions").json()
    assert action["status"] == "simulated"
    undone = client.post(f"/api/actions/{action['id']}/undo").json()
    assert undone["status"] == "undone"
    assert client.post(f"/api/actions/{action['id']}/undo").status_code == 409

    # unblocked: the next flood is blocked again
    assert post_flows(client, [make_flow("dos_flood", seed=99)])["blocked_sources"]


def test_benign_traffic_is_low_and_not_blocked(client, make_flow):
    res = post_flows(client, [make_flow("benign", seed=i) for i in range(20)])
    assert res["blocked_sources"] == []
    levels = {d["risk_level"] for d in client.get("/api/detections?module=network").json()}
    assert "high" not in levels


def test_novel_traffic_goes_to_review_not_defense(client, make_flow):
    res = post_flows(client, [make_flow("novel", seed=i) for i in range(5)])
    assert res["blocked_sources"] == []
    queue = client.get("/api/review-queue?module=network").json()
    assert queue, "novel flows should be hard examples"
    item = queue[0]
    r = client.post(f"/api/review-queue/{item['id']}/confirm", json={"label": "exfiltration"})
    assert r.json()["status"] == "confirmed" and r.json()["final_label"] == "exfiltration"
    assert client.post(f"/api/review-queue/{item['id']}/reject", json={}).status_code == 409


def test_detection_detail_explains_on_demand(client, make_flow):
    post_flows(client, [make_flow("port_scan")])
    [det] = client.get("/api/detections?alerts_only=true").json()
    detail = client.get(f"/api/detections/{det['id']}").json()
    assert detail["top_features"] and "features" in detail


def test_scan_rejects_unsafe_and_rate_limits(client, settings, monkeypatch):
    assert client.post("/api/scans", json={"url": "http://127.0.0.1"}).status_code == 422

    from ovael.scanner import url_guard
    from ovael.services import scans

    async def fake_check(raw, *a, **k):
        return url_guard.normalize(raw)

    async def fake_run(ctx, scan_id):
        pass

    monkeypatch.setattr(url_guard, "check", fake_check)
    monkeypatch.setattr(scans, "run_scan", fake_run)
    codes = [client.post("/api/scans", json={"url": f"https://site{i}.com"}).status_code
             for i in range(settings.scan_rate_limit + 1)]
    assert codes[:-1] == [202] * settings.scan_rate_limit and codes[-1] == 429


def test_scan_pipeline_with_stubbed_browser(client, monkeypatch):
    from ovael.scanner import url_guard
    from ovael.services import scans

    async def fake_check(raw, *a, **k):
        return url_guard.normalize(raw)

    async def fake_features(ctx, scan):
        return {"features": {"canvas_readback_calls": 8, "tracker_matched_requests": 40,
                             "unique_tracker_domains": 12, "third_party_cookies": 9,
                             "tracker_requests_cat_advertising": 20},
                "report": {"title": "Tracky"}}

    monkeypatch.setattr(url_guard, "check", fake_check)
    monkeypatch.setattr(scans, "_scan_features", fake_features)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        r = client.post("/api/scans", json={"url": "https://tracky-site.com"})
        assert r.status_code == 202
        while (msg := ws.receive_json())["type"] != "scan_complete":
            pass
    scan = client.get(f"/api/scans/{r.json()['id']}").json()
    assert scan["status"] == "completed"
    assert scan["detection"]["label"] in ("tracker", "invasive_tracker")
    assert scan["detection"]["top_features"]

    # second request for the same domain comes from the cache
    again = client.post("/api/scans", json={"url": "https://tracky-site.com/other"})
    assert again.status_code == 200 and again.json()["cached"]


def test_models_and_taxonomy(client):
    models = client.get("/api/models").json()
    assert {m["module"] for m in models} == {"network", "website"}
    assert all(m["status"] == "active" for m in models)
    tax = client.get("/api/taxonomy?module=network").json()
    flood = next(f for f in tax["families"] if f["id"] == "dos_flood")
    assert flood["how_it_works"] and flood["severity_weight"] > 0.5
    assert len(tax["decision_table"]) == 4


def test_stats(client, make_flow):
    post_flows(client, [make_flow("benign", seed=1), make_flow("port_scan", seed=2)])
    s = client.get("/api/stats/summary").json()
    assert s["total"] == 2 and s["timeline"]


@pytest.mark.parametrize("path", ["/api/actions/x/undo", "/api/models/network/retrain"])
def test_admin_token_enforced(settings, path):
    from fastapi.testclient import TestClient

    from ovael.api.app import create_app

    settings.admin_token = "secret"
    with TestClient(create_app(settings)) as c:
        assert c.post(path).status_code == 401
        assert c.post(path, headers={"Authorization": "Bearer wrong"}).status_code == 401
