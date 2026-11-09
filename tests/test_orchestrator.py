"""기획서 ③ Workflow 와 맞춘 부분: 6개 점검 병렬 실행, 오류 시 '확인 불가'(침묵 실패 금지), 감사 로그."""
from precheck import audit, orchestrator, screening
from precheck.schemas import Proposal


def test_six_checks_in_fixed_order():
    p = Proposal(company_name="Altria Group", ticker="MO", amount_krw=15e9, staff_id="S002")
    ids = [c.check_id for c in orchestrator.run_checks(p)]
    assert ids == ["law", "exclusion", "sanctions", "limit_single", "limit_sector", "conflict"]


def test_law_check_says_unknown_when_corpus_empty():
    p = Proposal(company_name="Microsoft Corp", amount_krw=5e9, staff_id="S002")
    law = orchestrator.run_checks(p)[0]
    assert law.signal == "UNKNOWN" and "확인 불가" in law.headline and law.questions


def test_failed_check_is_not_silent(monkeypatch):
    # 제재 점검이 터져도 보고서는 나오고, 종합이 '적합(GREEN)'으로 나오면 안 된다
    def boom(p):
        raise FileNotFoundError("sanctions.csv 없음")
    monkeypatch.setattr(screening, "sanctions", boom)
    monkeypatch.setattr(orchestrator, "CHECKS", [(cid, boom if cid == "sanctions" else fn)
                                                 for cid, fn in orchestrator.CHECKS])
    r = orchestrator.run(company="Microsoft Corp", amount_krw=5e9, staff_id="S002")
    sa = next(c for c in r.checks if c.check_id == "sanctions")
    assert sa.signal == "YELLOW" and "확인 불가" in sa.headline
    assert r.overall != "GREEN"


def test_each_run_is_audit_logged():
    orchestrator.run(company="Altria Group", amount_krw=15e9, staff_id="S001")
    last = audit.recent(1)[0]
    assert last["mode"] == "A" and last["company"] == "Altria Group" and last["overall"] == "RED"
