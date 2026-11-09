"""Step 6 완료 조건: tobacco 또는 coal 1건 이상 검출 + CSV 생성."""
import config
from precheck import batch


def test_batch_finds_themes_and_saves_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
    df = batch.run()
    assert df["theme"].isin(["tobacco", "coal"]).any()
    assert list(tmp_path.glob("batch_*.csv"))


def test_similar_name_is_flagged_yellow_not_red():
    df = batch.run(save=False)
    scco = df[df["ticker"] == "SCCO"]  # Southern Copper — 석탄 아님
    assert len(scco) == 1 and scco.iloc[0]["signal"] == "YELLOW"


def test_summary_totals_match_detail():
    df = batch.run(save=False)
    s = batch.summarize(df)
    assert s["count"].sum() == len(df)
    assert s["value_usd"].sum() == df["value_usd"].sum()
