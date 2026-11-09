"""⑥ 보고서 생성 + 근거 검증.

역할 분담이 핵심:
  - overall(종합 신호), 필요한 승인, 확인 질문  → 코드가 결정 (LLM 은 절대 못 바꿈)
  - summary(3~4문장 요약)                       → LLM 이 작성
  - summary 검증                                → 코드가 검사 (없는 조항·없는 숫자 → 재생성 → 템플릿)
"""
import json
import re
from collections import Counter

import config
from precheck import data, llm, rules
from precheck.schemas import CheckResult, Proposal, Report, Signal

SIGNAL_EMOJI = {"RED": "🔴", "YELLOW": "🟡", "GREEN": "🟢", "UNKNOWN": "⚪"}
CHECK_LABEL = {"exclusion": "배제 테마", "sanctions": "제재", "limit_single": "단일종목 한도",
               "limit_sector": "섹터 한도", "conflict": "이해상충", "law": "법령"}

RULE_REF = re.compile(r"\[((?:IG|ACT)-[\w-]+)\]")   # 요약 속 조문 인용 [IG-5-1]
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")           # 요약 속 숫자 150 / 1.84 / 10,714,286


# ── 1. 코드가 정하는 것들 ──────────────────────────────
def decide_overall(checks: list[CheckResult]) -> Signal:
    """RED 하나라도 → RED / YELLOW 하나라도 → YELLOW / GREEN 이 있으면 → GREEN / UNKNOWN 만 → YELLOW"""
    signals = {c.signal for c in checks}
    if "RED" in signals:
        return "RED"
    if "YELLOW" in signals:
        return "YELLOW"
    if "GREEN" in signals:
        return "GREEN"
    return "YELLOW"


def _dedupe(items) -> list[str]:
    return list(dict.fromkeys(items))


def sources_used() -> list[str]:
    return [f"{name} [{info['status']}] {info['source']} (기준일 {info.get('as_of') or '미상'})"
            for name, info in data.load_manifest().items()]


# ── 2. LLM 요약 검증 (환각 차단) ─────────────────────────
def _to_float(s: str) -> float:
    return float(s.replace(",", ""))


def _allowed_numbers(checks: list[CheckResult], p: Proposal | None) -> set[float]:
    """요약에 써도 되는 숫자 = 점검 결과(headline·근거·승인·질문)에 실제로 등장한 숫자 + 투자안 금액 + 건수."""
    texts = []
    for c in checks:
        texts += [c.headline, c.next_step or "", *c.questions, *(e.text for e in c.evidence)]
    allowed = {_to_float(n) for t in texts for n in NUMBER.findall(t)}
    allowed |= set(range(len(checks) + 1))  # "RED 2건" 같은 건수
    if p:
        allowed |= {p.amount_krw, p.amount_krw / 1e8, p.amount_krw / 1e12}  # 원 / 억 / 조
        if p.amount_usd:
            allowed.add(round(p.amount_usd))
    return allowed


def validate_summary(summary: str, checks: list[CheckResult], p: Proposal | None = None) -> list[str]:
    """문제 목록을 반환 (빈 리스트 = 통과)."""
    problems = []
    cited_in_checks = {e.source_id for c in checks for e in c.evidence}
    cited_in_checks |= {rid for c in checks for rid in RULE_REF.findall(c.next_step or "")}
    for rid in RULE_REF.findall(summary):
        if rules.get_rule(rid) is None:
            problems.append(f"존재하지 않는 조문 인용: [{rid}]")
        elif rid not in cited_in_checks:
            problems.append(f"점검 결과에 없는 조문 인용: [{rid}]")

    allowed = _allowed_numbers(checks, p)
    for n in NUMBER.findall(RULE_REF.sub("", summary)):  # 조문 ID 속 숫자는 제외하고 검사
        if _to_float(n) not in allowed:
            problems.append(f"근거에 없는 숫자: {n}")
    return problems


def template_summary(checks: list[CheckResult], overall: Signal) -> str:
    """LLM 이 없거나 검증을 끝내 통과 못 할 때 쓰는 코드 생성 요약. (항상 검증 통과)"""
    cnt = Counter(c.signal for c in checks)
    parts = [f"점검 {len(checks)}개 항목 중 RED {cnt['RED']}건, YELLOW {cnt['YELLOW']}건, "
             f"UNKNOWN {cnt['UNKNOWN']}건, GREEN {cnt['GREEN']}건으로 종합 신호는 {overall}입니다."]
    for c in checks:
        if c.signal in ("RED", "YELLOW"):
            refs = " ".join(f"[{e.source_id}]" for e in c.evidence if e.source_type == "rule")
            parts.append(f"{CHECK_LABEL[c.check_id]}: {c.headline} {refs}".rstrip() + ".")
    return " ".join(parts)


# ── 3. LLM 요약 생성 ────────────────────────────────────
SUMMARY_SYSTEM = "당신은 투자 준법 사전 점검 보고서의 요약을 쓰는 보조자입니다. 판단은 하지 않고, 주어진 점검 결과만 정리합니다."


def _summary_prompt(p: Proposal, checks: list[CheckResult], overall: Signal, feedback: list[str] | None) -> str:
    payload = {
        "proposal": {"company_name": p.company_name, "amount_krw": p.amount_krw, "staff_id": p.staff_id},
        "overall": overall,
        "checks": [c.model_dump(include={"check_id", "signal", "headline", "evidence", "next_step"}) for c in checks],
    }
    prompt = (
        "아래 점검 결과(JSON)를 담당자가 읽을 한국어 요약 3~4문장으로 써 주세요.\n"
        "규칙:\n"
        "1. 제공된 checks에 없는 사실·숫자·조항을 쓰지 마세요.\n"
        "2. 숫자는 근거 텍스트에 적힌 그대로 쓰세요 (반올림·환산 금지).\n"
        "3. 조항을 언급할 때는 반드시 [IG-5-1] 처럼 대괄호로 감싼 rule_id로, checks 근거에 나온 것만 쓰세요.\n"
        "4. overall 신호를 바꾸거나 새로 판단하지 마세요.\n"
        "5. 요약 문장만 출력하세요 (제목·목록·마크다운 없이).\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=1)}"
    )
    if feedback:
        prompt += "\n\n직전 답변에서 다음 문제가 발견되었습니다. 고쳐서 다시 쓰세요:\n- " + "\n- ".join(feedback)
    return prompt


def make_summary(p: Proposal, checks: list[CheckResult], overall: Signal) -> str:
    feedback = None
    for _ in range(1 + config.LLM_MAX_RETRIES):
        text = llm.complete(_summary_prompt(p, checks, overall, feedback), system=SUMMARY_SYSTEM)
        if text is None:          # 키 없음 / 호출 실패 → 바로 템플릿
            break
        feedback = validate_summary(text, checks, p)
        if not feedback:
            return text           # 검증 통과한 LLM 요약
    return template_summary(checks, overall)


# ── 4. 조립 ─────────────────────────────────────────────
def build(p: Proposal, checks: list[CheckResult]) -> Report:
    overall = decide_overall(checks)
    return Report(
        proposal=p,
        checks=checks,
        overall=overall,
        summary=make_summary(p, checks, overall),
        required_approvals=_dedupe(c.next_step for c in checks if c.next_step),
        open_questions=_dedupe(q for c in checks for q in c.questions),
        sources_used=sources_used(),
    )


# ── 5. Markdown 렌더 ───────────────────────────────────
def fmt_krw(amount: float) -> str:
    if amount >= 1e12:
        return f"{amount / 1e12:g}조 원"
    if amount >= 1e8:
        return f"{amount / 1e8:,.10g}억 원"
    return f"{amount:,.0f}원"


def _cell(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ")


def to_markdown(r: Report) -> str:
    p = r.proposal
    usd = f" (≈ ${p.amount_usd:,.0f})" if p.amount_usd else ""
    ident = ", ".join(x for x in [p.ticker, p.cusip] if x)
    lines = [
        f"# 투자안 사전 점검 보고서 — {SIGNAL_EMOJI[r.overall]} {r.overall}",
        "",
        "## 1. 투자안",
        "| 항목 | 내용 |", "|---|---|",
        f"| 기업 | {_cell(p.company_name)}{f' ({ident})' if ident else ''} |",
        f"| 금액 | {fmt_krw(p.amount_krw)}{usd} |",
        f"| 섹터 | {_cell(p.sector or '-')} |",
        f"| 담당자 | {p.staff_id} |",
    ]
    if p.memo:
        lines.append(f"| 메모 | {_cell(p.memo)} |")

    lines += ["", "## 2. 점검 결과", "| 점검 | 신호 | 결과 | 근거 |", "|---|---|---|---|"]
    for c in r.checks:
        refs = ", ".join(_dedupe(e.source_id for e in c.evidence)) or "-"
        lines.append(f"| {CHECK_LABEL[c.check_id]} | {SIGNAL_EMOJI[c.signal]} {c.signal} | {_cell(c.headline)} | {_cell(refs)} |")

    lines += ["", "## 3. 요약", r.summary, "", "## 4. 필요한 승인"]
    lines += [f"- {a}" for a in r.required_approvals] or ["- 없음"]
    lines += ["", "## 5. 확인 질문"]
    lines += [f"- {q}" for q in r.open_questions] or ["- 없음"]

    lines += ["", "## 6. 근거 상세"]
    for c in r.checks:
        lines.append(f"**{CHECK_LABEL[c.check_id]}** {SIGNAL_EMOJI[c.signal]}")
        lines += [f"- `{e.source_id}` {e.text}" for e in c.evidence] or ["- (근거 없음)"]
        lines.append("")

    lines += ["## 7. 참조 데이터"] + [f"- {s}" for s in r.sources_used]
    lines += ["", "---", f"> ⚠️ {r.disclaimer}"]
    return "\n".join(lines)
