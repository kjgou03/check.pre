"""모드 A — 투자안 1건 사전 점검.

    입력 ─① intake─▶ Proposal ─┬─③ screening.exclusion ─┐
                                ├─③ screening.sanctions ─┤
                                ├─④ limits.single        ├─▶ ⑥ report.build ─▶ Report
                                ├─④ limits.sector        │
                                └─⑤ conflicts.check      ┘

실행 예)
    python -m precheck.orchestrator --company "Altria Group" --amount 15000000000 --staff S002
    python -m precheck.orchestrator --company "Altria Group" --amount 150억 --staff S001
    python -m precheck.orchestrator --text "Altria Group에 150억 투자, 담당자 S001"
"""
import argparse
import sys

from precheck import conflicts, intake, limits, report, screening
from precheck.schemas import CheckResult, Proposal, Report

QUESTION_FOR = {
    "company_name": "투자 대상 기업명을 알려주세요. (LLM 키가 없으면 영문으로. 예: Altria Group)",
    "amount_krw": "투자 금액을 알려주세요. (예: 150억)",
    "staff_id": "담당자 ID를 알려주세요. (예: S001)",
}


def run_checks(p: Proposal) -> list[CheckResult]:
    # (선택) 법령 점검 'law' 는 kic_act_sample.json 이 채워지면 rules.get_by_category("law") 로 추가
    return [screening.exclusion(p), screening.sanctions(p),
            limits.single(p), limits.sector(p), conflicts.check(p)]


def run(text: str | None = None, *, company: str | None = None, amount_krw: float | None = None,
        staff_id: str | None = None, memo: str | None = None) -> Report | list[str]:
    """Report 를 돌려준다. 필수 정보가 빠졌으면 대신 '질문 목록'(list[str])을 돌려주고 멈춘다."""
    p = intake.parse(text) if text else intake.from_fields(company, amount_krw, staff_id, memo)
    if p.missing_fields:
        return [QUESTION_FOR[f] for f in p.missing_fields]
    return report.build(p, run_checks(p))


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
