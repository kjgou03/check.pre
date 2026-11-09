"""LLM 호출은 전부 이 파일 한 곳에서. (intake.py, report.py 만 사용)

키가 없거나, 호출이 실패하거나, 모델이 거절하면 None 을 돌려준다.
→ 호출한 쪽이 None 을 받으면 정규식/템플릿 폴백으로 동작한다. 그래서 키 없이도 전체가 돈다.
"""
import json
import sys

import config

# Claude Opus 5.5 의 안전 분류기가 요청을 거절하면, 서버가 다른 모델로 자동 재시도하게 하는 옵션
_FALLBACK_BETA = "server-side-fallback-2026-07-01"
_client = None


def enabled() -> bool:
    return bool(config.ANTHROPIC_API_KEY)


def _warn(msg: str) -> None:
    print(f"[llm] {msg}", file=sys.stderr)


def _get_client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=60)
    return _client


def complete(prompt: str, system: str | None = None, schema: dict | None = None) -> str | None:
    """프롬프트 → 응답 텍스트. schema(JSON Schema)를 주면 그 스키마에 맞는 JSON 문자열이 온다."""
    if not enabled():
        return None
    import anthropic

    output_config = {"effort": config.LLM_EFFORT}
    if schema:
        output_config["format"] = {"type": "json_schema", "schema": schema}
    kwargs = dict(
        model=config.LLM_MODEL,
        max_tokens=16000,
        messages=[{"role": "user", "content": prompt}],
        output_config=output_config,
        betas=[_FALLBACK_BETA],
        fallbacks="default",
    )
    if system:
        kwargs["system"] = system

    try:
        resp = _get_client().beta.messages.create(**kwargs)
    except anthropic.AuthenticationError:
        _warn("API 키가 올바르지 않습니다 → 폴백 사용")
        return None
    except anthropic.RateLimitError:
        _warn("요청 한도 초과 → 폴백 사용")
        return None
    except anthropic.APIConnectionError as e:
        _warn(f"네트워크 오류 → 폴백 사용: {e}")
        return None
    except anthropic.APIStatusError as e:
        _warn(f"API 오류 {e.status_code} → 폴백 사용: {e.message}")
        return None

    if resp.stop_reason in ("refusal", "max_tokens"):
        _warn(f"응답 중단(stop_reason={resp.stop_reason}) → 폴백 사용")
        return None
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    return text or None


def complete_json(prompt: str, schema: dict, system: str | None = None) -> dict | None:
    text = complete(prompt, system=system, schema=schema)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        _warn("JSON 파싱 실패 → 폴백 사용")
        return None
