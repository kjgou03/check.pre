"""Step 1 완료 조건 = 01번 문서의 '데이터 준비 완료 조건' 4개."""
import pandas as pd

import config
from precheck import data


def test_holdings_has_tobacco_name():
    names = data.load_holdings()["issuer_name"].str.upper()
    assert names.str.contains("ALTRIA").any() or names.str.contains("PHILIP MORRIS").any()


def test_at_least_5_holdings_match_exclusion_lists():
    ex = data.load_exclusions()
    ex = ex[ex.source.isin(["NBIM", "Urgewald_GCEL_2025"])]
    matched = [n for n in data.load_holdings()["norm"]
               if data.find_matches(n, ex, config.FUZZY_RED)]
    assert len(matched) >= 5, matched


def test_internal_guideline_has_8_rules():
    ig = [r for r in data.load_rules() if r["rule_id"].startswith("IG-")]
    assert len(ig) == 8


def test_all_csv_readable_utf8():
    for p in [config.HOLDINGS_CSV, config.EXCLUSION_CSV, config.SANCTIONS_CSV, config.STAFF_CSV]:
        pd.read_csv(p, encoding="utf-8")


def test_normalize_handles_13f_abbreviations():
    assert data.normalize_name("BRITISH AMERN TOB PLC SPONSORED ADR") == "british american tobacco"
    assert data.normalize_name("PHILIP MORRIS INTL INC") == data.normalize_name("Philip Morris International Inc.")


def test_subset_name_is_not_full_match():
    # Southern Co(석탄) 와 Southern Copper(구리)는 동일 기업으로 판정하면 안 된다
    score = data.match_score("southern", "southern copper")
    assert config.FUZZY_YELLOW <= score < config.FUZZY_RED
