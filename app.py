"""Streamlit 화면.  실행: streamlit run app.py

화면은 얇게: 계산·판정은 전부 precheck/ 모듈이 하고, 여기서는 입력을 받고 결과를 그리기만 한다.
"""
import pandas as pd
import streamlit as st

import config
from precheck import batch, data, llm, orchestrator, report
from precheck.report import CHECK_LABEL, SIGNAL_EMOJI
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

tab_a, tab_b = st.tabs(["① 사전 점검 (모드 A)", "② 포트폴리오 스크리닝 (모드 B)"])


# ── 모드 A ─────────────────────────────────────────────
def staff_label(sid: str) -> str:
    staff = data.load_staff()
    row = staff[staff["staff_id"] == sid]
    if row.empty:
        return f"{sid} (미등록)"
    n = int(((row["ticker"] != "") | (row["company_name"] != "")).sum())
    return f"{sid} {row.iloc[0]['staff_name']} (등록 보유 {n}건)"


def render_report(r: Report) -> None:
    st.markdown(f"### 종합 신호: {SIGNAL_EMOJI[r.overall]} {r.overall}")
    cols = st.columns(len(r.checks))
    for col, c in zip(cols, r.checks):
        col.markdown(f"{CHECK_LABEL[c.check_id]}  \n#### {SIGNAL_EMOJI[c.signal]} {c.signal}")

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
    st.write("보유내역 전체를 배제·제재 목록과 대조합니다.")
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
                     f"{row['theme']} · ${row['value_usd']:,.0f}")
            with st.expander(title):
                st.markdown(f"- 매칭: **{row['matched_name'] or '-'}** ({row['list_source']}"
                            + (f", {row['match_score']}점" if pd.notna(row['match_score']) else "") + ")")
                for line in row["evidence"].split(" / "):
                    st.markdown(f"- {line}")
        st.download_button("상세 CSV 다운로드", df.to_csv(index=False).encode("utf-8-sig"),
                           file_name="batch_screening.csv", mime="text/csv")

# ── 하단: 데이터 기준일 + 고지문 ─────────────────────────
st.divider()
h, ex = manifest["holdings.csv"], manifest["exclusion_list.csv"]
st.caption(f"보유내역 기준일 {h.get('as_of') or '미상'} [{h['status']}] · "
           f"배제목록 게시일 {ex.get('as_of') or '미상'} [{ex['status']}] · 환율 {config.FX_KRW_USD:,}원/$ · "
           "본 화면은 참고용이며 최종 판단은 담당자가 합니다.")
