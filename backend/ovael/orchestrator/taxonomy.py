"""Attack families for both modules: what each one is, how it works, how bad it is, what stops it.

The frontend reads this through GET /api/taxonomy instead of hard-coding it, so a class learned by
the self-learning loop shows up in the UI without a frontend release. A label that is not in any
family resolves to `unknown`, which keeps the pipeline working when a reviewer introduces a new
class before anyone has written its description.

`severity_weight` (0-1) is the attack-type severity weight the architecture document refers to:
it scales the decision-table risk level into a 0-100 risk score (see risk.py).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class AttackFamily:
    id: str
    module: str
    name: str
    severity_weight: float
    summary: str
    how_it_works: list[str]
    indicators: list[str]
    mitigations: list[str]
    labels: list[str] = field(default_factory=list)  # model labels and dataset aliases
    mitre: list[str] = field(default_factory=list)
    kill_chain: str = ""
    impact: str = ""
    auto_defense: bool = False  # whether a high-risk detection may trigger a block
    is_benign: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


FAMILIES: list[AttackFamily] = [
    # ---------------------------------------------------------------- network
    AttackFamily(
        id="benign", module="network", name="Normal traffic", severity_weight=0.0, is_benign=True,
        summary="Ordinary client-server traffic.",
        how_it_works=["A client opens a connection", "Request and response are exchanged",
                      "The connection closes cleanly"],
        indicators=[], mitigations=[], labels=["benign", "normal"],
    ),
    AttackFamily(
        id="dos_flood", module="network", name="Volumetric flood (DoS/DDoS)", severity_weight=0.9,
        summary="Overwhelms the victim with more packets or connections than it can handle.",
        how_it_works=[
            "Attacker sends packets as fast as it can, often with forged headers",
            "Each SYN makes the victim reserve a half-open connection slot",
            "No ACK ever comes back, so the slots stay reserved",
            "The connection table fills and real users are refused",
        ],
        indicators=["flow_pkts_per_s", "syn_flag_count", "src_conn_rate_10s", "total_bwd_packets"],
        mitigations=["Block or rate-limit the source", "Enable SYN cookies",
                     "Put an upstream scrubbing service or CDN in front"],
        labels=["dos_flood", "ddos", "syn flood", "udp flood", "icmp flood", "dns flood",
                "dos hulk", "dos goldeneye"],
        mitre=["T1498", "T1499"], kill_chain="Impact", impact="Availability", auto_defense=True,
    ),
    AttackFamily(
        id="slow_dos", module="network", name="Slow exhaustion (Slowloris)", severity_weight=0.8,
        summary="Ties up every server worker with connections that never finish.",
        how_it_works=[
            "Attacker opens many connections to the web server",
            "It sends a partial HTTP header on each, then one more line every few seconds",
            "The server keeps every connection open waiting for the request to finish",
            "All worker slots are held and real requests queue forever",
        ],
        indicators=["flow_duration", "flow_iat_mean", "fwd_pkt_len_mean", "src_conn_rate_10s"],
        mitigations=["Block the source", "Lower header and request timeouts",
                     "Limit connections per IP"],
        labels=["slow_dos", "slowloris", "dos slowloris", "dos slowhttptest"],
        mitre=["T1499.002"], kill_chain="Impact", impact="Availability", auto_defense=True,
    ),
    AttackFamily(
        id="port_scan", module="network", name="Reconnaissance (port scan)", severity_weight=0.45,
        summary="Maps which services are running so an attack can be planned.",
        how_it_works=[
            "Attacker sends a SYN to one port after another",
            "Open ports answer SYN-ACK, closed ports answer RST",
            "The attacker drops each connection before it completes",
            "The result is a list of open services to target next",
        ],
        indicators=["src_distinct_dst_ports_10s", "rst_flag_count", "flow_duration", "total_fwd_packets"],
        mitigations=["Block the source", "Close unused ports", "Alert on repeat scanners"],
        labels=["port_scan", "port scan", "portscan", "os scan", "ping sweep", "vulnerability scan"],
        mitre=["T1046", "T1595"], kill_chain="Reconnaissance", impact="Confidentiality",
        auto_defense=True,
    ),
    AttackFamily(
        id="brute_force", module="network", name="Credential brute force", severity_weight=0.85,
        summary="Guesses passwords against a login service until one works.",
        how_it_works=[
            "Attacker connects to SSH or FTP",
            "It tries a username and a password from a word list",
            "The server rejects it and the attacker immediately tries the next",
            "Thousands of attempts later, a weak password is accepted",
        ],
        indicators=["src_conn_rate_10s", "dst_port", "flow_duration", "psh_flag_count"],
        mitigations=["Block the source", "Use key-based login and disable passwords",
                     "Add fail2ban and lockout after failed attempts"],
        labels=["brute_force", "ssh-patator", "ftp-patator", "dictionary attack",
                "web attack brute force"],
        mitre=["T1110"], kill_chain="Credential Access", impact="Confidentiality, Integrity",
        auto_defense=True,
    ),
    AttackFamily(
        id="web_attack", module="network", name="Web application attack", severity_weight=0.9,
        summary="Sends crafted input that the web application executes (SQL injection, XSS).",
        how_it_works=[
            "Attacker finds a form field or URL parameter",
            "It sends input containing SQL or script instead of normal text",
            "The application passes that input to its database or page unescaped",
            "The attacker reads data or runs script in other users' browsers",
        ],
        indicators=["fwd_pkt_len_mean", "total_fwd_bytes", "psh_flag_count", "dst_port"],
        mitigations=["Block the source", "Use parameterized queries and output encoding",
                     "Add a web application firewall"],
        labels=["web_attack", "web attack sql injection", "web attack xss", "sql injection", "xss"],
        mitre=["T1190", "T1059.007"], kill_chain="Initial Access",
        impact="Confidentiality, Integrity", auto_defense=True,
    ),
    AttackFamily(
        id="botnet", module="network", name="Botnet / command and control", severity_weight=1.0,
        summary="A compromised host checks in with an attacker-controlled server.",
        how_it_works=[
            "Malware on an internal host contacts its controller",
            "It beacons at regular intervals to receive commands",
            "Commands make it scan, attack others or send data out",
            "Small, regular flows to the same destination give it away",
        ],
        indicators=["flow_iat_std", "dst_port", "total_bwd_bytes"],
        mitigations=["Isolate the host", "Block the controller address", "Reimage the machine"],
        labels=["botnet", "bot", "infiltration", "heartbleed"],
        mitre=["T1071", "T1041"], kill_chain="Command and Control", impact="Confidentiality",
        auto_defense=False,
    ),
    # ---------------------------------------------------------------- website
    AttackFamily(
        id="web_benign", module="website", name="No tracking found", severity_weight=0.0,
        is_benign=True, summary="The site loads without third-party tracking or fingerprinting.",
        how_it_works=["Page loads its own content", "Any third parties are content delivery only"],
        indicators=[], mitigations=[], labels=["benign"],
    ),
    AttackFamily(
        id="tracker", module="website", name="Tracking", severity_weight=0.45,
        summary="Third parties record your visit for advertising or analytics.",
        how_it_works=[
            "The page loads scripts from advertising and analytics companies",
            "Those scripts set cookies that identify your browser",
            "Each site that embeds the same tracker reports your visit to it",
            "The tracker builds a profile of what you browse",
        ],
        indicators=["tracker_matched_requests", "unique_tracker_domains", "third_party_cookies",
                    "tracker_request_ratio"],
        mitigations=["Use a tracker-blocking browser or extension", "Block third-party cookies"],
        labels=["tracker"], mitre=[], kill_chain="Collection", impact="Privacy",
    ),
    AttackFamily(
        id="invasive_tracker", module="website", name="Invasive tracking / fingerprinting",
        severity_weight=0.8,
        summary="The site identifies your device without cookies or records what you do on the page.",
        how_it_works=[
            "A script draws hidden text or graphics and reads the pixels back",
            "Tiny differences in your GPU, fonts and audio stack form a device fingerprint",
            "Session-replay scripts record clicks, scrolls and typing",
            "The fingerprint follows you even after you clear cookies",
        ],
        indicators=["canvas_readback_calls", "webgl_unmasked_info_queries", "offline_audio_contexts",
                    "tracker_requests_cat_session_replay", "hidden_iframe_count"],
        mitigations=["Use a browser with fingerprinting protection",
                     "Avoid entering sensitive data on the site"],
        labels=["invasive_tracker", "fingerprinting", "malicious"],
        mitre=[], kill_chain="Collection", impact="Privacy",
    ),
]

UNKNOWN = {
    "network": AttackFamily(
        id="unknown", module="network", name="Unrecognized behaviour", severity_weight=0.6,
        summary="Traffic the models have not seen before. Needs a person to review it.",
        how_it_works=["The flow does not match any known pattern",
                      "It is saved to the review queue for an analyst"],
        indicators=[], mitigations=["Review the flow", "Label it so the next model learns it"],
    ),
    "website": AttackFamily(
        id="unknown", module="website", name="Unrecognized behaviour", severity_weight=0.6,
        summary="Site behaviour the models have not seen before. Needs a person to review it.",
        how_it_works=["The scan does not match any known pattern",
                      "It is saved to the review queue for an analyst"],
        indicators=[], mitigations=["Review the scan", "Label it so the next model learns it"],
    ),
}

_BY_LABEL: dict[tuple[str, str], AttackFamily] = {
    (f.module, label.lower()): f for f in FAMILIES for label in [*f.labels, f.id]
}


def family_for(module: str, label: str) -> AttackFamily:
    return _BY_LABEL.get((module, (label or "").strip().lower()), UNKNOWN[module])


def is_benign_label(module: str, label: str) -> bool:
    return family_for(module, label).is_benign


def families(module: str | None = None) -> list[AttackFamily]:
    items = [f for f in FAMILIES if module in (None, f.module)]
    items += [u for m, u in UNKNOWN.items() if module in (None, m)]
    return items
