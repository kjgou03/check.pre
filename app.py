"""Streamlit 화면.  실행: streamlit run app.py

화면은 얇게: 계산·판정은 전부 precheck/ 모듈이 하고, 여기서는 입력을 받고 결과를 그리기만 한다.
"""
import pandas as pd
import streamlit as st

import config
from precheck import audit, batch, data, impact, llm, orchestrator, report
from precheck.report import CHECK_LABEL, SIGNAL_EMOJI, SIGNAL_LABEL
from precheck.schemas import Report

st.set_page_config(page_title="PreCheck", page_icon="🚦", layout="wide")
st.title("🚦 PreCheck — 투자안 사전 점검")
st.caption("배제목록·제재목록·투자한도·이해상충을 대조해 **근거가 붙은 신호등 보고서**를 만듭니다. 최종 판단은 담당자.")

manifest = data.load_manifest()
with st.sidebar:
    st.subheader("상태")
    st.write("LLM:", f"사용 중 (`{config.LLM_MODEL}`)" if llm.enabled() else "미사용 — 템플릿·정규식 폴백")
    st.subheader("데이터")
    for name, info in manifest.items():
        st.markdown(f"`{name}` — **{info['status']}**")
    if any(v["status"] != "REAL" for v in manifest.values()):
        st.warning("샘플·모의 데이터가 포함되어 있습니다. 수치는 동작 확인용입니다.")
    st.subheader("최근 점검 이력 (감사 로그)")
    for row in audit.recent(5):
        st.caption(f"#{row['id']} {row['ts'][:16].replace('T', ' ')} UTC · 모드 {row['mode']} · "
                   f"{row['company'] or '포트폴리오'} · {row['overall']}")

tab_a, tab_b, tab_c = st.tabs(["① 사전 점검 (모드 A)", "② 정기 스크리닝 (모드 B)", "③ 규정 변경 영향 (모드 B-2)"])


# ── 모드 A ─────────────────────────────────────────────
def staff_label(sid: str) -> str:
    staff = data.load_staff()
    row = staff[staff["staff_id"] == sid]
    if row.empty:
        return f"{sid} (미등록)"
    n = int(((row["ticker"] != "") | (row["company_name"] != "")).sum())
    return f"{sid} {row.iloc[0]['staff_name']} (등록 보유 {n}건)"


def render_report(r: Report) -> None:
    st.markdown(f"### 종합 신호: {SIGNAL_EMOJI[r.overall]} {r.overall} ({SIGNAL_LABEL[r.overall]})")
    cols = st.columns(len(r.checks))
    for col, c in zip(cols, r.checks):
        col.markdown(f"{CHECK_LABEL[c.check_id]}  \n**{SIGNAL_EMOJI[c.signal]} {SIGNAL_LABEL[c.signal]}**")

    st.markdown("#### 점검 결과 (행을 펼치면 근거 원문)")
    for c in r.checks:
        with st.expander(f"{SIGNAL_EMOJI[c.signal]} **{CHECK_LABEL[c.check_id]}** — {c.headline}",
                         expanded=c.signal == "RED"):
            for e in c.evidence:
                st.markdown(f"- `{e.source_id}` {e.text}")
            if not c.evidence:
                st.markdown("- (근거 없음 — 판정 불가 사유는 위 제목 참고)")
            if c.confidence is not None:
                st.caption(f"이름 매칭 신뢰도 {c.confidence:.2f}")

    left, right = st.columns(2)
    with left:
        st.markdown("#### 요약")
        st.write(r.summary)
    with right:
        st.markdown("#### 필요한 승인")
        for a in r.required_approvals or ["없음"]:
            st.markdown(f"- {a}")
        if r.open_questions:
            st.markdown("#### 확인 질문")
            for q in r.open_questions:
                st.markdown(f"- {q}")

    md = report.to_markdown(r)
    with st.expander("Markdown 보고서 전체 보기"):
        st.markdown(md)
    st.download_button("보고서 다운로드 (.md)", md, file_name=f"precheck_{r.proposal.company_name}.md")
    st.caption(f"⚠️ {r.disclaimer}")


with tab_a:
    staff_ids = sorted(data.load_staff()["staff_id"].unique()) + ["S999"]  # S999 = 미등록 담당자 시연용
    mode = st.radio("입력 방식", ["폼 입력", "자유 입력 (문장)"], horizontal=True)
    with st.form("precheck"):
        if mode == "폼 입력":
            c1, c2, c3 = st.columns([3, 1.3, 2])
            company = c1.text_input("기업명", "Altria Group")
            amount_eok = c2.number_input("금액 (억 원)", min_value=0.0, value=150.0, step=10.0)
            staff_id = c3.selectbox("담당자", staff_ids, format_func=staff_label)
            memo = st.text_input("메모 (선택)")
        else:
            text = st.text_area("투자안을 한 문장으로",
                                "Altria Group에 150억 추가 투자하려고 해요, 담당자 S001")
            if not llm.enabled():
                st.caption("LLM 키가 없어 정규식으로 읽습니다 — 기업명은 영문으로, 금액은 '150억', 담당자는 'S001' 형태로.")
        submitted = st.form_submit_button("점검 실행", type="primary")

    if submitted:
        with st.spinner("점검 중…"):
            if mode == "폼 입력":
                st.session_state["a_result"] = orchestrator.run(
                    company=company, amount_krw=amount_eok * 1e8, staff_id=staff_id, memo=memo or None)
            else:
                st.session_state["a_result"] = orchestrator.run(text)

    result = st.session_state.get("a_result")
    if isinstance(result, list):
        st.warning("점검을 시작하려면 다음 정보가 필요합니다:\n\n" + "\n".join(f"- {q}" for q in result))
    elif result is not None:
        render_report(result)


# ── 모드 B ─────────────────────────────────────────────
with tab_b:
    st.write("보유내역 전체를 최신 배제·제재 목록, 단일종목 한도와 다시 대조합니다. (분기마다 / 목록 갱신 시)")
    if st.button("스크리닝 실행", type="primary"):
        with st.spinner("보유 종목 대조 중…"):
            st.session_state["b_df"] = batch.run()

    df = st.session_state.get("b_df")
    if df is not None:
        st.info(batch.reference_note())
        red = df[df["signal"] == "RED"]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("🔴 RED 종목", f"{len(red)}건")
        m2.metric("RED 합계 (USD)", f"${red['value_usd'].sum() / 1e9:,.2f}B")
        m3.metric("원화 환산", f"{red['value_usd'].sum() * config.FX_KRW_USD / 1e12:,.2f}조 원")
        m4.metric("🟡 확인 필요", f"{int((df['signal'] == 'YELLOW').sum())}건")

        st.markdown("#### 테마별 합계")
        st.dataframe(batch.summarize(df), hide_index=True, use_container_width=True)

        st.markdown("#### 상세 (펼치면 목록 행 원문)")
        for _, row in df.iterrows():
            title = (f"{SIGNAL_EMOJI[row['signal']]} {row['issuer_name']} ({row['ticker']}) — "
                     f"{row['theme']} · ${row['value_usd']:,.0f} (비중 {row['weight_pct']:.2f}%)")
            with st.expander(title):
                st.markdown(f"- 매칭: **{row['matched_name'] or '-'}** ({row['list_source']}"
                            + (f", {row['match_score']}점" if pd.notna(row['match_score']) else "") + ")")
                for line in row["evidence"].split(" / "):
                    st.markdown(f"- {line}")
        st.download_button("상세 CSV 다운로드", df.to_csv(index=False).encode("utf-8-sig"),
                           file_name="batch_screening.csv", mime="text/csv")

# ── 모드 B-2 ───────────────────────────────────────────
with tab_c:
    st.write("새 배제·제재 목록(CSV)이나 공지 문서(.txt/.md)를 넣으면, 보유 종목 중 **새로 걸리는 종목**을 바로 뽑습니다. "
             "문서는 LLM이 기업명을 추출합니다(키 필요).")
    up = st.file_uploader("새 목록 / 문서", type=["csv", "txt", "md"])
    use_example = st.button("예시 파일로 실행 (data/samples/new_list_example.csv — 가상 목록)")
    source = None
    if up is not None:
        source = (up.name, up.getvalue().decode("utf-8"))
    elif use_example:
        ex_path = config.SAMPLES_DIR / "new_list_example.csv"
        source = (ex_path.name, ex_path.read_text(encoding="utf-8"))
    if source is not None:
        try:
            with st.spinner("새 목록 읽고 보유 종목과 대조 중…"):
                st.session_state["c_result"] = impact.run(impact.parse_new_list(*source))
        except ValueError as e:
            st.error(str(e))

    res = st.session_state.get("c_result")
    if res is not None:
        s = res["summary"]
        m1, m2, m3 = st.columns(3)
        m1.metric("새로 추가된 기업", f"{s['added']}개", help=f"새 목록 {s['new_list']}개 중 기존 목록에 이미 있음 {s['already_listed']}개")
        m2.metric("🔴 새로 RED가 된 보유 종목", f"{s['newly_red']}건")
        m3.metric("해당 금액 (원화 환산)", f"{s['newly_red_usd'] * config.FX_KRW_USD / 1e8:,.0f}억 원",
                  help=f"${s['newly_red_usd']:,} × 환율 {config.FX_KRW_USD:,}원/$")
        st.markdown("#### 영향받는 보유 종목 (before = 기존 목록 기준 신호)")
        st.dataframe(res["detail"], hide_index=True, use_container_width=True)
        with st.expander("새로 추가된 기업 (추출·정리 결과 — 사람이 확인)"):
            st.dataframe(res["added"], hide_index=True, use_container_width=True)
        with st.expander("기존 목록에 이미 있던 기업"):
            st.dataframe(res["already"], hide_index=True, use_container_width=True)

# ── 하단: 데이터 기준일 + 고지문 ─────────────────────────
st.divider()
h, ex = manifest["holdings.csv"], manifest["exclusion_list.csv"]
st.caption(f"보유내역 기준일 {h.get('as_of') or '미상'} [{h['status']}] · "
           f"배제목록 게시일 {ex.get('as_of') or '미상'} [{ex['status']}] · 환율 {config.FX_KRW_USD:,}원/$ · "
           "본 화면은 참고용이며 최종 판단은 담당자가 합니다.")
