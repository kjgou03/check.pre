"""Step 4 완료 조건: 보고서 조립 + 근거 검증 (키 없이 실행)."""
import pytest
from pydantic import ValidationError

from precheck import conflicts, limits, llm, report, screening
from precheck.schemas import CheckResult, Evidence, Proposal


def _c(signal, check_id="exclusion"):
    ev = [Evidence(source_type="rule", source_id="IG-5-1", text="...")] if signal in ("RED", "YELLOW") else []
    return CheckResult(check_id=check_id, signal=signal, headline="h", evidence=ev)


def _altria_checks():
    p = Proposal(company_name="Altria Group", ticker="MO", sector="Consumer Staples",
                 amount_krw=15e9, amount_usd=15e9 / 1400, staff_id="S002")
    checks = [screening.exclusion(p), screening.sanctions(p), limits.single(p), limits.sector(p), conflicts.check(p)]
    return p, checks


def test_red_without_evidence_is_rejected():
    with pytest.raises(ValidationError):
        CheckResult(check_id="exclusion", signal="RED", headline="x", evidence=[])


@pytest.mark.parametrize("signals, expected", [
    (["GREEN", "RED", "YELLOW"], "RED"),
    (["GREEN", "YELLOW", "UNKNOWN"], "YELLOW"),
    (["UNKNOWN", "UNKNOWN"], "YELLOW"),
    (["GREEN", "GREEN", "UNKNOWN"], "GREEN"),
])
def test_overall_logic(signals, expected):
    assert report.decide_overall([_c(s) for s in signals]) == expected


def test_fake_rule_citation_is_caught():
    p, checks = _altria_checks()
    problems = report.validate_summary("이 투자안은 [IG-9-9]에 따라 금지됩니다.", checks, p)
    assert any("IG-9-9" in x for x in problems)


def test_fake_number_is_caught():
    p, checks = _altria_checks()
    problems = report.validate_summary("추가 후 비중은 7.77%입니다.", checks, p)
    assert any("7.77" in x for x in problems)


def test_hallucinated_llm_summary_falls_back_to_template(monkeypatch):
    # LLM 이 계속 가짜 조항을 쓴다고 가정 → 재생성 2회 후 템플릿으로 대체되어야 함
    calls = []
    monkeypatch.setattr(llm, "complete", lambda *a, **k: calls.append(1) or "[IG-9-9]에 따라 투자 불가입니다.")
    p, checks = _altria_checks()
    r = report.build(p, checks)
    assert "IG-9-9" not in r.summary
    assert r.summary.startswith("점검 5개 항목 중")
    assert len(calls) == 3  # 최초 1회 + 재생성 2회


def test_valid_llm_summary_is_kept(monkeypatch):
    good = "Altria Group은 NBIM 배제목록에 해당하여 [IG-5-1]에 따라 책임투자위원회 사전 심의가 필요합니다."
    monkeypatch.setattr(llm, "complete", lambda *a, **k: good)
    p, checks = _altria_checks()
    assert report.build(p, checks).summary == good


def test_template_summary_passes_own_validation():
    p, checks = _altria_checks()
    overall = report.decide_overall(checks)
    assert report.validate_summary(report.template_summary(checks, overall), checks, p) == []


def test_markdown_has_disclaimer():
    p, checks = _altria_checks()
    md = report.to_markdown(report.build(p, checks))
    assert "최종 판단" in md
    assert "SAMPLE" in md  # 샘플 데이터임이 보고서에 드러나야 함
