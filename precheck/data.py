"""데이터 로더 + 이름 정규화/매칭 유틸.

- 모든 CSV는 문자열로 읽는다(dtype=str). 빈칸은 NaN 대신 "" → 초보자가 헷갈리는 NaN 처리 회피.
- 한 번 읽은 파일은 캐시(lru_cache). 배치 모드에서 수십 번 불려도 디스크는 한 번만 읽는다.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz, process

import config


# ── 파일 읽기 ─────────────────────────────────────────
def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"데이터 파일이 없습니다: {path}\n→ data/README.md 의 준비 방법을 참고하세요.")
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")


@lru_cache
def load_holdings() -> pd.DataFrame:
    df = _read_csv(config.HOLDINGS_CSV)
    df["value_usd"] = df["value_usd"].astype(int)
    df["shares"] = df["shares"].astype(int)
    df["norm"] = df["issuer_name"].map(normalize_name)
    return df


@lru_cache
def load_exclusions() -> pd.DataFrame:
    df = _read_csv(config.EXCLUSION_CSV)
    df["norm"] = df["company_name"].map(normalize_name)
    return df


@lru_cache
def load_sanctions() -> pd.DataFrame:
    df = _read_csv(config.SANCTIONS_CSV)
    df["norm"] = df["name"].map(normalize_name)
    return df


@lru_cache
def load_staff() -> pd.DataFrame:
    # ticker·company_name 이 비어 있는 행 = "보유 없음"으로 등록된 담당자
    df = _read_csv(config.STAFF_CSV)
    df["norm"] = df["company_name"].map(normalize_name)
    return df


@lru_cache
def load_rules() -> tuple[dict, ...]:
    rules = []
    for path in config.RULE_FILES:
        if not path.exists():
            raise FileNotFoundError(f"규정 파일이 없습니다: {path}")
        rules.extend(json.loads(path.read_text(encoding="utf-8")))
    ids = [r["rule_id"] for r in rules]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise ValueError(f"rule_id 중복: {dup}")
    return tuple(rules)


@lru_cache
def load_manifest() -> dict:
    m = json.loads(config.MANIFEST_JSON.read_text(encoding="utf-8"))
    return {k: v for k, v in m.items() if not k.startswith("_")}


# ── 이름 정규화 ───────────────────────────────────────
# 13F 발행사명은 "PHILIP MORRIS INTL INC", "BRITISH AMERN TOB PLC SPONSORED ADR" 처럼 줄임말투성이.
# 목록 쪽은 "Philip Morris International Inc." → 둘 다 같은 모양으로 바꿔야 비교가 된다.
_ABBREV = {
    "intl": "international", "amern": "american", "amer": "american", "tob": "tobacco",
    "elec": "electric", "pwr": "power", "hldgs": "holdings", "hldg": "holdings",
    "whsl": "wholesale", "sys": "systems", "natl": "national", "instrs": "instruments",
    "machs": "machines", "pac": "pacific", "cos": "companies",
}
# 법인 접미사·주식 종류 등 '회사를 구별하지 못하는' 단어
_DROP = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "companies", "ltd", "limited",
    "plc", "group", "holdings", "lp", "llc", "sa", "ag", "nv", "se", "the", "and", "new", "del",
    "cl", "class", "a", "b", "com", "stk", "cap", "adr", "ads", "sponsored", "spon", "shs",
    "public", "joint", "stock", "pjsc", "pao", "jsc", "oao",
}


def normalize_name(s: str) -> str:
    """'BRITISH AMERN TOB PLC SPONSORED ADR' → 'british american tobacco'"""
    s = (s or "").lower().replace("&", " and ")
    s = re.sub(r"[^\w\s]", " ", s)  # 구두점 → 공백
    tokens = [_ABBREV.get(t, t) for t in s.split()]
    return " ".join(t for t in tokens if t not in _DROP)


def match_score(a: str, b: str) -> float:
    """정규화된 두 이름의 유사도(0~100). 배제·제재·이해상충 판정에 쓰는 '엄격한' 점수.

    token_set_ratio 만 쓰면 한쪽이 다른 쪽의 부분집합일 때 100점이 나온다.
      예) 'southern'(Southern Co, 석탄 발전) ⊂ 'southern copper'(구리 광산) → 100점 → 오탐 RED
    그래서 어순만 무시하는 token_sort_ratio 와 평균을 내서, 부분 일치는 80점대(YELLOW, 확인 필요)로 내린다.
    """
    if not a or not b:
        return 0.0
    return (fuzz.token_set_ratio(a, b) + fuzz.token_sort_ratio(a, b)) / 2


def find_matches(name_norm: str, df: pd.DataFrame, min_score: float) -> list[tuple[float, pd.Series]]:
    """df['norm'] 중 name_norm 과 match_score ≥ min_score 인 행들을 (점수, 행) 으로 반환 (점수 내림차순)."""
    if not name_norm or df.empty:
        return []
    # 1차: 빠른 C 구현으로 후보만 거른다 (match_score ≤ token_set_ratio 이므로 놓치는 후보 없음)
    cands = process.extract(name_norm, df["norm"].tolist(), scorer=fuzz.token_set_ratio,
                            score_cutoff=min_score, limit=None)
    out = []
    for _, _, idx in cands:
        score = match_score(name_norm, df.iloc[idx]["norm"])
        if score >= min_score:
            out.append((score, df.iloc[idx]))
    return sorted(out, key=lambda x: -x[0])
