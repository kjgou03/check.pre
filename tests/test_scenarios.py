"""04번 문서의 데모 시나리오를 그대로 코드화. 발표 전 `pytest` 한 번이면 시연이 깨졌는지 알 수 있다.
LLM 키 없이(템플릿 폴백) 통과해야 한다."""
import time

from precheck import batch, orchestrator, report


def _check(r, check_id):
    return next(c for c in r.checks if c.check_id == check_id)


# 시나리오 1 — 모드 A: 배제 테마 해당 (RED)
def test_scenario1_altria_red():
    t0 = time.time()
    r = orchestrator.run(company="Altria Group", amount_krw=15e9, staff_id="S002")
    assert time.time() - t0 < 10

    assert r.overall == "RED"
    ex = _check(r, "exclusion")
    assert ex.signal == "RED" and any(e.source_id == "IG-5-1" for e in ex.evidence)
    assert any(e.source_id == "IG-5-2" for e in ex.evidence)
    assert _check(r, "sanctions").signal == "GREEN"
    assert _check(r, "limit_single").signal in ("GREEN", "YELLOW")
    assert _check(r, "limit_sector").signal == "UNKNOWN"
    assert _check(r, "conflict").signal == "GREEN"
    assert "책임투자위원회" in " ".join(r.required_approvals)
    assert "[IG-5-1]" in r.summary and report.validate_summary(r.summary, r.checks, r.proposal) == []


# 시나리오 2 — 모드 A: 이해상충 (같은 투자안도 누가 올리느냐에 따라 달라짐)
def test_scenario2_conflict():
    first = orchestrator.run(company="Microsoft Corp", amount_krw=5e9, staff_id="S001")
    assert _check(first, "conflict").signal == "GREEN"

    r = orchestrator.run(company="Altria Group", amount_krw=5e9, staff_id="S001")
    cf = _check(r, "conflict")
    assert cf.signal == "RED" and any(e.source_id == "IG-7-1" for e in cf.evidence)
    assert _check(r, "exclusion").signal == "RED"
    assert "준법감시부 신고 및 담당자 교체" in " ".join(r.required_approvals)


# 시나리오 3 — 모드 B: 포트폴리오 스크리닝
def test_scenario3_batch():
    df = batch.run(save=False)
    assert (df.theme == "tobacco").any() or (df.theme == "coal").any()
    assert "참조 목록" in batch.reference_note()


# 정상 케이스 — GREEN 도 "왜 GREEN 인지" 근거가 붙는다
def test_green_has_evidence():
    r = orchestrator.run(company="Microsoft Corp", amount_krw=5e9, staff_id="S002")
    assert r.overall == "GREEN"
    for c in r.checks:
        if c.check_id == "limit_sector":
            assert c.signal == "UNKNOWN"
        else:
            assert c.signal == "GREEN"
        if c.signal == "GREEN":
            assert len(c.evidence) > 0


# 모든 RED/YELLOW 에 source 가 있다 (00번 완료 정의)
def test_every_red_yellow_has_source():
    for kwargs in [dict(company="Altria Group", amount_krw=15e9, staff_id="S001"),
                   dict(company="Southern Copper Corp", amount_krw=15e9, staff_id="S002")]:
        r = orchestrator.run(**kwargs)
        for c in r.checks:
            if c.signal in ("RED", "YELLOW"):
                assert c.evidence and all(e.source_id for e in c.evidence)
