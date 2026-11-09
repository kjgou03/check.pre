"""③ 배제·제재 대조 (LLM 없음 — 순수 코드).

판정 규칙 (02번 명세):
  목록(NBIM·Urgewald 등) 이름 ≥ 90   → RED     + 목록 행 + IG-5-1, IG-5-2
  목록 이름 점수 80~89                 → YELLOW  "유사 기업 가능, 확인 필요"
  테마 키워드만 걸림                    → YELLOW  "키워드 기반 후보"
  아무것도 없음                         → GREEN   (무엇과 대조했는지를 근거로 남김)
"""
import re

import config
from precheck import data, rules
from precheck.schemas import CheckResult, Evidence, Proposal

KEYWORD_SOURCE = "KIC_theme_keyword"  # 이 source 의 행은 기업이 아니라 테마 키워드


def _as_of(filename: str) -> str:
    return data.load_manifest().get(filename, {}).get("as_of") or "미상"


def _best_matches(p: Proposal, df, min_score: float) -> list[tuple[float, object]]:
    """입력 이름·13F 이름 각각으로 찾아서, 목록 행마다 최고 점수만 남긴다."""
    best = {}
    for name in data.names_for(p.company_name, p.ticker):
        for score, row in data.find_matches(name, df, min_score):
            if score > best.get(row.name, (0, None))[0]:
                best[row.name] = (score, row)
    return sorted(best.values(), key=lambda x: -x[0])


# ── 배제목록 ─────────────────────────────────────────
def match_exclusions(p: Proposal, ex=None) -> list[dict]:
    """배제목록 매칭 결과를 구조화해서 반환. exclusion()·batch.py·impact.py 가 같이 쓴다.

    ex 를 주면 그 목록으로 대조 (모드 B-2: 새 목록만 넣어 보기). 기본은 data/exclusion_list.csv.
    각 원소: {kind: "list"|"keyword", score, company_name, theme, source, source_detail, effective_date}
    """
    ex = data.load_exclusions() if ex is None else ex
    out = []
    # 키워드 행을 뺀 나머지는 전부 '실제 목록' (NBIM, Urgewald, 새로 들어온 목록 …)
    for score, r in _best_matches(p, ex[ex["source"] != KEYWORD_SOURCE], config.FUZZY_YELLOW):
        out.append({"kind": "list", "score": score, **r.drop("norm").to_dict()})

    # 키워드: 정규화된 기업명 + 섹터에 단어 단위로 등장하는지
    text = " ".join(data.names_for(p.company_name, p.ticker)) + " " + (p.sector or "").lower()
    for _, r in ex[ex["source"] == KEYWORD_SOURCE].iterrows():
        if re.search(rf"\b{re.escape(r['company_name'].lower())}\b", text):
            out.append({"kind": "keyword", "score": None, **r.drop("norm").to_dict()})
    return out


def _list_evidence(m: dict) -> Evidence:
    if m["kind"] == "keyword":
        text = f"키워드 '{m['company_name']}' 포함 → 테마 {m['theme']} 후보 | {m['source_detail']}"
    else:
        text = (f"{m['company_name']} | 테마 {m['theme']} | {m['source_detail']} | "
                f"게시일 {m['effective_date'] or '미상'} | 이름 매칭 {m['score']:.0f}점")
    return Evidence(source_type="list", source_id=m["source"], text=text)


def exclusion(p: Proposal) -> CheckResult:
    matches = match_exclusions(p)
    strong = [m for m in matches if m["kind"] == "list" and m["score"] >= config.FUZZY_RED]
    weak = [m for m in matches if m["kind"] == "list" and m["score"] < config.FUZZY_RED]
    keyword = [m for m in matches if m["kind"] == "keyword"]

    if strong:
        sources = ", ".join(dict.fromkeys(m["source"] for m in strong))
        themes = ", ".join(dict.fromkeys(m["theme"] for m in strong))
        return CheckResult(
            check_id="exclusion", signal="RED",
            headline=f"배제목록 해당 — {sources} ({themes})",
            evidence=[_list_evidence(m) for m in strong]
                     + [rules.as_evidence("IG-5-1"), rules.as_evidence("IG-5-2")],
            confidence=strong[0]["score"] / 100,
            next_step="책임투자위원회 사전 심의 [IG-8-1]",
        )
    if weak:
        return CheckResult(
            check_id="exclusion", signal="YELLOW",
            headline="배제목록에 이름이 비슷한 기업 있음 — 동일 기업인지 확인 필요",
            evidence=[_list_evidence(m) for m in weak] + [rules.as_evidence("IG-5-2")],
            confidence=weak[0]["score"] / 100,
            questions=[f"'{p.company_name}'와(과) 배제목록의 '{m['company_name']}'이(가) 같은 기업입니까?"
                       for m in weak],
        )
    if keyword:
        themes = ", ".join(dict.fromkeys(m["theme"] for m in keyword))
        return CheckResult(
            check_id="exclusion", signal="YELLOW",
            headline=f"키워드 기반 후보 ({themes}) — 실제 배제목록 아님, 사업 내용 확인 필요",
            evidence=[_list_evidence(m) for m in keyword] + [rules.as_evidence("IG-5-1")],
            questions=[f"'{p.company_name}'의 {themes} 관련 매출 비중을 확인해 주세요 (IG-5-1 기준)."],
        )

    ex = data.load_exclusions()
    sources = [s for s in dict.fromkeys(ex["source"]) if s != KEYWORD_SOURCE]
    counts = ", ".join(f"{s} {int((ex['source'] == s).sum())}건" for s in sources)
    n_kw = int((ex["source"] == KEYWORD_SOURCE).sum())
    return CheckResult(
        check_id="exclusion", signal="GREEN",
        headline="배제목록·배제 테마 해당 없음",
        evidence=[Evidence(source_type="list", source_id="exclusion_list.csv",
                           text=f"대조 대상: {counts}, 테마 키워드 {n_kw}개 — 해당 없음")],
    )


# ── 제재목록 ─────────────────────────────────────────
def sanctions(p: Proposal) -> CheckResult:
    sa = data.load_sanctions()
    hits = _best_matches(p, sa, config.FUZZY_YELLOW)
    strong = [(s, r) for s, r in hits if s >= config.FUZZY_RED]
    weak = [(s, r) for s, r in hits if s < config.FUZZY_RED]

    def ev(s, r):
        return Evidence(source_type="list", source_id=r["source"],
                        text=f"{r['name']} | 프로그램 {r['program']} | 이름 매칭 {s:.0f}점")

    if strong:
        s, r = strong[0]
        return CheckResult(
            check_id="sanctions", signal="RED",
            headline=f"제재 대상 해당 — {r['name']} ({r['program']})",
            evidence=[ev(s, r) for s, r in strong] + [rules.as_evidence("IG-6-1")],
            confidence=s / 100,
            next_step="투자 불가(제재 대상) — 준법감시부 확인 [IG-6-1]",
        )
    if weak:
        return CheckResult(
            check_id="sanctions", signal="YELLOW",
            headline="제재목록에 이름이 비슷한 대상 있음 — 확인 필요",
            evidence=[ev(s, r) for s, r in weak] + [rules.as_evidence("IG-6-1")],
            confidence=weak[0][0] / 100,
            questions=[f"'{p.company_name}'와(과) 제재 대상 '{r['name']}'이(가) 관련(동일·50% 이상 자회사)이 있습니까?"
                       for _, r in weak],
        )
    return CheckResult(
        check_id="sanctions", signal="GREEN",
        headline="제재목록 해당 없음",
        evidence=[Evidence(source_type="list", source_id="OFAC_SDN",
                           text=f"OFAC SDN {len(sa)}건 대조, 해당 없음 (기준일 {_as_of('sanctions.csv')})")],
    )
