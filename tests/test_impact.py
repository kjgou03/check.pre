"""모드 B-2 — 규정 변경 영향 분석 (기획서 데모 시나리오 3)."""
import pytest

import config
from precheck import impact, llm


def _example():
    path = config.SAMPLES_DIR / "new_list_example.csv"
    return impact.parse_new_list(path.name, path.read_text(encoding="utf-8"))


def test_new_list_finds_newly_affected_holdings():
    res = impact.run(_example())
    s = res["summary"]
    assert s["new_list"] == 3 and s["already_listed"] == 1 and s["added"] == 2  # Alliance 는 이미 목록에 있음
    assert s["newly_red"] == 1 and s["newly_red_usd"] == 120_000_000            # Warrior Met Coal
    row = res["detail"].iloc[0]
    assert row["ticker"] == "HCC" and row["before"] == "YELLOW" and row["signal"] == "RED"
    assert "saved_to" in s


def test_document_without_llm_key_gives_clear_error():
    with pytest.raises(ValueError, match="LLM 키"):
        impact.parse_new_list("notice.md", "Warrior Met Coal Inc. 을 배제 대상에 추가한다.")


def test_document_with_llm_extracts_companies(monkeypatch):
    fake = {"companies": [{"company_name": "Warrior Met Coal Inc", "theme": "coal", "reason": "석탄 채굴"}]}
    monkeypatch.setattr(llm, "complete_json", lambda *a, **k: fake)
    df = impact.parse_new_list("notice.md", "(문서 본문)")
    assert df.iloc[0]["company_name"] == "Warrior Met Coal Inc" and df.iloc[0]["source"] == "notice"
    assert impact.run(df, save=False)["summary"]["newly_red"] == 1


def test_csv_without_company_column_is_rejected():
    with pytest.raises(ValueError, match="company_name"):
        impact.parse_new_list("bad.csv", "name,theme\nX,coal\n")
