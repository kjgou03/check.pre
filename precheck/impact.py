"""모드 B-2 — 규정 변경 영향 분석.

새 배제·제재 목록(CSV) 또는 공지 문서(.txt/.md)를 넣으면, 우리 보유 종목 중 **새로 걸리는 종목**을 바로 뽑는다.

  CSV          → 그대로 읽음 (company_name 열 필수, 나머지 열은 없으면 기본값)
  문서 .txt/.md → LLM 이 '새로 지정된 기업명'만 추출 (키 필요). 추출 결과는 화면에 그대로 보여줘서 사람이 확인
  공통         → 기존 목록에 이미 있던 기업은 빼고, 새로 추가된 기업만 보유내역과 대조 → 순증 영향 산출

실행:  python -m precheck.impact data/samples/new_list_example.csv
"""
import argparse
import datetime as dt
import io
from pathlib import Path

import pandas as pd

import config
from precheck import audit, data, llm, report, screening
from precheck.schemas import Proposal

LIST_COLUMNS = ["company_name", "theme", "source", "source_detail", "effective_date"]

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {"companies": {"type": "array", "items": {
        "type": "object",
        "properties": {"company_name": {"type": "string"}, "theme": {"type": "string"}, "reason": {"type": "string"}},
        "required": ["company_name", "theme", "reason"],
        "additionalProperties": False,
    }}},
    "required": ["companies"],
    "additionalProperties": False,
}
EXTRACT_PROMPT = """아래 문서에서 '투자 배제 또는 제재 대상으로 새로 지정된 기업'만 뽑아 JSON으로 답하세요.
- 문서에 명시된 기업만. 추정하거나 보완하지 마세요.
- theme: tobacco / coal / cannabis / controversial_weapons / child_labor / sanctions / other 중 하나.
- reason: 문서에 적힌 지정 사유를 짧게, 문서 표현 그대로.

문서:
{text}"""


def parse_new_list(filename: str, content: str) -> pd.DataFrame:
    """업로드된 파일 → 목록 DataFrame (exclusion_list.csv 와 같은 열 + norm)."""
    if filename.lower().endswith(".csv"):
        df = pd.read_csv(io.StringIO(content), dtype=str, keep_default_na=False)
        if "company_name" not in df.columns:
            raise ValueError("CSV에 company_name 열이 필요합니다.")
    else:
        result = llm.complete_json(EXTRACT_PROMPT.format(text=content), EXTRACT_SCHEMA)
        if result is None:
            raise ValueError("문서(.txt/.md)에서 기업명을 뽑으려면 LLM 키가 필요합니다. 키가 없으면 CSV를 사용하세요.")
        df = pd.DataFrame(result["companies"], columns=["company_name", "theme", "reason"])
        df["source_detail"] = "문서에서 추출(LLM): " + df["reason"]

    for col in LIST_COLUMNS:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str).str.strip()
    df.loc[df["theme"] == "", "theme"] = "other"
    df.loc[df["source"] == "", "source"] = Path(filename).stem
    df = df[df["company_name"] != ""][LIST_COLUMNS].copy()
    df["norm"] = df["company_name"].map(data.normalize_name)
    return df.reset_index(drop=True)


def run(new_list: pd.DataFrame, save: bool = True) -> dict:
    """반환: {"summary": 숫자 요약, "detail": 영향 종목 표, "added": 새로 추가된 기업, "already": 기존 목록에 있던 기업}"""
    current = data.load_exclusions()
    current = current[current["source"] != screening.KEYWORD_SOURCE]
    is_known = new_list["norm"].map(lambda n: bool(data.find_matches(n, current, config.FUZZY_RED)))
    added, already = new_list[~is_known], new_list[is_known]

    rows = []
    for _, h in data.load_holdings().iterrows():
        p = Proposal(company_name=h["issuer_name"], ticker=h["ticker"] or None, sector=h["sector"] or None,
                     amount_krw=0, staff_id="BATCH")
        hits = [m for m in screening.match_exclusions(p, ex=added) if m["kind"] == "list"]
        if not hits:
            continue
        top = hits[0]
        rows.append({
            "signal": "RED" if top["score"] >= config.FUZZY_RED else "YELLOW",
            "before": screening.exclusion(p).signal,  # 기존 목록 기준 신호
            "issuer_name": h["issuer_name"],
            "ticker": h["ticker"],
            "value_usd": int(h["value_usd"]),
            "matched_name": top["company_name"],
            "theme": top["theme"],
            "source": top["source"],
            "match_score": round(top["score"]),
            "evidence": top["source_detail"],
        })
    detail = pd.DataFrame(rows, columns=["signal", "before", "issuer_name", "ticker", "value_usd", "matched_name",
                                         "theme", "source", "match_score", "evidence"])
    newly_red = detail[(detail["signal"] == "RED") & (detail["before"] != "RED")]
    summary = {
        "new_list": len(new_list),
        "already_listed": len(already),
        "added": len(added),
        "affected_holdings": len(detail),
        "newly_red": len(newly_red),
        "newly_red_usd": int(newly_red["value_usd"].sum()),
    }

    if save:
        config.OUTPUT_DIR.mkdir(exist_ok=True)
        path = config.OUTPUT_DIR / f"impact_{dt.date.today():%Y%m%d}.csv"
        detail.to_csv(path, index=False, encoding="utf-8-sig")
        summary["saved_to"] = str(path)
        sources = sorted(set(new_list["source"]))
        audit.log("B-2", summary, overall=f"새로 RED {summary['newly_red']}건",
                  sources=report.sources_used() + [f"새 목록: {', '.join(sources)}"])
    return {"summary": summary, "detail": detail, "added": added.drop(columns="norm"),
            "already": already.drop(columns="norm")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="PreCheck 모드 B-2 — 규정 변경 영향 분석")
    ap.add_argument("file", help="새 목록 CSV 또는 공지 문서(.txt/.md)")
    args = ap.parse_args(argv)
    path = Path(args.file)
    try:
        new_list = parse_new_list(path.name, path.read_text(encoding="utf-8"))
    except ValueError as e:
        print(f"입력 오류: {e}")
        return 2
    result = run(new_list)
    s = result["summary"]
    print(f"새 목록 {s['new_list']}개 기업 중 기존 목록에 이미 있음 {s['already_listed']}개, 새로 추가 {s['added']}개")
    print(f"→ 보유 종목 중 영향 {s['affected_holdings']}건, 새로 RED {s['newly_red']}건 "
          f"(합계 ${s['newly_red_usd']:,} ≈ {s['newly_red_usd'] * config.FX_KRW_USD / 1e8:,.0f}억 원)\n")
    if not result["detail"].empty:
        print(result["detail"].drop(columns="evidence").to_string(index=False))
    if "saved_to" in s:
        print(f"\n상세 저장: {s['saved_to']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
