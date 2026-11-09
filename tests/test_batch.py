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


def test_batch_also_checks_single_issuer_limit(monkeypatch):
    # 기획서: 모드 B 는 보유내역 전체에 ③(배제·제재)과 ④(한도)를 돌린다.
    # 모의 지침 한도를 1.5% 로 낮추면 비중 큰 종목들이 한도 점검에 걸려야 한다.
    from precheck import rules
    real = rules.param
    monkeypatch.setattr(rules, "param", lambda rid, key: 1.5 if (rid, key) == ("IG-3-1", "max_pct") else real(rid, key))
    df = batch.run(save=False)
    over = df[df["limit_single"] == "RED"]
    assert "AAPL" in set(over["ticker"]) and (over["weight_pct"] > 1.5).all()
    assert (df.loc[df["ticker"] == "AAPL", "theme"] == "limit").all()
