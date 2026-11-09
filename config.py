"""설정은 전부 여기 한 곳에서. (모델명, 임계값, 경로)

다른 모듈은 `import config` 후 `config.XXX` 로만 읽는다.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

# ── 경로 ──────────────────────────────────────────────
DATA_DIR = ROOT / "data"
RULES_DIR = DATA_DIR / "rules"
OUTPUT_DIR = ROOT / "output"

HOLDINGS_CSV = DATA_DIR / "holdings.csv"
EXCLUSION_CSV = DATA_DIR / "exclusion_list.csv"
SANCTIONS_CSV = DATA_DIR / "sanctions.csv"
STAFF_CSV = DATA_DIR / "staff_holdings.csv"
MANIFEST_JSON = DATA_DIR / "manifest.json"  # 각 데이터 파일의 출처·기준일·샘플 여부
RULE_FILES = [RULES_DIR / "internal_guideline.json", RULES_DIR / "kic_act_sample.json"]

# ── LLM (intake.py, report.py 에서만 사용) ─────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY") or None
LLM_MODEL = os.getenv("PRECHECK_MODEL", "claude-opus-5-5")
LLM_EFFORT = "low"          # 추출·요약은 단순 작업 → 빠르게 (시연 10초 목표)
LLM_MAX_RETRIES = 2         # 근거 검증 실패 시 요약 재생성 횟수

# ── 계산·매칭 파라미터 ────────────────────────────────
FX_KRW_USD = 1400           # 원/달러 환율 (고정값, 실서비스는 기준환율 연동)
FUZZY_RED = 90              # 이름 매칭 점수 ≥ 90 → 동일 기업으로 간주
FUZZY_YELLOW = 80           # 80~89 → "유사 기업 가능, 확인 필요"
INTAKE_MATCH = 85           # 입력 기업명 ↔ 보유내역 매칭 임계값
