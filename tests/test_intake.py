"""Step 5: 입력 정규화 (LLM 없이 정규식 폴백) + 오케스트레이터."""
import pytest

from precheck import intake, orchestrator


@pytest.mark.parametrize("text, expected", [
    ("150억 투자", 15e9),
    ("1조 5천억", 1.5e12),
    ("5천만 원", 5e7),
    ("3,000,000,000원", 3e9),
    ("금액 미정", None),
])
def test_parse_amount(text, expected):
    assert intake.parse_amount_krw(text) == expected


def test_regex_fallback_extracts_fields():
    p = intake.parse("Altria Group에 150억 추가 투자하려고 해요, 담당자 S001이 올립니다")
    assert p.company_name == "Altria Group"
    assert p.amount_krw == 15e9 and p.staff_id == "S001"
    assert p.ticker == "MO" and p.sector == "Consumer Staples"  # 보유내역 매칭으로 보강
    assert p.missing_fields == []


def test_korean_company_without_llm_asks_instead_of_guessing():
    p = intake.parse("알트리아에 150억, 담당자 S001")
    assert "company_name" in p.missing_fields


def test_short_name_matches_holding():
    assert intake.match_holding("Philip Morris")["ticker"] == "PM"
    assert intake.match_holding("Southern")["ticker"] == "SO"   # Southern Copper 아님


def test_ambiguous_name_is_not_filled():
    assert intake.match_holding("Energy") is None  # Duke/Peabody/NextEra… 중 하나를 찍지 않음


def test_orchestrator_returns_questions_when_missing():
    out = orchestrator.run(company="Altria Group", amount_krw=None, staff_id=None)
    assert isinstance(out, list) and len(out) == 2


def test_cli_prints_red_report(capsys):
    code = orchestrator.main(["--company", "Altria Group", "--amount", "15000000000", "--staff", "S002"])
    out = capsys.readouterr().out
    assert code == 0
    assert "🔴 RED" in out and "책임투자위원회" in out
