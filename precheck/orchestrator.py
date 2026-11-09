"""모드 A — 투자안 1건 사전 점검. (기획서 ③ Workflow 의 오케스트레이터)

    입력 ─① intake─▶ Proposal ─┬─② rules.check (법령)    ─┐
                                ├─③ screening.exclusion    ─┤
                                ├─③ screening.sanctions    ─┤  ← ②~⑤ 병렬 실행
                                ├─④ limits.single          ├─▶ ⑥ report.build ─▶ Report ─▶ 감사 로그
                                ├─④ limits.sector          │
                                └─⑤ conflicts.check        ┘

실행 예)
    python -m precheck.orchestrator --company "Altria Group" --amount 15000000000 --staff S002
    python -m precheck.orchestrator --company "Altria Group" --amount 150억 --staff S001
    python -m precheck.orchestrator --text "Altria Group에 150억 투자, 담당자 S001"
"""
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor

from precheck import audit, conflicts, intake, limits, report, rules, screening
from precheck.report import CHECK_LABEL
from precheck.schemas import CheckResult, Evidence, Proposal, Report

# 서로 독립인 점검들. 순서 = 보고서 표 순서
CHECKS = [
    ("law", rules.check),
    ("exclusion", screening.exclusion),
    ("sanctions", screening.sanctions),
    ("limit_single", limits.single),
    ("limit_sector", limits.sector),
    ("conflict", conflicts.check),
]

QUESTION_FOR = {
    "company_name": "투자 대상 기업명을 알려주세요. (LLM 키가 없으면 영문으로. 예: Altria Group)",
    "amount_krw": "투자 금액을 알려주세요. (예: 150억)",
    "staff_id": "담당자 ID를 알려주세요. (예: S001)",
}


def _safe(check_id: str, fn, p: Proposal) -> CheckResult:
    """점검 하나가 실패해도 보고서는 만든다. 단, 조용히 '문제 없음'으로 넘기지 않는다 (침묵 실패 금지).

    UNKNOWN 이 아니라 YELLOW 로 올리는 이유: UNKNOWN 은 GREEN 과 섞이면 종합이 GREEN 이 될 수 있다.
    점검을 못 했는데 종합 '적합'이 나오는 것이 가장 위험한 실패이므로, 사람 확인(YELLOW)으로 올린다.
    """
    try:
        return fn(p)
    except Exception as e:  # noqa: BLE001 — 어떤 오류든 보고서에 드러내는 것이 목적
        print(f"[precheck] {check_id} 점검 실패: {e!r}", file=sys.stderr)
        return CheckResult(
            check_id=check_id, signal="YELLOW",
            headline=f"확인 불가 — 점검 중 오류({type(e).__name__}), 사람 확인 필요",
            evidence=[Evidence(source_type="db", source_id="system_error", text=str(e)[:300])],
            questions=[f"{CHECK_LABEL[check_id]} 점검을 수행하지 못했습니다. 데이터·설정 확인 후 재점검 필요"],
        )


def run_checks(p: Proposal) -> list[CheckResult]:
    """6개 점검을 병렬로 실행 (서로 독립이라 순서 무관). 결과는 CHECKS 순서대로."""
    with ThreadPoolExecutor(max_workers=len(CHECKS)) as pool:
        futures = [pool.submit(_safe, check_id, fn, p) for check_id, fn in CHECKS]
        return [f.result() for f in futures]


def run(text: str | None = None, *, company: str | None = None, amount_krw: float | None = None,
        staff_id: str | None = None, memo: str | None = None) -> Report | list[str]:
    """Report 를 돌려준다. 필수 정보가 빠졌으면 대신 '질문 목록'(list[str])을 돌려주고 멈춘다."""
    p = intake.parse(text) if text else intake.from_fields(company, amount_krw, staff_id, memo)
    if p.missing_fields:
        return [QUESTION_FOR[f] for f in p.missing_fields]
    r = report.build(p, run_checks(p))
    audit.log("A", r.model_dump(mode="json"), company=p.company_name, staff_id=p.staff_id,
              overall=r.overall, sources=r.sources_used)
    return r


def _amount(s: str) -> float:
    try:
        return float(s.replace(",", ""))
    except ValueError:
        v = intake.parse_amount_krw(s)
        if v is None:
            raise argparse.ArgumentTypeError(f"금액을 읽을 수 없습니다: {s}")
        return v


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="PreCheck 모드 A — 투자안 사전 점검")
    ap.add_argument("--text", help="자유 입력 (예: 'Altria Group에 150억 투자, 담당자 S001')")
    ap.add_argument("--company", help="기업명")
    ap.add_argument("--amount", type=_amount, help="금액(원). 15000000000 또는 150억")
    ap.add_argument("--staff", help="담당자 ID (예: S001)")
    ap.add_argument("--memo")
    ap.add_argument("--json", action="store_true", help="Markdown 대신 JSON 출력")
    args = ap.parse_args(argv)
    if not (args.text or args.company):
        ap.error("--text 또는 --company 가 필요합니다")

    result = run(args.text, company=args.company, amount_krw=args.amount, staff_id=args.staff, memo=args.memo)
    if isinstance(result, list):
        print("점검을 시작하려면 다음 정보가 필요합니다:")
        print("\n".join(f"- {q}" for q in result))
        return 2
    print(result.model_dump_json(indent=2) if args.json else report.to_markdown(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
