from __future__ import annotations

import pytest

from ovael.feature_extraction.flow_builder import FlowBuilder, Packet
from ovael.feature_extraction.network_schema import NETWORK_FEATURES
from ovael.ml.labeling import label_website_dataset
from ovael.orchestrator import decide, family_for
from ovael.scanner.url_guard import UnsafeURL, is_public_ip, normalize


# ---------------------------------------------------------------- decision table
@pytest.mark.parametrize("attack,unusual,level", [
    (True, True, "high"), (True, False, "medium"), (False, True, "suspicious"), (False, False, "low")])
def test_decision_table_rows(attack, unusual, level):
    d = decide(is_attack=attack, is_unusual=unusual, confidence=0.9, anomaly_score=0.5,
               family=family_for("network", "dos_flood" if attack else "benign"))
    assert d.risk_level == level


def test_risk_score_stays_inside_its_band():
    fam = family_for("network", "dos_flood")
    for conf in (0.0, 0.5, 1.0):
        assert 75 <= decide(is_attack=True, is_unusual=True, confidence=conf, anomaly_score=1, family=fam).risk_score <= 100
        assert 50 <= decide(is_attack=True, is_unusual=False, confidence=conf, anomaly_score=0, family=fam).risk_score <= 74
    assert decide(is_attack=False, is_unusual=False, confidence=1, anomaly_score=0.2,
                  family=family_for("network", "benign")).risk_score <= 24


def test_flagged_disagreement_goes_to_review():
    d = decide(is_attack=False, is_unusual=True, confidence=0.99, anomaly_score=0.99,
               family=family_for("network", "benign"))
    assert d.needs_review and not d.models_agree


def test_taxonomy_aliases_and_unknown():
    assert family_for("network", "SYN Flood").id == "dos_flood"
    assert family_for("network", "ssh-patator").id == "brute_force"
    assert family_for("network", "something-new").id == "unknown"
    assert family_for("website", "benign").is_benign


# ---------------------------------------------------------------- flow builder
def test_flow_builder_closes_on_fin_and_builds_schema():
    fb = FlowBuilder()
    pkts = [Packet(0.0, "10.0.0.1", "10.0.0.2", 5000, 80, 6, 60, "S", 64240),
            Packet(0.01, "10.0.0.2", "10.0.0.1", 80, 5000, 6, 60, "SA"),
            Packet(0.02, "10.0.0.1", "10.0.0.2", 5000, 80, 6, 400, "PA"),
            Packet(0.05, "10.0.0.2", "10.0.0.1", 80, 5000, 6, 1400, "PA"),
            Packet(0.06, "10.0.0.1", "10.0.0.2", 5000, 80, 6, 52, "FA"),
            Packet(0.07, "10.0.0.2", "10.0.0.1", 80, 5000, 6, 52, "FA")]
    out = [f for p in pkts for f in fb.add(p)]
    assert len(out) == 1
    f = out[0].features
    assert list(f) == NETWORK_FEATURES
    assert f["total_fwd_packets"] == 3 and f["total_bwd_packets"] == 3
    assert f["syn_flag_count"] == 2 and f["init_win_bytes_fwd"] == 64240
    assert out[0].meta["src_ip"] == "10.0.0.1" and out[0].meta["dst_port"] == 80


def test_flow_builder_scan_context():
    fb = FlowBuilder()
    flows = []
    for port in range(1, 60):
        flows += fb.add(Packet(port * 0.01, "10.0.0.9", "10.0.0.2", 40000, port, 6, 44, "S"))
        flows += fb.add(Packet(port * 0.01 + 0.001, "10.0.0.2", "10.0.0.9", port, 40000, 6, 40, "R"))
    assert flows[-1].features["src_distinct_dst_ports_10s"] == 59


# ---------------------------------------------------------------- URL guard
@pytest.mark.parametrize("url", ["ftp://example.com", "http://127.0.0.1/", "http://[::1]/",
                                 "https://user:pw@example.com", "https://example.com:22/",
                                 "http://localhost/", "", "x" * 3000])
def test_url_guard_rejects(url):
    with pytest.raises(UnsafeURL):
        normalize(url)


def test_url_guard_normalizes():
    c = normalize("Example.COM/path?q=1#frag")
    assert c.url == "https://example.com/path?q=1" and c.domain == "example.com"


def test_url_guard_resolves_bare_names():
    assert normalize("rummycircle").domain == "rummycircle.com"  # found in the Tranco list
    assert normalize("Instagram").url == "https://instagram.com/"
    assert normalize("surely-not-a-real-site-xyz").domain == "surely-not-a-real-site-xyz.com"


def test_lookalike_domains():
    from ovael.scanner.reputation import lookalike_of

    assert lookalike_of("instagrarn.com", None)["kind"] == "lookalike_characters"
    assert lookalike_of("paypal-secure-login.com", None)["kind"] == "contains_brand"
    assert lookalike_of("instagram.com", 11) is None
    assert lookalike_of("rummycircle.com", 247095) is None


def test_content_classifier():
    from ovael.scanner.insights import classify_content

    c = classify_content("rummycircle.com", "Play Rummy Online", {"text_sample": "Win real money in cash games"})
    assert c["categories"][0]["id"] == "gambling"
    c = classify_content("example.com", "Notice", {"text_sample": "Your account has been suspended. Verify your account now."})
    assert len(c["scam_phrases"]) >= 2


def test_smart_report_verdicts():
    from ovael.services.smart_report import compose

    det = {"risk_level": "low", "risk_score": 10, "label": "benign"}
    popular = {"domain": "example.org", "tranco_rank": 200, "rdap": {"age_days": 9000, "registered": "2001-01-01"},
               "https": True, "tls": {"protocol": "TLS 1.3", "issuer": "CA", "valid_to": "2027-01-01"},
               "content": {"categories": []}}
    assert compose({"insights": popular}, det)["verdict"] == "Safe to open"

    gambling = {**popular, "content": {"categories": [{"id": "gambling", "evidence": ["rummy"]}]}}
    assert compose({"insights": gambling}, det)["risk_level"] == "suspicious"

    phish = {"domain": "instagrarn.com", "original_domain": "instagrarn.com", "password_inputs": 1,
             "lookalike": {"target": "instagram.com", "kind": "lookalike_characters"}, "rdap": {"age_days": 3},
             "https": True, "content": {"categories": []}}
    r = compose({"insights": phish}, det)
    assert r["risk_level"] == "high" and r["findings"][0]["severity"] == "critical"

    legacy = compose({"title": "old cached report"}, det)  # no insights: privacy only, no crash
    assert legacy["limited"] and all(f["category"] == "privacy" for f in legacy["findings"])


def test_adult_sites_are_flagged_and_never_safe():
    from ovael.scanner.reputation import is_adult_domain
    from ovael.services.smart_report import compose

    assert is_adult_domain("www.pornhub.com") and is_adult_domain("xvideos.com")
    assert not is_adult_domain("notpornhub.com") and not is_adult_domain("instagram.com")
    ins = {"domain": "xvideos.com", "tranco_rank": 100, "rdap": {"age_days": 9000, "registered": "2000"},
           "https": True, "content": {"categories": []}, "adult_listed": True}
    r = compose({"insights": ins}, {"risk_level": "low", "risk_score": 5, "label": "benign"})
    assert r["adult"] and r["risk_level"] == "medium" and r["verdict"].startswith("Adult content (18+)")
    assert any("sextortion" in a for a in r["advice"])


def test_offline_report_when_page_cannot_load():
    from ovael.services.smart_report import compose

    ins = {"offline": True, "domain": "example.com", "tranco_rank": 169, "content": {"categories": []}}
    r = compose({"insights": ins}, None)
    assert r["offline"] and r["verdict"] == "Couldn't fully check this website"
    assert {c["id"]: c["status"] for c in r["categories"]}["privacy"] == "unknown"


def test_private_addresses_are_not_public():
    import ipaddress

    for ip in ("10.0.0.1", "192.168.1.1", "169.254.169.254", "100.64.0.1", "::ffff:127.0.0.1"):
        assert not is_public_ip(ipaddress.ip_address(ip))
    assert is_public_ip(ipaddress.ip_address("93.184.216.34"))


# ---------------------------------------------------------------- website labels
def test_weak_labels_and_human_override(website_rows):
    df = label_website_dataset(website_rows)
    assert len(df) == 4  # failed crawl dropped
    assert list(df["label"]) == ["invasive_tracker", "tracker", "benign", "benign"]
    assert df.iloc[-1]["label_source"] == "manual_review_label"


# ---------------------------------------------------------------- learning loop
def test_retrain_promotes_only_when_not_worse(tmp_path, monkeypatch):
    from ovael.config import Settings
    from ovael.learning_loop.retrain import retrain
    from ovael.ml import datasets, synthetic
    from ovael.ml.registry import ModelRegistry

    monkeypatch.setattr(datasets, "load_base",
                        lambda m, s: (synthetic.generate(n_per_class=150, seed=5), "synthetic_bootstrap"))
    s, reg = Settings(model_dir=tmp_path, env="test"), ModelRegistry(tmp_path)
    first = retrain("network", s, reg)
    assert first["promoted"] and reg.active_version("network") == "network-v1"

    # Reviewed samples that teach a brand-new class.
    novel = synthetic.generate(n_per_class=40, seed=8, classes=["novel"]).assign(label="exfiltration")
    second = retrain("network", s, reg, novel)
    assert second["version"] == "network-v2"
    assert second["metrics"]["macro_f1"] >= first["metrics"]["macro_f1"] - 1e-9 or not second["promoted"]
    if second["promoted"]:
        assert "exfiltration" in reg.active("network").classes

    # Versions are kept, so rolling back is a promote.
    reg.promote("network", "network-v1")
    assert reg.active("network").version == "network-v1"


def test_nat64_addresses_are_judged_by_embedded_ipv4():
    import ipaddress

    assert is_public_ip(ipaddress.ip_address("64:ff9b::c7e8:6851"))  # 199.232.104.81
    assert not is_public_ip(ipaddress.ip_address("64:ff9b::7f00:1"))  # 127.0.0.1
    assert not is_public_ip(ipaddress.ip_address("64:ff9b::a9fe:a9fe"))  # 169.254.169.254
