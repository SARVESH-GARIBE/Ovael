"""Smart report: turns the scan's observations and the model's privacy verdict into a plain-language
answer to "is it safe to open this website?".

Inputs are the scanner's report (with `insights`, see scanner/insights.py) and the detection. The
output is stored at report["smart"]. Each rule emits a finding with a severity; severities add up
to a threat score, the model's tracking score is blended in, and the total maps to a verdict.
Every rule tolerates missing signals (old cached reports, failed RDAP lookups, ...).
"""

from __future__ import annotations

from typing import Any

SEVERITY_POINTS = {"critical": 45, "high": 22, "medium": 10, "low": 4, "info": 0, "good": -6}
SEVERITY_ORDER = ["critical", "high", "medium", "low", "info", "good"]

VERDICTS = [  # (min score, risk level, headline, advice)
    (75, "high", "Avoid this website",
     "Several strong warning signs. Don't open it, and never enter passwords, card details or personal data here."),
    (50, "medium", "Open with caution",
     "There are real risks. If you open it, don't log in, pay or download anything unless you trust the site."),
    (25, "suspicious", "Mostly safe, with some concerns",
     "No sign of malware or phishing, but read the concerns below before you sign up or pay."),
    (0, "low", "Safe to open",
     "Nothing dangerous found. Normal care applies, as on any website."),
]

ADULT_VERDICT = ("Adult content (18+): open with caution",
                 "This website is only for adults, and its ads, pop-ups and payment offers carry real risks. "
                 "Read the warnings below before you open it.")
OFFLINE_VERDICTS = {  # risk level -> (headline, advice) when the page itself could not be loaded
    "low": ("Couldn't fully check this website", "Be careful until you know more about it."),
    "suspicious": ("Some concerns (reputation only)", "Read the concerns below before you open it."),
}

ADULT_ADVICE = [
    "Don't download video players, codecs or apps the site offers. They are a common way to spread malware.",
    "Close pop-ups and “your device is infected” alerts with the tab's close button, never by clicking inside them.",
    "Use a private window and a tracker blocker, so this visit doesn't end up in your ad profile.",
    "Be wary of “premium” or subscription offers: check the billing terms and cancel policy before paying.",
    "Ignore emails claiming “we recorded you” and demanding money. These sextortion emails are a scam.",
    "Check that the site is legal to access where you live; many countries block or age-restrict it.",
]

CATEGORY_LABELS = {
    "gambling": "real-money gaming / gambling", "adult": "adult content", "crypto_investment": "crypto or investment",
    "loans": "lending / loans", "piracy": "piracy or free streaming", "dating": "dating", "social": "social media",
    "shopping": "online shopping", "banking": "banking or finance", "news": "news",
}

CATEGORY_RULES = {  # category -> (severity, title, detail, advice)
    "gambling": ("medium", "Real-money gaming or gambling",
                 "Games played for money carry a real risk of financial loss and addiction. Real-money gaming is "
                 "restricted or illegal in some countries and states.",
                 "Check that real-money gaming is legal where you live, set a deposit limit, and never chase losses."),
    "adult": ("high", "Adult content (18+)",
              "Sexually explicit material meant only for adults. Adult sites carry far more malicious ads, "
              "pop-unders, fake “virus detected” alerts and fake video-player downloads than the rest of the web, "
              "and they are blocked or age-restricted by law in some countries.",
              None),  # its advice is ADULT_ADVICE
    "crypto_investment": ("medium", "Crypto or investment offers",
                          "Crypto and trading sites are the most common home of 'guaranteed returns' scams.",
                          "Never share a wallet seed phrase, and treat promises of guaranteed or doubled returns as a scam."),
    "loans": ("medium", "Lending or instant loans",
              "Unregulated loan apps often charge hidden fees and misuse contacts and photos for recovery.",
              "Check the lender is registered with your country's financial regulator before you share documents."),
    "piracy": ("high", "Piracy or free streaming",
               "Piracy sites are a common source of malware, fake download buttons and malicious ads.",
               "Don't download files or browser extensions from this site."),
    "dating": ("low", "Dating",
               "Dating sites are a common place for romance and money-request scams.",
               "Never send money or gift cards to someone you have only met online."),
}


def _f(category: str, severity: str, title: str, detail: str, advice: str | None = None) -> dict:
    return {"category": category, "severity": severity, "title": title, "detail": detail, "advice": advice}


def _g(obj: Any, key: str, default=None):
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


def _reputation(ins: dict) -> list[dict]:
    out = []
    domain = ins.get("domain", "this site")
    site_hosts = {domain, ins.get("original_domain")}
    malware = ins.get("malware_hosts") or []
    own = [h for h in malware if any(h == s or h.endswith("." + s) for s in site_hosts if s)]
    if own:
        out.append(_f("reputation", "critical", "Listed as a malware site",
                      f"{', '.join(own)} is on the URLhaus list of hosts distributing malware.",
                      "Don't open this website."))
    elif malware:
        out.append(_f("reputation", "high", "Loads content from a known malware host",
                      f"The page contacted {', '.join(malware[:3])}, listed by URLhaus as distributing malware.",
                      "Don't download anything from this page."))

    has_password = (ins.get("password_inputs") or 0) > 0
    look = ins.get("lookalike")
    if look:
        target = look["target"]
        kind = look["kind"]
        if kind in ("typo", "lookalike_characters"):
            out.append(_f("reputation", "critical" if has_password else "high", f"Imitates {target}",
                          f"The address {domain} is a near-copy of {target}, a classic phishing trick.",
                          f"To use {target}, type its address yourself instead of following links."))
        elif kind == "contains_brand":
            out.append(_f("reputation", "high" if has_password else "medium", f"Uses the name of {target}",
                          f"{domain} contains the brand name of {target} but is a different website.",
                          f"Don't enter your {target} password here."))
        else:
            out.append(_f("reputation", "medium" if has_password else "low", f"Same name as {target}, different site",
                          f"{domain} shares its name with {target} but is a separate domain, possibly run by someone else.",
                          f"If you meant {target}, go there directly."))

    rank = ins.get("tranco_rank")
    if rank is not None and rank <= 10_000:
        out.append(_f("reputation", "good", "One of the most visited websites",
                      f"Ranked #{rank:,} worldwide by the Tranco list."))
    elif rank is not None and rank <= 100_000:
        out.append(_f("reputation", "good", "A popular, established website", f"Ranked #{rank:,} worldwide."))
    elif rank is not None:
        out.append(_f("reputation", "info", "A moderately known website", f"Ranked #{rank:,} worldwide."))

    rd = ins.get("rdap") or {}
    age = rd.get("age_days")
    if age is not None:
        years = age / 365.25
        if age < 30:
            out.append(_f("reputation", "high", "Brand-new domain",
                          f"Registered only {age} day{'s' if age != 1 else ''} ago. Most scam sites live for days or weeks.",
                          "Be very careful with brand-new sites, especially ones that ask for money or logins."))
        elif age < 180:
            out.append(_f("reputation", "medium", "Recently registered domain", f"Registered {age} days ago."))
        elif age < 365:
            out.append(_f("reputation", "low", "Domain under a year old", f"Registered {age} days ago."))
        elif years >= 5:
            out.append(_f("reputation", "good", "Long-established domain",
                          f"Registered in {rd['registered'][:4]} ({int(years)} years ago)."))
    if rank is None and (age is None or age < 3 * 365):
        out.append(_f("reputation", "low", "Little-known website",
                      "Not in the top 1 million websites, so there is little public track record."))
    if ins.get("suspicious_tld"):
        out.append(_f("reputation", "low", f"Uncommon domain ending (.{ins.get('tld')})",
                      "This ending is cheap and disproportionately used by spam and scam sites."))
    if ins.get("punycode"):
        out.append(_f("reputation", "medium", "Address uses international characters",
                      "Internationalised addresses can hide letters that look identical to Latin ones.",
                      "Check the address carefully before trusting the page."))
    return out


def _connection(ins: dict, report: dict) -> list[dict]:
    out = []
    has_password = (ins.get("password_inputs") or 0) > 0
    if ins.get("https") is False:
        out.append(_f("connection", "high" if has_password else "medium", "Not encrypted (HTTP)",
                      "Anything you send, including passwords, can be read or changed by others on the network.",
                      "Don't enter passwords or personal data on an unencrypted page."))
    tls = ins.get("tls")
    if tls:
        proto = tls.get("protocol") or ""
        days_left = tls.get("days_left")
        if days_left is not None and days_left < 0:
            out.append(_f("connection", "high", "Expired certificate", f"The certificate expired on {tls.get('valid_to')}."))
        elif proto in ("TLS 1.0", "TLS 1.1", "SSL 3.0"):
            out.append(_f("connection", "medium", f"Outdated encryption ({proto})",
                          "This protocol version has known weaknesses."))
        else:
            issuer = f" issued by {tls['issuer']}" if tls.get("issuer") else ""
            out.append(_f("connection", "good", "Encrypted connection",
                          f"{proto or 'TLS'} with a valid certificate{issuer}, valid until {tls.get('valid_to')}."))
    mixed = ins.get("mixed_content_requests") or 0
    if mixed:
        out.append(_f("connection", "low", "Some content loaded without encryption",
                      f"{mixed} request{'s' if mixed != 1 else ''} went over plain HTTP from a secure page."))
    headers = ins.get("security_headers")
    if headers:
        present = [h for h, v in headers.items() if v]
        if not any(headers.get(h) for h in ("strict-transport-security", "content-security-policy", "x-frame-options")):
            out.append(_f("connection", "low", "Missing basic security headers",
                          "No HSTS, Content-Security-Policy or frame protection: weaker defence against "
                          "downgrade, script-injection and clickjacking attacks."))
        elif len(present) >= 4:
            out.append(_f("connection", "good", "Strong security headers",
                          f"{len(present)} of 6 recommended security headers are set."))
    status = report.get("http_status")
    if status and status >= 400:
        out.append(_f("connection", "info", f"Page returned an error (HTTP {status})",
                      "The site may be down, blocking automated visits, or the address may be wrong."))
    return out


def _content(ins: dict) -> list[dict]:
    out = []
    content = ins.get("content") or {}
    for cat in content.get("categories") or []:
        rule = CATEGORY_RULES.get(cat["id"])
        if rule:
            sev, title, detail, advice = rule
            if cat.get("evidence"):
                detail += f" (Signals: {', '.join(cat['evidence'][:4])}.)"
            out.append(_f("content", sev, title, detail, advice))
    scam = content.get("scam_phrases") or []
    if len(scam) >= 2:
        out.append(_f("content", "high", "Uses scam-style pressure language",
                      f"Phrases like “{scam[0]}” and “{scam[1]}” are typical of phishing and scam pages.",
                      "Don't act on urgent warnings or prize claims. Contact the company through its official site."))
    elif scam:
        out.append(_f("content", "low", "Some pressure language", f"The page says “{scam[0]}”."))

    foreign = ins.get("foreign_form_domains") or []
    has_password = (ins.get("password_inputs") or 0) > 0
    if foreign and has_password:
        out.append(_f("content", "high", "Login form sends data to another site",
                      f"Your password would be submitted to {', '.join(foreign[:2])}, not to {ins.get('domain')}.",
                      "Don't log in here."))
    elif has_password:
        out.append(_f("content", "info", "Asks for a password", "The page has a login or sign-up form."))
    if (ins.get("card_inputs") or 0) > 0:
        risky = ins.get("tranco_rank") is None and ((ins.get("rdap") or {}).get("age_days") or 0) < 365
        out.append(_f("content", "medium" if risky else "info", "Asks for card details",
                      "The page has payment card fields." + (" The site is new and little-known." if risky else ""),
                      "Pay only on sites you trust, and prefer methods with buyer protection." if risky else None))
    return out


def _behaviour(ins: dict, report: dict) -> list[dict]:
    out = []
    counts = report.get("counts") or {}
    if (ins.get("downloads_attempted") or 0) > 0:
        out.append(_f("behaviour", "high", "Tried to download a file automatically",
                      "The page started a download without being asked (it was blocked). This is how drive-by malware spreads.",
                      "Don't open files this site downloads."))
    if (ins.get("popups_opened") or 0) > 0:
        out.append(_f("behaviour", "medium", "Opens pop-up windows",
                      f"{ins['popups_opened']} pop-up window(s) opened on their own while the page loaded."))
    if (report.get("blocked_destinations") or 0) > 0:
        out.append(_f("behaviour", "medium", "Tried to reach private network addresses",
                      "The page tried to connect to addresses inside a private network. The scanner blocked it."))
    if ins.get("cross_domain_redirect"):
        final = (report.get("final_url") or "").split("/")[2:3]
        out.append(_f("behaviour", "low", "Redirects to a different website",
                      f"You end up on {final[0] if final else 'another domain'} instead of {ins.get('original_domain')}."))
    if (counts.get("redirect_count") or 0) > 3:
        out.append(_f("behaviour", "low", "Long redirect chain", f"{counts['redirect_count']} redirects before the page loaded."))
    if (counts.get("hidden_iframe_count") or 0) > 2:
        out.append(_f("behaviour", "low", "Hidden embedded frames",
                      f"{counts['hidden_iframe_count']} invisible frames, often used for tracking or ad fraud."))
    return out


def _privacy(report: dict, detection: Any) -> list[dict]:
    out = []
    counts = report.get("counts") or {}
    level = _g(detection, "risk_level")
    label = (_g(detection, "label") or "").replace("_", " ")
    if level == "high":
        out.append(_f("privacy", "high", "Heavy, invasive tracking",
                      f"Our model classifies the page as {label} with high confidence.",
                      "Use a tracker-blocking browser or extension on this site."))
    elif level == "medium":
        out.append(_f("privacy", "medium", "Significant tracking", f"Our model classifies the page as {label}.",
                      "Consider a tracker blocker, and reject non-essential cookies."))
    elif level == "suspicious":
        out.append(_f("privacy", "low", "Unusual tracking pattern",
                      "The page doesn't match known tracking profiles, but behaves unlike typical sites."))
    elif level == "low":
        out.append(_f("privacy", "good", "Light tracking", "Tracking is in line with ordinary websites."))

    trackers = report.get("trackers") or []
    n = counts.get("unique_tracker_domains") or 0
    if n:
        owners = []
        for t in trackers:
            if t.get("owner") and t["owner"] not in owners:
                owners.append(t["owner"])
        who = f", including {', '.join(owners[:3])}" if owners else ""
        out.append(_f("privacy", "medium" if n >= 10 else "low", f"{n} tracking domain{'s' if n != 1 else ''}",
                      f"Your visit is reported to {n} known tracker domain{'s' if n != 1 else ''}{who}."))
    if (report.get("insights") or {}).get("adult") and n:
        out.append(_f("privacy", "medium", "Trackers can learn your sexual interests",
                      f"{n} tracker domain{'s' if n != 1 else ''} see this visit. What you watch on adult sites is among "
                      "the most sensitive data that can be collected about you."))
    fp = report.get("fingerprinting") or {}
    if any(fp.get(k) for k in ("canvas_readback_calls", "webgl_unmasked_info_queries", "offline_audio_contexts")):
        out.append(_f("privacy", "medium", "Fingerprints your device",
                      "Scripts read canvas, graphics-card or audio details that can identify your browser without cookies.",
                      "Browsers with fingerprinting protection (Firefox, Brave, Safari) blunt this."))
    tpc = counts.get("third_party_cookies") or 0
    if tpc >= 10:
        out.append(_f("privacy", "low", f"{tpc} third-party cookies", "Other companies set cookies to follow you across sites."))
    return out


def _worst(findings: list[dict]) -> str | None:
    sevs = {f["severity"] for f in findings}
    return next((s for s in SEVERITY_ORDER if s in sevs), None)


NOTHING_FOUND = {"reputation": "No reputation concerns", "connection": "No connection problems",
                 "content": "Nothing concerning on the page", "behaviour": "No pop-ups, forced downloads or odd redirects",
                 "privacy": "No tracking concerns"}


def _category_status(findings: list[dict], cat: str, has_data: bool) -> dict:
    mine = [f for f in findings if f["category"] == cat]
    worst = _worst(mine)
    status = {"critical": "danger", "high": "danger", "medium": "caution", "low": "caution",
              "info": "ok", "good": "good", None: "unknown"}[worst]
    top = next((f for s in SEVERITY_ORDER for f in mine if f["severity"] == s), None)
    if top is None and has_data:
        return {"id": cat, "status": "good", "headline": NOTHING_FOUND[cat]}
    return {"id": cat, "status": status, "headline": top["title"] if top else "Not checked"}


def _summary(ins: dict, report: dict, findings: list[dict], verdict: tuple) -> str:
    domain = ins.get("domain") or report.get("final_url") or "This site"
    parts = []
    cats = [CATEGORY_LABELS[c["id"]] for c in (ins.get("content") or {}).get("categories", []) if c["id"] in CATEGORY_LABELS]
    what = (f"an {cats[0]}" if cats[0][0] in "aeiou" else f"a {cats[0]}") + " website" if cats else "a website"
    rank, age = ins.get("tranco_rank"), (ins.get("rdap") or {}).get("age_days")
    known = []
    if rank:
        known.append(f"ranked #{rank:,} worldwide")
    if age is not None:
        known.append(f"registered {age // 365} year{'s' if age // 365 != 1 else ''} ago" if age >= 365 else f"registered {age} days ago")
    parts.append(f"{domain} is {what}" + (f" ({', '.join(known)})." if known else "."))
    tls = ins.get("tls")
    if ins.get("https") and tls:
        parts.append("The connection is encrypted with a valid certificate.")
    elif ins.get("https") is False:
        parts.append("The connection is not encrypted.")
    n = (report.get("counts") or {}).get("unique_tracker_domains")
    if n:
        parts.append(f"Opening it shares your visit with {n} tracking domain{'s' if n != 1 else ''}.")
    elif n == 0:
        parts.append("No known trackers were contacted.")
    if ins.get("offline"):
        parts.append("The page itself could not be loaded, so only its reputation was checked.")
    concerns = [f["title"].lower() for f in findings if f["severity"] in ("critical", "high", "medium")
                and f["category"] != "privacy"][:2]
    if concerns:
        parts.append(f"Main concern{'s' if len(concerns) > 1 else ''}: {' and '.join(concerns)}.")
    parts.append(verdict[3])
    return " ".join(parts)


def _facts(ins: dict, report: dict) -> list[dict]:
    rd = ins.get("rdap") or {}
    tls = ins.get("tls") or {}
    cats = [CATEGORY_LABELS.get(c["id"], c["id"]) for c in (ins.get("content") or {}).get("categories", [])]
    rows = [
        ("Address", report.get("final_url") or ins.get("domain")),
        ("Popularity", f"#{ins['tranco_rank']:,} worldwide" if ins.get("tranco_rank") else "Not in the top 1M"),
        ("Registered", f"{rd['registered'][:10]}" if rd.get("registered") else None),
        ("Registrar", rd.get("registrar")),
        ("Encryption", tls.get("protocol") or ("None (HTTP)" if ins.get("https") is False else None)),
        ("Certificate", f"{tls.get('issuer')}, until {tls.get('valid_to')}" if tls.get("issuer") else None),
        ("Looks like", ", ".join(cats) if cats else None),
        ("Third-party sites contacted", ins.get("contacted_domains")),
    ]
    return [{"label": k, "value": v} for k, v in rows if v not in (None, "")]


def _is_adult(ins: dict) -> bool:
    return bool(ins.get("adult_listed")) or any(c["id"] == "adult" for c in (ins.get("content") or {}).get("categories", []))


def compose(report: dict, detection: Any) -> dict:
    """`report` without a detection and with offline insights gives a reputation-only report."""
    ins = report.get("insights") or {}
    offline = bool(ins.get("offline"))
    adult = _is_adult(ins)
    if adult:
        content = ins.get("content") or {}
        cats = content.get("categories") or []
        if not any(c["id"] == "adult" for c in cats):
            cats = [{"id": "adult", "evidence": ["known adult website"]}, *cats]
        ins = {**ins, "adult": True, "content": {**content, "categories": cats}}
        report = {**report, "insights": ins}
    findings = _privacy(report, detection)
    if offline:
        findings += _reputation(ins) + _content(ins)
        findings.append(_f("connection", "info", "Couldn't load the website",
                           "The scanner could not open the page: it may be down, blocked in the scanner's country or "
                           "network, or refusing automated visits. Connection, behaviour and tracking were not checked."))
    elif ins:  # reports from before insights existed only have the privacy side
        findings += _reputation(ins) + _connection(ins, report) + _content(ins) + _behaviour(ins, report)
    findings.sort(key=lambda f: SEVERITY_ORDER.index(f["severity"]))

    points = [SEVERITY_POINTS[f["severity"]] for f in findings if f["category"] != "privacy"]
    concerns = sum(p for p in points if p > 0)
    # A good reputation softens concerns but never cancels them: at most half is offset.
    threat = concerns + max(sum(p for p in points if p < 0), -concerns / 2)
    privacy = max(float(_g(detection, "risk_score") or 0),
                  min(100, sum(max(SEVERITY_POINTS[f["severity"]], 0) for f in findings if f["category"] == "privacy")))
    score = max(0.0, min(100.0, threat + 0.3 * privacy))
    worst = _worst([f for f in findings if f["category"] != "privacy"])
    if worst == "critical":
        score = max(score, 85)
    elif worst == "high":
        score = max(score, 55)
    elif worst == "medium":
        score = max(score, 25)
    if adult:
        score = max(score, 50)  # never "safe": 18+ content plus the ad and payment risks that come with it
    verdict = next(v for v in VERDICTS if score >= v[0])
    if adult and verdict[1] == "medium":
        verdict = (verdict[0], "medium", *ADULT_VERDICT)
    elif offline and verdict[1] in OFFLINE_VERDICTS:
        verdict = (verdict[0], "suspicious", *OFFLINE_VERDICTS[verdict[1]])

    advice, seen = list(ADULT_ADVICE) if adult else [], set(ADULT_ADVICE) if adult else set()
    for f in findings:
        if f.get("advice") and f["advice"] not in seen and f["severity"] not in ("good", "info"):
            seen.add(f["advice"])
            advice.append(f["advice"])

    return {
        "version": 1,
        "score": round(score, 1),
        "privacy_score": round(privacy, 1),
        "risk_level": verdict[1],
        "verdict": verdict[2],
        "summary": _summary(ins, report, findings, verdict),
        "categories": [_category_status(findings, c, (c in ("reputation", "content")) if offline else (bool(ins) or c == "privacy"))
                       for c in ("reputation", "connection", "content", "behaviour", "privacy")],
        "findings": findings,
        "advice": advice[:8],
        "adult": adult,
        "offline": offline,
        "facts": _facts(ins, report),
        "limited": not ins,  # True for reports scanned before insights existed
    }
