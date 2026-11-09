"""감사 로그 — "그때 왜 괜찮다고 했어?"에 답하기 위한 영수증.

점검할 때마다 [언제·무엇을·누가·결과·어떤 데이터 버전을 봤는지]를 SQLite 파일 하나(output/audit.db)에 쌓는다.
기획서의 '장기 메모리(점검 이력)'와 '감사 로그'를 최소 형태로 구현한 것.
"""
import datetime as dt
import json
import sqlite3
from contextlib import closing

import config

_SCHEMA = """CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,          -- 기록 시각 (UTC)
    mode TEXT NOT NULL,        -- A / B / B-2
    company TEXT,
    staff_id TEXT,
    overall TEXT,              -- 종합 신호 (모드 A) 또는 요약 (B, B-2)
    sources TEXT,              -- 참조한 데이터 파일·버전 (JSON 배열)
    payload TEXT               -- 보고서 전체 또는 결과 요약 (JSON)
)"""


def _connect() -> sqlite3.Connection:
    config.OUTPUT_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(config.OUTPUT_DIR / config.AUDIT_DB_NAME)
    conn.execute(_SCHEMA)
    return conn


def log(mode: str, payload: dict, *, company: str | None = None, staff_id: str | None = None,
        overall: str | None = None, sources: list[str] | None = None) -> int:
    """한 줄 기록하고 id 를 돌려준다."""
    with closing(_connect()) as conn, conn:  # closing: 파일 닫기 / conn: 커밋
        cur = conn.execute(
            "INSERT INTO audit_log (ts, mode, company, staff_id, overall, sources, payload) VALUES (?,?,?,?,?,?,?)",
            (dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), mode, company, staff_id, overall,
             json.dumps(sources or [], ensure_ascii=False), json.dumps(payload, ensure_ascii=False)),
        )
        return cur.lastrowid


def recent(n: int = 10) -> list[dict]:
    """최근 기록 n개 (최신순)."""
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT id, ts, mode, company, staff_id, overall FROM audit_log "
                            "ORDER BY id DESC LIMIT ?", (n,)).fetchall()
    return [dict(r) for r in rows]
