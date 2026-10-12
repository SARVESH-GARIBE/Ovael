"""Label suggestions for the review queue.

A suggestion is a proposal for the reviewer, never a label: nothing trains until a person
confirms it (one by one, or with "Accept all"). Each suggestion says where it came from, so the
reviewer can judge it. In order:

  1. similar  - the item is close (log-scaled feature space, k=3 nearest neighbours) to flows a
                person already confirmed, and those neighbours agree on a label. "Close" means
                within the distance at which confirmed flows of the same label sit from each other.
  2. second   - the classifier gave an attack class the active model still knows a real share
                (>= 20%).
  3. normal   - the classifier is confident the flow is normal (>= 90%) and nothing above
                applies: most likely a false alarm of the anomaly detector.
  4. none     - no basis for a suggestion; the reviewer has to decide.
"""

from __future__ import annotations

import numpy as np

from ..feature_extraction import SCHEMAS

K = 3
RADIUS_SAMPLE = 300
SECOND_GUESS_MIN = 0.20
NORMAL_MIN = 0.90


def _matrix(rows: list[dict], cols: list[str]) -> np.ndarray:
    X = np.array([[float(r.get(c) or 0.0) for c in cols] for r in rows], dtype=float)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    return np.log1p(np.clip(X, 0, None))


def suggest(module: str, pending: list, confirmed: list, benign_labels: set[str],
            known_classes: set[str] | None = None) -> dict[str, dict]:
    cols = SCHEMAS[module]
    out: dict[str, dict] = {}

    ref = [c for c in confirmed if c.final_label]
    ref_X = _matrix([c.features for c in ref], cols) if ref else None
    ref_y = np.array([c.final_label for c in ref]) if ref else None
    radius = None
    if ref_X is not None and len(ref) > K:
        # typical distance between a confirmed flow and its nearest same-label neighbour,
        # measured on at most RADIUS_SAMPLE flows so memory stays small
        pick = np.random.default_rng(0).permutation(len(ref))[:RADIUS_SAMPLE]
        sx, sy = ref_X[pick], ref_y[pick]
        d = np.sqrt(((sx[:, None, :] - sx[None, :, :]) ** 2).sum(-1))
        np.fill_diagonal(d, np.inf)
        same = sy[:, None] == sy[None, :]
        nn = np.where(same, d, np.inf).min(axis=1)
        nn = nn[np.isfinite(nn)]
        radius = float(np.percentile(nn, 90)) if len(nn) else None

    X = _matrix([p.features for p in pending], cols) if pending else np.zeros((0, len(cols)))
    for i, item in enumerate(pending):
        ctx = item.context or {}
        probs: dict = ctx.get("probabilities") or {}

        if radius is not None:
            dist = np.sqrt(((ref_X - X[i]) ** 2).sum(-1))
            idx = np.argsort(dist)[:K]
            labels = set(ref_y[idx])
            if len(labels) == 1 and dist[idx].mean() <= radius:
                label = ref_y[idx[0]]
                n_same = int((ref_y == label).sum())
                out[item.id] = {"label": str(label), "source": "similar",
                                "reason": f"looks like {n_same} flows you confirmed as {label}"}
                continue

        # Probabilities were stored when the item was queued, possibly by an older model; only
        # classes the active model still knows are worth suggesting.
        attacks = sorted(((p, c) for c, p in probs.items()
                          if c not in benign_labels and (known_classes is None or c in known_classes)),
                         reverse=True)
        if attacks and attacks[0][0] >= SECOND_GUESS_MIN:
            p, label = attacks[0]
            out[item.id] = {"label": label, "source": "second",
                            "reason": f"classifier's next guess ({round(p * 100)}%)"}
            continue

        conf = float(ctx.get("confidence") or 0)
        if item.predicted_label in benign_labels and conf >= NORMAL_MIN:
            out[item.id] = {"label": item.predicted_label, "source": "normal",
                            "reason": f"classifier {round(conf * 100)}% sure it is normal; likely a false alarm"}
            continue

        out[item.id] = {"label": None, "source": "none", "reason": "no basis for a suggestion"}
    return out
