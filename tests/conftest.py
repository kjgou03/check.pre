import os

import pytest

import config


@pytest.fixture(autouse=True)
def _output_to_tmp(tmp_path, monkeypatch):
    """테스트가 만드는 CSV·감사 로그(audit.db)는 임시 폴더로 → 저장소 output/ 를 더럽히지 않는다."""
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "output")


@pytest.fixture(autouse=True)
def _no_llm_by_default(monkeypatch):
    """테스트는 기본적으로 LLM 없이(템플릿 폴백) 돈다 → .env 에 키가 있어도 결과가 매번 같다.
    실제 LLM 까지 태워 보고 싶으면:  PRECHECK_TEST_LLM=1 pytest"""
    if not os.getenv("PRECHECK_TEST_LLM"):
        monkeypatch.setattr(config, "ANTHROPIC_API_KEY", None)
