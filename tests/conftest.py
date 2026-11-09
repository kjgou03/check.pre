import os

import pytest

import config


@pytest.fixture(autouse=True)
def _no_llm_by_default(monkeypatch):
    """테스트는 기본적으로 LLM 없이(템플릿 폴백) 돈다 → .env 에 키가 있어도 결과가 매번 같다.
    실제 LLM 까지 태워 보고 싶으면:  PRECHECK_TEST_LLM=1 pytest"""
    if not os.getenv("PRECHECK_TEST_LLM"):
        monkeypatch.setattr(config, "ANTHROPIC_API_KEY", None)
