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
    # Not every flood flow is "unusual" at the 0.99 threshold, but a second of flood always has some.
    flows = [make_flow("dos_flood", seed=i) for i in range(30)]
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "hello"
        res = post_flows(client, flows)
        assert res["alerts"] == 30
        assert res["blocked_sources"] == [flows[0]["src_ip"]]
        types = set()
        for _ in range(4):
            types.add(ws.receive_json()["type"])
        assert {"new_detection", "defense_action"} <= types

    incidents = client.get("/api/incidents").json()
    assert len(incidents) == 1 and incidents[0]["detection_count"] == 30
    assert incidents[0]["status"] == "mitigated"

    [action] = client.get("/api/actions").json()
    assert action["status"] == "simulated"
    undone = client.post(f"/api/actions/{action['id']}/undo").json()
    assert undone["status"] == "undone"
    assert client.post(f"/api/actions/{action['id']}/undo").status_code == 409

    # unblocked: the next flood is blocked again
    assert post_flows(client, [make_flow("dos_flood", seed=100 + i) for i in range(30)])["blocked_sources"]


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
    assert scan["report"]["smart"]["verdict"] and scan["report"]["smart"]["findings"]

    # adult scans stay off the shared recent-scans list
    from ovael.scanner import insights

    async def no_rdap(domain, timeout_s=8.0):
        return None

    monkeypatch.setattr(insights.reputation, "rdap", no_rdap)

    async def adult_features(ctx, scan):
        return {"features": {"tracker_matched_requests": 3},
                "report": {"title": "explicit title", "insights": await insights.offline("pornhub.com", "pornhub.com")}}

    monkeypatch.setattr(scans, "_scan_features", adult_features)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        adult = client.post("/api/scans", json={"url": "pornhub"}).json()
        while (msg := ws.receive_json())["type"] != "scan_complete":
            pass
    adult = client.get(f"/api/scans/{adult['id']}").json()
    assert adult["domain"] == "pornhub.com" and adult["report"]["smart"]["adult"]
    assert adult["report"]["title"] is None
    assert adult["id"] not in {s["id"] for s in client.get("/api/scans").json()}

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


def test_model_schema_has_baseline(client):
    s = client.get("/api/models/network/schema").json()
    assert s["threshold"] > 0.5 and len(s["features"]) == 24
    assert all("baseline" in f and f["description"] for f in s["features"])


def test_block_survives_cache_loss(client, make_flow):
    flood = [make_flow("dos_flood", seed=i) for i in range(30)]
    assert post_flows(client, flood)["blocked_sources"]
    ctx = client.app.state.ctx
    ctx.cache._mem.clear()  # what a restart does to the in-process cache
    post_flows(client, [make_flow("dos_flood", seed=200 + i) for i in range(30)])
    assert len([a for a in client.get("/api/actions").json() if a["status"] == "simulated"]) == 1


def test_evasion_sweep(client):
    r = client.post("/api/lab/evasion", json={"attack": "dos_flood", "technique": "mimic", "steps": 5, "flows": 20})
    assert r.status_code == 200
    pts = r.json()["points"]
    assert len(pts) == 5 and pts[0]["strength"] == 0 and pts[-1]["strength"] == 1
    assert pts[0]["recognized"] > pts[-1]["recognized"]


def test_learning_loop_experiment(client, tmp_path):
    before = client.post("/api/lab/learning/probe", json={"flows": 30}).json()
    assert before["flows"] == 30 and before["recognized"] < 0.5  # new behaviour is not recognised
    taught = client.post("/api/lab/learning/teach", json={"probe_id": before["probe_id"], "label": "exfiltration"})
    assert taught.status_code == 200, taught.text
    body = taught.json()
    assert body["labelled"] == 30 and body["version"] != before["model_version"]
    if body["promoted"]:
        after = client.post("/api/lab/learning/probe", json={"flows": 30}).json()
        assert after["recognized"] > before["recognized"]
        assert after["labels"].get("exfiltration", 0) > 15
    assert client.post("/api/lab/learning/teach", json={"probe_id": before["probe_id"]}).status_code == 409


def test_persistent_known_attack_is_escalated_and_blocked(client, make_flow):
    # Brute force is recognised but never "unusual", so no single flow is high risk.
    flows = [make_flow("brute_force", seed=i) for i in range(25)]
    res = post_flows(client, flows)
    assert res["blocked_sources"] == [flows[0]["src_ip"]]
    [inc] = [i for i in client.get("/api/incidents").json() if i["family"] == "brute_force"]
    assert inc["risk_level"] == "high" and inc["status"] == "mitigated"
    [action] = client.get("/api/actions").json()
    assert "persistent" in action["reason"]


def test_few_known_attack_alerts_are_not_blocked(client, make_flow):
    res = post_flows(client, [make_flow("brute_force", seed=i) for i in range(5)])
    assert res["blocked_sources"] == []


def test_review_suggestions_and_accept_all(client):
    client.post("/api/lab/learning/probe", json={"flows": 10})  # queues 10 hard examples
    queue = client.get("/api/review-queue?module=network").json()
    assert queue
    sugg = client.get("/api/review-queue/suggestions?module=network").json()
    assert set(sugg) == {i["id"] for i in queue}
    assert all({"label", "source", "reason"} <= set(v) for v in sugg.values())

    # nothing is learned until a person accepts: confirm all, with one label overridden
    decisions = [{"id": i["id"], "label": sugg[i["id"]]["label"] or "unknown_beacon"} for i in queue]
    decisions[0]["label"] = "botnet"
    res = client.post("/api/review-queue/confirm-batch", json={"items": decisions}).json()
    assert res["confirmed"] == len(queue) and res["skipped"] == 0
    assert client.get("/api/review-queue?module=network").json() == []
    again = client.post("/api/review-queue/confirm-batch", json={"items": decisions}).json()
    assert again["confirmed"] == 0 and again["skipped"] == len(queue)
