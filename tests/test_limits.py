"""Step 3 완료 조건: 한도 계산 (LLM 없음)."""
from precheck import data, limits
from precheck.schemas import Proposal


def _usd_to_reach(ticker: str, target_pct: float) -> float:
    """해당 종목 비중을 target_pct 로 만들려면 몇 달러를 더 사야 하는지 (테스트용 역산)."""
    h = data.load_holdings()
    total, cur = h.value_usd.sum(), h.loc[h.ticker == ticker, "value_usd"].sum()
    t = target_pct / 100
    return (t * total - cur) / (1 - t)


def P(amount_usd, ticker="MSFT", sector=None):
    return Proposal(company_name="Microsoft Corp", ticker=ticker, staff_id="S002",
                    amount_krw=amount_usd * 1400, amount_usd=amount_usd, sector=sector)


def test_over_limit_is_red():
    r = limits.single(P(_usd_to_reach("MSFT", 3.5)))
    assert r.signal == "RED"
    text = r.evidence[0].text
    assert "현재" in text and "추가 후" in text and "한도" in text
    assert "리스크관리위원회" in r.next_step


def test_near_limit_is_yellow():
    r = limits.single(P(_usd_to_reach("MSFT", 2.7)))
    assert r.signal == "YELLOW"


def test_small_amount_is_green():
    r = limits.single(P(1_000_000))
    assert r.signal == "GREEN"


def test_no_sector_is_unknown_not_error():
    r = limits.sector(P(1_000_000, sector=None))
    assert r.signal == "UNKNOWN"


def test_sector_without_benchmark_is_unknown_but_shows_calc():
    r = limits.sector(P(1_000_000, sector="Information Technology"))
    assert r.signal == "UNKNOWN" and "벤치마크" in r.headline
    assert r.evidence and r.evidence[0].source_type == "calc"
