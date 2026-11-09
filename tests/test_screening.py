"""Step 2 완료 조건: 배제·제재·이해상충 (LLM 없음)."""
from precheck import conflicts, screening
from precheck.schemas import Proposal


def P(name, staff="S002", ticker=None, sector=None):
    return Proposal(company_name=name, staff_id=staff, amount_krw=1, ticker=ticker, sector=sector)


def test_altria_exclusion_red_with_ig_5_1():
    r = screening.exclusion(P("Altria Group"))
    assert r.signal == "RED"
    assert any(e.source_id == "IG-5-1" for e in r.evidence)
    assert "책임투자위원회" in r.next_step


def test_normal_company_green_with_evidence():
    p = P("Microsoft Corp")
    ex, sa = screening.exclusion(p), screening.sanctions(p)
    assert ex.signal == "GREEN" and sa.signal == "GREEN"
    assert ex.evidence and sa.evidence


def test_conflict_red_when_staff_holds_it():
    r = conflicts.check(P("Altria Group", staff="S001"))
    assert r.signal == "RED"
    assert any(e.source_id == "IG-7-1" for e in r.evidence)


def test_unregistered_staff_unknown_with_question():
    r = conflicts.check(P("Altria Group", staff="S999"))
    assert r.signal == "UNKNOWN"
    assert len(r.questions) == 1


# ── 아래는 명세 외 추가 확인 ──
def test_registered_staff_without_holdings_is_green():
    r = conflicts.check(P("Altria Group", staff="S002"))
    assert r.signal == "GREEN" and "0건" in r.evidence[0].text


def test_similar_name_is_yellow_not_red():
    # Southern Copper(구리) 는 GCEL 의 Southern Company(석탄)와 이름만 비슷 → 확인 필요
    r = screening.exclusion(P("Southern Copper Corp"))
    assert r.signal == "YELLOW" and r.questions


def test_keyword_only_is_yellow():
    r = screening.exclusion(P("Warrior Met Coal Inc"))
    assert r.signal == "YELLOW" and "키워드" in r.headline


def test_sanctioned_entity_red():
    r = screening.sanctions(P("Sberbank of Russia"))
    assert r.signal == "RED"
    assert any(e.source_id == "IG-6-1" for e in r.evidence)
