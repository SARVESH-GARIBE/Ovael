"""Labels for the website dataset.

The crawler dataset has no ground-truth labels (`security_label` is empty for every row). Until
reviewers label sites, rows get a *weak label* from documented rules over the DuckDuckGo Tracker
Data Set matches and the fingerprinting counters:

    invasive_tracker  any fingerprinting readback (canvas pixels, unmasked GPU, offline audio),
                      session-replay trackers, or requests to hosts the reference tags as malware
    tracker           requests to advertising / analytics / ad-motivated tracking domains,
                      or third-party cookies set by tracker domains
    benign            neither of the above

Limitation, stated plainly: the classifier is trained on features that the rules themselves read,
so at first it reproduces the rules. That is intended; it is the starting point the learning loop
replaces. Labels that a person confirmed in the review queue, and any `manual_review_label` /
`security_label` already in the CSV, always take precedence over the weak label.
"""

from __future__ import annotations

import pandas as pd

WEAK_LABEL_SOURCE = "weak_rules_v1"
USABLE_STATUSES = {"success", "http_error"}


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df:
        return pd.Series(0, index=df.index)
    return pd.to_numeric(df[col], errors="coerce").fillna(0)


def weak_label(df: pd.DataFrame) -> pd.Series:
    invasive = (
        (_num(df, "canvas_readback_calls") > 0)
        | (_num(df, "webgl_unmasked_info_queries") > 0)
        | (_num(df, "offline_audio_contexts") > 0)
        | (_num(df, "tracker_requests_cat_session_replay") > 0)
        | (_num(df, "tracker_requests_cat_malware") > 0)
    )
    tracking = (
        (_num(df, "tracker_requests_cat_advertising") > 0)
        | (_num(df, "tracker_requests_cat_analytics") > 0)
        | (_num(df, "tracker_requests_cat_ad_motivated_tracking") > 0)
        | ((_num(df, "third_party_cookies") > 0) & (_num(df, "unique_tracker_domains") > 0))
    )
    labels = pd.Series("benign", index=df.index)
    labels[tracking] = "tracker"
    labels[invasive] = "invasive_tracker"
    return labels


def label_website_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """Keep rows whose page was actually observed and attach `label` + `label_source`."""
    df = df[df["crawl_status"].isin(USABLE_STATUSES)].copy()
    if "instrumentation_status" in df:
        df = df[df["instrumentation_status"] == "ok"]
    df["label"] = weak_label(df)
    df["label_source"] = WEAK_LABEL_SOURCE
    for col in ("security_label", "manual_review_label"):
        if col in df:
            human = df[col].fillna("").astype(str).str.strip()
            mask = human != ""
            df.loc[mask, "label"] = human[mask]
            df.loc[mask, "label_source"] = col
    return df
