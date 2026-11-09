"""모든 모듈이 주고받는 데이터 구조 (02번 명세 그대로).

흐름:  Proposal ─(각 점검 함수)→ CheckResult × N ─(report.build)→ Report
"""
from typing import Literal, Optional

from pydantic import BaseModel, model_validator

Signal = Literal["GREEN", "YELLOW", "RED", "UNKNOWN"]


class Proposal(BaseModel):
    """투자안 1건. intake.py 가 만든다."""
    company_name: str
    ticker: Optional[str] = None
    cusip: Optional[str] = None
    amount_krw: float                      # 투자 금액(원)
    amount_usd: Optional[float] = None     # 환산(원/달러 환율은 config)
    asset_class: str = "listed_equity"
    country: Optional[str] = None
    sector: Optional[str] = None
    staff_id: str
    memo: Optional[str] = None
    missing_fields: list[str] = []         # ①이 채우지 못한 필수값


class Evidence(BaseModel):
    """판단 근거 1개. 보고서의 모든 신호는 이걸 달고 다닌다."""
    source_type: Literal["rule", "list", "calc", "db"]
    source_id: str          # rule_id, 목록명, 계산식 설명 등
    text: str               # 조문 원문 / 목록 행 / 계산 결과
    url: Optional[str] = None


class CheckResult(BaseModel):
    """점검 1개의 결과 (신호등 한 칸)."""
    check_id: Literal["exclusion", "sanctions", "limit_single", "limit_sector", "conflict", "law"]
    signal: Signal
    headline: str                 # 한 줄 결과 (사람이 읽는)
    evidence: list[Evidence]      # 비어 있으면 GREEN/UNKNOWN만 허용
    confidence: Optional[float] = None   # 이름 매칭 신뢰도 등
    next_step: Optional[str] = None      # 필요한 승인 절차
    questions: list[str] = []            # 담당자에게 물을 것

    @model_validator(mode="after")
    def _red_yellow_need_evidence(self):
        # 핵심 안전장치: 근거 없는 RED/YELLOW 는 만들 수 없다.
        if self.signal in ("RED", "YELLOW") and not self.evidence:
            raise ValueError(f"{self.check_id}: {self.signal} 신호에는 evidence가 1개 이상 필요합니다")
        return self


class Report(BaseModel):
    """최종 보고서 1장."""
    proposal: Proposal
    checks: list[CheckResult]
    overall: Signal
    summary: str                  # LLM이 쓴 3~4문장 요약 (검증 통과분만)
    required_approvals: list[str]
    open_questions: list[str]
    sources_used: list[str]       # 참조한 데이터 파일·버전
    disclaimer: str = "본 보고서는 참고용이며 최종 판단은 담당자가 합니다."
