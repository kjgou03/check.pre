"""④ 한도·비중 계산 (LLM 절대 금지 — 숫자는 코드만 만든다).

  추가 후 비중 > 한도(IG-3-1, 3%)          → RED    + "리스크관리위원회 승인"
  추가 후 비중 > 한도 × 0.8(IG-3-3)        → YELLOW + "리스크관리부 사전 보고"
  그 외                                    → GREEN
한도 숫자(3.0, 0.8)는 코드에 박지 않고 규정 JSON의 param 에서 읽는다.
"""
import config
from precheck import data, rules
from precheck.schemas import CheckResult, Evidence, Proposal


def _add_usd(p: Proposal) -> float:
    return p.amount_usd if p.amount_usd is not None else p.amount_krw / config.FX_KRW_USD


def single(p: Proposal) -> CheckResult:
    h = data.load_holdings()
    total = float(h["value_usd"].sum())
    current = float(h.loc[h["ticker"] == p.ticker, "value_usd"].sum()) if p.ticker else 0.0
    add = _add_usd(p)

    before_pct = current / total * 100
    after_pct = (current + add) / (total + add) * 100
    limit = rules.param("IG-3-1", "max_pct")
    warn = limit * rules.param("IG-3-3", "ratio")

    held_note = "" if current else " — 보유내역에 없음(신규 편입)"
    evidence = [
        Evidence(source_type="calc", source_id="single_issuer_pct",
                 text=f"현재 {before_pct:.2f}% → 추가 후 {after_pct:.2f}% (한도 {limit:g}%, 보고 기준 {warn:.2f}%)"),
        Evidence(source_type="calc", source_id="single_issuer_inputs",
                 text=f"보유 ${current:,.0f} + 추가 ${add:,.0f} (환율 {config.FX_KRW_USD:,}원/$) "
                      f"/ 포트폴리오 ${total:,.0f}{held_note}"),
        rules.as_evidence("IG-3-1"),
    ]

    if after_pct > limit:
        return CheckResult(check_id="limit_single", signal="RED",
                           headline=f"단일종목 한도 초과 — 추가 후 {after_pct:.2f}% > 한도 {limit:g}%",
                           evidence=evidence, next_step="리스크관리위원회 승인 [IG-8-1]")
    if after_pct > warn:
        return CheckResult(check_id="limit_single", signal="YELLOW",
                           headline=f"한도 근접 — 추가 후 {after_pct:.2f}% (보고 기준 {warn:.2f}% 초과)",
                           evidence=evidence + [rules.as_evidence("IG-3-3")],
                           next_step="투자 실행 전 리스크관리부 보고 [IG-3-3]")
    return CheckResult(check_id="limit_single", signal="GREEN",
                       headline=f"단일종목 비중 추가 후 {after_pct:.2f}% — 한도 {limit:g}% 이내",
                       evidence=evidence)


def sector(p: Proposal) -> CheckResult:
    """IG-3-2 는 '벤치마크 대비 ±5%p' 인데 벤치마크 섹터 비중 데이터가 없다.
    → 판정은 UNKNOWN 으로 두되, 계산 가능한 '우리 포트폴리오 내 섹터 비중'은 근거로 보여준다. (숨기지 않기)"""
    if not p.sector:
        return CheckResult(check_id="limit_sector", signal="UNKNOWN",
                           headline="섹터 정보 없음 — 섹터 한도 판정 불가", evidence=[],
                           questions=["투자 대상의 GICS 섹터를 알려주시면 섹터 비중을 계산할 수 있습니다."])

    h = data.load_holdings()
    total = float(h["value_usd"].sum())
    in_sector = float(h.loc[h["sector"] == p.sector, "value_usd"].sum())
    add = _add_usd(p)
    before_pct = in_sector / total * 100
    after_pct = (in_sector + add) / (total + add) * 100
    # TODO: data/benchmark_sectors.csv 가 생기면 여기서 |after_pct - 벤치마크| > max_pp 비교 → RED/GREEN
    return CheckResult(
        check_id="limit_sector", signal="UNKNOWN",
        headline="벤치마크 비중 데이터 없음 — 섹터 한도(±5%p) 판정 불가",
        evidence=[Evidence(source_type="calc", source_id="sector_pct",
                           text=f"포트폴리오 내 {p.sector} 비중: 현재 {before_pct:.2f}% → 추가 후 {after_pct:.2f}% "
                                f"(벤치마크 비중 데이터 없음)"),
                  rules.as_evidence("IG-3-2")],
    )
