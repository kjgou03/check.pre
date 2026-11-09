"""모드 B — 보유내역 전체를 배제·제재 목록과 대조 (국감 지적 재현용).

모드 A 의 screening 함수를 그대로 재사용한다. 보유 종목 하나하나를 '금액 0원짜리 투자안'으로 보고 돌리는 것.

실행:  python -m precheck.batch
"""
import datetime as dt

import pandas as pd

import config
from precheck import data, screening
from precheck.schemas import Proposal

DETAIL_COLUMNS = ["signal", "theme", "issuer_name", "ticker", "value_usd",
                  "exclusion", "sanctions", "matched_name", "list_source", "match_score", "evidence"]
_ORDER = {"RED": 0, "YELLOW": 1, "UNKNOWN": 2, "GREEN": 3}


def run(save: bool = True) -> pd.DataFrame:
    """해당(RED/YELLOW) 종목만 담은 상세 표를 반환. save=True 면 output/batch_YYYYMMDD.csv 저장."""
    rows = []
    for _, h in data.load_holdings().iterrows():
        p = Proposal(company_name=h["issuer_name"], ticker=h["ticker"] or None, sector=h["sector"] or None,
                     amount_krw=0, staff_id="BATCH")
        ex, sa = screening.exclusion(p), screening.sanctions(p)
        if ex.signal == "GREEN" and sa.signal == "GREEN":
            continue

        top = screening.match_exclusions(p)[0] if ex.signal != "GREEN" else None
        flagged = [c for c in (ex, sa) if c.signal != "GREEN"]
        rows.append({
            "signal": min((c.signal for c in flagged), key=_ORDER.get),
            "theme": top["theme"] if top else "sanctions",
            "issuer_name": h["issuer_name"],
            "ticker": h["ticker"],
            "value_usd": int(h["value_usd"]),
            "exclusion": ex.signal,
            "sanctions": sa.signal,
            "matched_name": top["company_name"] if top else "",
            "list_source": top["source"] if top else "OFAC_SDN",
            "match_score": round(top["score"]) if top and top["score"] is not None else None,
            # 목록 행 원문만 (조문 원문은 너무 길어서 제외)
            "evidence": " / ".join(e.text for c in flagged for e in c.evidence if e.source_type == "list"),
        })

    df = pd.DataFrame(rows, columns=DETAIL_COLUMNS)
    df["match_score"] = df["match_score"].astype("Int64")  # 빈칸 허용 정수 (100.0 → 100)
    df = df.sort_values(["signal", "value_usd"], key=lambda s: s.map(_ORDER) if s.name == "signal" else -s)
    df = df.reset_index(drop=True)
    if save:
        config.OUTPUT_DIR.mkdir(exist_ok=True)
        path = config.OUTPUT_DIR / f"batch_{dt.date.today():%Y%m%d}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")  # utf-8-sig: 엑셀에서 한글 안 깨지게
        df.attrs["saved_to"] = str(path)
    return df


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    """테마·신호별 건수와 금액 합계."""
    if df.empty:
        return pd.DataFrame(columns=["theme", "signal", "count", "value_usd", "value_krw_조", "sources"])
    g = df.groupby(["theme", "signal"], as_index=False).agg(
        count=("issuer_name", "size"),
        value_usd=("value_usd", "sum"),
        sources=("list_source", lambda s: ", ".join(sorted(set(s)))),
    )
    g["value_krw_조"] = (g["value_usd"] * config.FX_KRW_USD / 1e12).round(3)
    g = g.sort_values(["signal", "value_usd"], key=lambda s: s.map(_ORDER) if s.name == "signal" else -s)
    return g[["theme", "signal", "count", "value_usd", "value_krw_조", "sources"]].reset_index(drop=True)


_BATCH_FILES = ("holdings.csv", "exclusion_list.csv", "sanctions.csv")


def reference_note() -> str:
    m = data.load_manifest()
    parts = [f"{k}({m[k]['status']}, 기준일 {m[k].get('as_of') or '미상'})" for k in _BATCH_FILES]
    note = "참조 목록: " + ", ".join(parts)
    if any(m[k]["status"] != "REAL" for k in _BATCH_FILES):
        note += "\n⚠️ 실데이터가 아닌 파일이 있습니다 — 아래 건수·금액은 동작 확인용이며 실제 수치가 아닙니다."
    return note


def main() -> int:
    df = run()
    summary = summarize(df)
    print(reference_note())
    print(f"환율 {config.FX_KRW_USD:,}원/$\n")
    print("[테마별 합계]")
    print(summary.to_string(index=False) if not summary.empty else "해당 없음")
    red = df[df["signal"] == "RED"]
    print(f"\nRED(목록 확정 매칭) {len(red)}건, 합계 ${red['value_usd'].sum():,.0f} "
          f"(≈ {red['value_usd'].sum() * config.FX_KRW_USD / 1e12:.2f}조 원)")
    print(f"YELLOW(확인 필요) {int((df['signal'] == 'YELLOW').sum())}건")
    if "saved_to" in df.attrs:
        print(f"\n상세 목록 저장: {df.attrs['saved_to']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
