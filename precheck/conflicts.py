"""⑤ 이해상충 — 담당자 개인 보유 종목과 투자안이 겹치는지 (LLM 없음).

  등록 보유 종목과 티커 일치 또는 이름 점수 ≥ 90 → RED + IG-7-1
  등록돼 있고 겹치는 것 없음                       → GREEN (몇 건과 대조했는지 근거로)
  담당자가 아예 미등록                             → UNKNOWN + "등록 후 재점검" 질문
"""
import config
from precheck import data, rules
from precheck.schemas import CheckResult, Evidence, Proposal


def check(p: Proposal) -> CheckResult:
    staff = data.load_staff()
    rows = staff[staff["staff_id"] == p.staff_id]
    if rows.empty:
        return CheckResult(
            check_id="conflict", signal="UNKNOWN",
            headline=f"담당자 {p.staff_id}의 보유내역 미등록 — 판정 불가",
            evidence=[],
            questions=["담당자 보유내역이 등록되어 있지 않습니다. 등록 후 재점검 필요"],
        )

    held = rows[(rows["ticker"] != "") | (rows["company_name"] != "")]
    names = data.names_for(p.company_name, p.ticker)
    hits = []
    for _, r in held.iterrows():
        same_ticker = bool(p.ticker and r["ticker"] and r["ticker"].upper() == p.ticker.upper())
        same_name = any(data.match_score(n, r["norm"]) >= config.FUZZY_RED for n in names)
        if same_ticker or same_name:
            hits.append(r)

    staff_name = rows.iloc[0]["staff_name"]
    if hits:
        return CheckResult(
            check_id="conflict", signal="RED",
            headline=f"{staff_name}({p.staff_id})가 해당 종목 보유 — 이해상충",
            evidence=[Evidence(source_type="db", source_id="staff_holdings",
                               text=f"{p.staff_id} {staff_name} 보유: {r['ticker']} {r['company_name']} "
                                    f"(등록일 {r['registered_at']})") for r in hits]
                     + [rules.as_evidence("IG-7-1")],
            next_step="준법감시부 신고 및 담당자 교체 [IG-8-1]",
        )
    return CheckResult(
        check_id="conflict", signal="GREEN",
        headline="담당자 보유 종목과 겹치지 않음",
        evidence=[Evidence(source_type="db", source_id="staff_holdings",
                           text=f"담당자 {p.staff_id} 등록 보유내역 {len(held)}건 대조, 해당 없음")],
    )
