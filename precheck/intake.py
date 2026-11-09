"""① 입력 정규화: 자유 텍스트 또는 폼 값 → Proposal.

  자유 텍스트: LLM 구조화 추출 → (키 없으면) 정규식 폴백
  폼 값      : 그대로 사용
  공통       : 보유내역(holdings)과 이름 매칭해서 ticker/cusip/sector 를 채운다.
              필수값(기업명·금액·담당자)이 비면 missing_fields 에 적는다 → 오케스트레이터가 질문하고 중단.
"""
import re

from rapidfuzz import fuzz, process

import config
from precheck import data, llm
from precheck.schemas import Proposal

REQUIRED = ("company_name", "amount_krw", "staff_id")

# ── LLM 추출 ───────────────────────────────────────────
_nullable = lambda t: {"anyOf": [{"type": t}, {"type": "null"}]}  # noqa: E731
EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "company_name": _nullable("string"),
        "amount_krw": _nullable("number"),
        "staff_id": _nullable("string"),
        "sector": _nullable("string"),
        "country": _nullable("string"),
        "memo": _nullable("string"),
    },
    "required": ["company_name", "amount_krw", "staff_id", "sector", "country", "memo"],
    "additionalProperties": False,
}
EXTRACT_PROMPT = """다음 문장에서 투자안 정보를 추출해 JSON으로 답하세요.
- 추정하지 말고, 문장에 없으면 null.
- amount_krw: 원 단위 숫자로 변환 (예: 150억 → 15000000000, 1조 5천억 → 1500000000000).
- company_name: 영문 공식 기업명으로 (예: 알트리아 → Altria Group). 기업이 언급되지 않았으면 null.
- staff_id: S로 시작하는 담당자 코드 (예: S001).
- memo: 위 항목 외에 투자 사유 등 참고할 내용이 있으면 한 줄로, 없으면 null.

문장: {text}"""


# ── 정규식 폴백 (LLM 키가 없을 때) ──────────────────────
_UNITS = {"조": 1e12, "억": 1e8, "만": 1e4}


def parse_amount_krw(text: str) -> float | None:
    """'150억' → 1.5e10, '1조 5천억' → 1.5e12, '3,000,000,000원' → 3e9"""
    text = re.sub(r"(\d+(?:\.\d+)?)\s*천", lambda m: str(float(m.group(1)) * 1000), text)  # 5천억 → 5000억
    hits = re.findall(r"(\d[\d,]*(?:\.\d+)?)\s*(조|억|만)", text)
    if hits:
        return sum(float(n.replace(",", "")) * _UNITS[u] for n, u in hits)
    m = re.search(r"(\d[\d,]{3,}(?:\.\d+)?)\s*원", text)
    return float(m.group(1).replace(",", "")) if m else None


def _regex_extract(text: str) -> dict:
    staff = re.search(r"(?<![A-Za-z0-9])[Ss]\d{3}(?!\d)", text)
    without_staff = text.replace(staff.group(0), " ") if staff else text
    # 영문 덩어리 중 가장 긴 것을 기업명으로 (한글 기업명은 LLM 없이는 영문 목록과 대조 불가 → 비워서 질문)
    runs = re.findall(r"[A-Za-z][A-Za-z0-9&.' -]*[A-Za-z0-9.]", without_staff)
    return {
        "company_name": max(runs, key=len).strip() if runs else None,
        "amount_krw": parse_amount_krw(text),
        "staff_id": staff.group(0) if staff else None,
    }


# ── 보유내역 매칭 ────────────────────────────────────────
def match_holding(company_name: str):
    """입력 기업명 → holdings 의 한 행 (없거나 애매하면 None).

    입력은 'Philip Morris' 처럼 짧게 들어오므로 부분집합도 허용하는 token_set_ratio 로 후보를 찾고,
    후보가 여럿인데 확실한 1등이 없으면(예: 'Energy') 엉뚱한 종목을 채우지 않도록 포기한다.
    """
    h = data.load_holdings()
    name = data.normalize_name(company_name)
    cands = process.extract(name, h["norm"].tolist(), scorer=fuzz.token_set_ratio,
                            score_cutoff=config.INTAKE_MATCH, limit=None)
    if not cands:
        return None
    scored = sorted(((data.match_score(name, h.iloc[i]["norm"]), i) for _, _, i in cands), reverse=True)
    best_score, best_idx = scored[0]
    if len(scored) > 1 and best_score < config.FUZZY_RED:
        return None
    return h.iloc[best_idx]


# ── 공개 함수 ────────────────────────────────────────────
def _finalize(f: dict) -> Proposal:
    missing = [k for k in REQUIRED if not f.get(k)]
    company = (f.get("company_name") or "").strip()
    amount = float(f.get("amount_krw") or 0)
    h = match_holding(company) if company else None
    return Proposal(
        company_name=company,
        ticker=(h["ticker"] or None) if h is not None else None,
        cusip=(h["cusip"] or None) if h is not None else None,
        sector=f.get("sector") or (h["sector"] if h is not None and h["sector"] else None),
        country=f.get("country") or (h["country"] if h is not None and h["country"] else None),
        amount_krw=amount,
        amount_usd=amount / config.FX_KRW_USD if amount else None,
        staff_id=(f.get("staff_id") or "").strip().upper(),
        memo=f.get("memo") or None,
        missing_fields=missing,
    )


def parse(text: str) -> Proposal:
    """자유 텍스트 → Proposal. 예) '알트리아에 150억 추가 투자하려고 해요, 담당자 S001'"""
    fields = llm.complete_json(EXTRACT_PROMPT.format(text=text), EXTRACT_SCHEMA)
    if fields is None:
        fields = _regex_extract(text)
    return _finalize(fields)


def from_fields(company_name: str | None, amount_krw: float | None, staff_id: str | None,
                memo: str | None = None) -> Proposal:
    """폼/CLI 입력 → Proposal (LLM 안 씀)."""
    return _finalize({"company_name": company_name, "amount_krw": amount_krw,
                      "staff_id": staff_id, "memo": memo})
