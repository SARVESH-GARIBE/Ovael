"""Locks in A10: the website model is trained without any of the 16 label-rule features."""
from __future__ import annotations

from ovael.feature_extraction import SCHEMAS
from ovael.feature_extraction.website_schema import LABEL_RULE_FEATURES, WEBSITE_FEATURES


def test_website_schema_excludes_every_label_rule_feature():
    overlap = set(WEBSITE_FEATURES) & set(LABEL_RULE_FEATURES)
    assert overlap == set(), f"label-rule features leaked into the model schema: {overlap}"


def test_schemas_dict_used_by_training_is_the_same_object():
    # SCHEMAS["website"] is what ml/train.py actually selects columns with (ml/train.py:58).
    assert SCHEMAS["website"] is WEBSITE_FEATURES
    assert set(SCHEMAS["website"]) & set(LABEL_RULE_FEATURES) == set()
