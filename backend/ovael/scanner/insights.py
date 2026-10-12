"""Raw signals for the smart report, gathered in the scanner next to the browser visit.

Everything here is an observation (what the page is, who it talks to, how it is served); the
judgement - severities, the verdict and the wording - is made in services/smart_report.py so it
can be tuned without touching the scanner. Page text is classified here and never leaves the
scanner: only the matched categories and keywords do.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from . import reputation

# Category -> keyword patterns, matched case-insensitively on the domain, title, description and
# the first few thousand characters of visible text. Two or more distinct hits (or one in the
# domain/title) are needed for a category to count.
CATEGORIES: dict[str, list[str]] = {
    "gambling": [r"casino", r"\bbet(ting|s)?\b", r"poker", r"rummy", r"teen ?patti", r"jackpot", r"slots?\b",
                 r"roulette", r"lottery", r"sportsbook", r"real money", r"win (real )?cash", r"fantasy (sports|cricket|league)",
                 r"deposit bonus", r"cash games?", r"wager", r"gambl"],
    "adult": [r"\bporn", r"\bxxx", r"\bsex\b", r"\bnsfw\b", r"escort", r"\badult (content|videos?)\b", r"nude", r"18\+ only",
              r"hentai", r"\bmilf\b", r"\bcam ?girls?\b", r"\blive (sex )?cams\b", r"\bnaked\b"],
    "crypto_investment": [r"crypto", r"bitcoin", r"\bbtc\b", r"ethereum", r"airdrop", r"\bnft", r"forex", r"trading signals?",
                          r"guaranteed (returns?|profit)", r"double your", r"\bdefi\b", r"connect (your )?wallet", r"seed phrase"],
    "loans": [r"instant loan", r"personal loan", r"loan app", r"credit line", r"no credit check", r"payday"],
    "piracy": [r"torrent", r"watch free", r"free movies", r"\bwarez\b", r"crack(ed)? (version|software)", r"mod apk", r"keygen"],
    "dating": [r"dating", r"singles? near", r"hookup", r"meet (women|men|singles)"],
    "social": [r"followers", r"\bstories\b", r"\breels\b", r"social network", r"sign up to see photos", r"friends"],
    "shopping": [r"add to cart", r"\bcheckout\b", r"free shipping", r"\bdeals?\b", r"shop now", r"buy now"],
    "banking": [r"net ?banking", r"online banking", r"\bbank\b", r"credit card", r"account number", r"\bifsc\b"],
    "news": [r"breaking news", r"\bheadlines\b", r"latest news", r"editorial", r"opinion"],
}

# Phrases phishing and scam pages lean on: urgency, prizes, credential requests.
SCAM_PHRASES = [r"verify your (account|identity)", r"account (has been )?(suspended|locked|limited)", r"unusual (sign-?in )?activity",
                r"confirm your (password|payment|details)", r"you have won", r"claim your (prize|reward|gift)",
                r"congratulations[,!]? you", r"act now", r"limited time offer", r"gift card", r"update your (payment|billing)",
                r"within 24 hours", r"your (device|computer) (is|has been) infected", r"call (this number|now|support)",
                r"double your (money|bitcoin|crypto)", r"send .{0,20}(btc|bitcoin|usdt)"]

SUSPICIOUS_TLDS = {"zip", "mov", "xyz", "top", "click", "country", "gq", "tk", "ml", "cf", "ga", "work", "rest",
                   "cam", "icu", "buzz", "fit", "lol", "sbs", "cfd", "cyou", "quest", "bond", "monster", "support"}


def classify_content(domain: str, title: str | None, content: dict | None, adult_listed: bool = False) -> dict:
    content = content or {}
    head = " ".join(filter(None, [domain.replace("-", " ").replace(".", " "), title, content.get("site_name")])).lower()
    body = " ".join(filter(None, [content.get("description"), content.get("text_sample")])).lower()
    categories = []
    for cat, patterns in CATEGORIES.items():
        hits_head = {p for p in patterns if re.search(p, head)}
        hits_body = {p for p in patterns if re.search(p, body)}
        hits = hits_head | hits_body
        if hits_head or len(hits) >= 2:
            words = sorted({m.group(0).strip() for p in hits for m in [re.search(p, head) or re.search(p, body)] if m})
            categories.append({"id": cat, "evidence": words[:6], "strength": len(hits) + 2 * len(hits_head)})
    if adult_listed:  # the curated list beats keywords: age gates show almost no text
        categories = [c for c in categories if c["id"] != "adult"]
        categories.append({"id": "adult", "evidence": ["known adult website"], "strength": 100})
    categories.sort(key=lambda c: -c["strength"])
    scam = sorted({m.group(0) for p in SCAM_PHRASES if (m := re.search(p, head + " " + body))})
    return {"categories": categories[:3], "scam_phrases": scam[:8]}


def _tls_summary(tls: dict | None) -> dict | None:
    if not tls:
        return None
    out = {"issuer": tls.get("issuer"), "protocol": tls.get("protocol"), "subject": tls.get("subjectName"),
           "valid_from": None, "valid_to": None, "days_left": None, "age_days": None}
    now = datetime.now(timezone.utc).timestamp()
    if tls.get("validFrom"):
        out["valid_from"] = datetime.fromtimestamp(tls["validFrom"], timezone.utc).date().isoformat()
        out["age_days"] = int((now - tls["validFrom"]) // 86400)
    if tls.get("validTo"):
        out["valid_to"] = datetime.fromtimestamp(tls["validTo"], timezone.utc).date().isoformat()
        out["days_left"] = int((tls["validTo"] - now) // 86400)
    return out


async def gather(rec: dict, attempt_data: dict, original_host: str, original_domain: str) -> dict:
    final = rec.get("final") or {}
    final_url = final.get("url") or ""
    final_domain = final.get("registrable_domain") or original_domain
    signals = attempt_data.get("page_signals") or {}
    content = signals.get("content") or {}
    requests = attempt_data.get("requests") or []
    nav = rec.get("navigation") or {}

    adult = reputation.is_adult_domain(final_domain) or reputation.is_adult_domain(original_host)
    rank = reputation.tranco().rank(final_domain)
    lookalike = reputation.lookalike_of(final_domain, rank)
    contacted = sorted({q["hostname"] for q in requests if q.get("hostname")})
    malware_hosts = reputation.malware_listed([original_host, final.get("hostname") or "", *contacted])

    form_domains = set()
    for action in content.get("form_actions") or []:
        m = re.match(r"https?://([^/:]+)", action)
        if m:
            form_domains.add(reputation_domain(m.group(1)))
    foreign_forms = sorted(d for d in form_domains if d and d != final_domain)

    https = final_url.startswith("https://")
    mixed = sum(1 for q in requests if https and q.get("scheme") == "http") if https else 0

    return {
        "domain": final_domain,
        "original_domain": original_domain,
        "tld": final_domain.rsplit(".", 1)[-1],
        "suspicious_tld": final_domain.rsplit(".", 1)[-1] in SUSPICIOUS_TLDS,
        "punycode": "xn--" in (final.get("hostname") or original_host),
        "subdomain_depth": max(len((final.get("hostname") or "").split(".")) - len(final_domain.split(".")), 0),
        "tranco_rank": rank,
        "lookalike": lookalike,
        "malware_hosts": malware_hosts,
        "rdap": await reputation.rdap(final_domain),
        "https": https,
        "mixed_content_requests": mixed,
        "tls": _tls_summary(signals.get("tls")),
        "security_headers": signals.get("security_headers"),
        "content": classify_content(final_domain, final.get("title"), content, adult),
        "adult_listed": adult,
        "lang": content.get("lang"),
        "password_inputs": content.get("password_inputs"),
        "card_inputs": content.get("card_inputs"),
        "foreign_form_domains": foreign_forms,
        "cross_domain_redirect": bool(nav.get("cross_domain_redirect")),
        "popups_opened": nav.get("popups_opened"),
        "downloads_attempted": nav.get("downloads_blocked"),
        "contacted_domains": len({reputation_domain(h) for h in contacted}),
    }


async def offline(hostname: str, domain: str) -> dict:
    """What can be said without loading the page, for scans the browser could not complete
    (site down, ISP-blocked, timed out): lists, rank, lookalikes and domain age only."""
    adult = reputation.is_adult_domain(hostname)
    rank = reputation.tranco().rank(domain)
    return {
        "offline": True,
        "domain": domain,
        "original_domain": domain,
        "tld": domain.rsplit(".", 1)[-1],
        "suspicious_tld": domain.rsplit(".", 1)[-1] in SUSPICIOUS_TLDS,
        "punycode": "xn--" in hostname,
        "tranco_rank": rank,
        "lookalike": reputation.lookalike_of(domain, rank),
        "malware_hosts": reputation.malware_listed([hostname, domain]),
        "rdap": await reputation.rdap(domain, timeout_s=5.0),
        "content": classify_content(domain, None, None, adult),
        "adult_listed": adult,
    }


def reputation_domain(host: str) -> str:
    from .url_guard import _extract  # noqa: PLC0415

    ext = _extract(host)
    return f"{ext.domain}.{ext.suffix}" if ext.suffix else host
