"""② 규정 검색 (LLM 없음).

조문이 수십 개뿐이라 벡터DB 없이 'category 필터'로 충분하다.
가장 중요한 함수는 get_rule() — 보고서 요약이 인용한 조문 ID가 실제로 있는지 확인할 때 쓴다(환각 차단).
"""
from precheck import data
from precheck.schemas import Evidence


def load() -> dict[str, dict]:
    """{rule_id: 조문} 사전."""
    return {r["rule_id"]: r for r in data.load_rules()}


def get_rule(rule_id: str) -> dict | None:
    return load().get(rule_id)


def as_evidence(rule_id: str) -> Evidence:
    """조문 원문을 그대로 근거(Evidence)로 감싼다."""
    r = get_rule(rule_id)
    if r is None:
        raise KeyError(f"존재하지 않는 조문: {rule_id}")
    return Evidence(source_type="rule", source_id=rule_id, text=r["text"])


def get_by_category(category: str) -> list[Evidence]:
    return [as_evidence(r["rule_id"]) for r in data.load_rules() if r["category"] == category]


def param(rule_id: str, key: str):
    """조문에 딸린 숫자 파라미터. 예) param("IG-3-1", "max_pct") → 3.0
    한도 숫자를 코드에 하드코딩하지 않고 규정 파일 한 곳에서 관리하기 위함."""
    return get_rule(rule_id)["param"][key]
