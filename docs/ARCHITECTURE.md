# 구조 설명 — 코드 읽는 법

전체 약 1,250줄. 아래 순서대로 읽으면 하루 안에 전부 이해할 수 있게 짰습니다.

## 1. 큰 그림

```
                       ┌──────────── LLM 사용 ────────────┐
 "Altria에 150억,      │                                  │
  담당자 S001"  ──▶ ① intake ──▶ Proposal                 │
                                   │                      │
            ┌──────────────────────┼──────────────────┐   │
            ▼                      ▼                  ▼   │
     ③ screening             ④ limits           ⑤ conflicts   ← 전부 순수 코드 (LLM 금지)
     exclusion / sanctions   single / sector    check
            │                      │                  │
            └────────── CheckResult × 5 ──────────────┘
                                   │
                                   ▼
                              ⑥ report.build ──▶ Report ──▶ to_markdown / Streamlit
                       (overall·승인·질문 = 코드, summary = LLM → 코드가 검증)
```

- **모드 A** (`orchestrator.py`): 위 흐름을 투자안 1건에 대해 한 번.
- **모드 B** (`batch.py`): 보유 종목 하나하나를 "금액 0원짜리 투자안"으로 보고 ③만 반복. 새 로직 없음.

## 2. 읽는 순서

| 순서 | 파일 | 볼 것 |
|---|---|---|
| 1 | `precheck/schemas.py` | 데이터 3단계: `Proposal` → `CheckResult` → `Report`. 이것만 알면 나머지는 "이 모양을 만드는 함수들"입니다. `CheckResult`의 validator가 **근거 없는 RED/YELLOW를 아예 못 만들게** 막습니다. |
| 2 | `config.py` | 숫자·경로·모델명이 전부 여기 있습니다. |
| 3 | `precheck/data.py` | 파일 로딩과 **기업명 정규화**. `normalize_name`(13F 줄임말 → 정식명)과 `match_score`(왜 점수 두 개의 평균인지 주석 참고)가 이 프로젝트에서 제일 까다로운 부분입니다. |
| 4 | `precheck/rules.py` | 조문을 `Evidence`로 감싸는 함수들. `param()`으로 한도 숫자(3%, 0.8)를 규정 파일에서 읽습니다. |
| 5 | `precheck/screening.py` | 배제·제재 판정 규칙(RED/YELLOW/GREEN). 맨 위 docstring의 표가 곧 명세입니다. |
| 6 | `precheck/limits.py` | 비중 계산. `before_pct`, `after_pct` 두 줄이 핵심. |
| 7 | `precheck/conflicts.py` | 담당자 보유 종목 대조. 미등록 담당자는 UNKNOWN. |
| 8 | `precheck/report.py` | `decide_overall` → `validate_summary` → `make_summary` → `build` 순서로. **환각 차단 로직**이 여기 있습니다. |
| 9 | `precheck/llm.py` | LLM 호출 단일 창구. 실패하면 `None` → 호출한 쪽이 폴백. |
| 10 | `precheck/intake.py` | 자유 입력 → `Proposal`. LLM 추출과 정규식 폴백. |
| 11 | `precheck/orchestrator.py`, `batch.py`, `app.py` | 위 부품을 조립만 합니다. |

## 3. 설계 포인트 (발표 때 질문 받을 만한 것)

**① LLM은 두 군데뿐, 그리고 숫자·판정은 절대 LLM이 안 만든다**
- `intake`(문장 → JSON 추출)와 `report`(요약 문장 작성)만 LLM을 씁니다.
- 신호(RED/GREEN), 종합 신호, 필요한 승인, 비중 계산은 전부 코드. LLM이 틀려도 판정은 안 바뀝니다.

**② 근거 검증 = 환각 차단** (`report.validate_summary`)
- 요약에 나온 `[IG-x-x]`가 (a) 규정 파일에 실제로 있고 (b) 이번 점검 근거에 실제로 쓰였는지 확인.
- 요약에 나온 숫자가 점검 근거 텍스트에 실제로 있는지 확인.
- 실패 → 문제를 알려주고 재생성(최대 2회) → 그래도 실패 → 코드가 만든 템플릿 요약으로 대체.
- 시연: `tests/test_report.py::test_hallucinated_llm_summary_falls_back_to_template`

**③ GREEN에도 근거가 붙는다**
- "해당 없음"도 "무엇과 몇 건을 대조해서 해당 없음인지"를 evidence로 남깁니다.
- 판정할 수 없으면(벤치마크 데이터 없음, 담당자 미등록) 숨기지 않고 UNKNOWN + 이유.

**④ 이름 매칭은 일부러 보수적으로**
- `token_set_ratio`만 쓰면 `Southern Co`(석탄)과 `Southern Copper`(구리)가 100점 → 오탐 RED.
- 그래서 `token_sort_ratio`와 평균 → 부분 일치는 85점 → YELLOW "동일 기업인지 확인 필요".
- LLM 키 없이 한글 기업명이 들어오면 추측하지 않고 "영문으로 알려달라"고 되묻습니다.
  (잘못된 이름으로 대조해서 GREEN이 나오는 것이 이 시스템에서 가장 위험한 실패이기 때문)

**⑤ 데이터 출처가 보고서에 찍힌다**
- `data/manifest.json`의 `status`(REAL/SAMPLE/MOCK/EMPTY)가 보고서 "참조 데이터"와 화면 사이드바에 그대로 나옵니다.

## 4. 명세(02번 문서)와 다르게 한 것

| 항목 | 명세 | 구현 | 이유 |
|---|---|---|---|
| 이름 점수 | `token_set_ratio` | `token_set`·`token_sort` 평균 | 부분 일치 오탐 방지 (위 ④) |
| `rules.py` | Step 4 | Step 2에서 먼저 작성 | screening이 조문 근거를 붙이려면 필요 |
| 요약 검증 | 존재하는 조문인지 | + 이번 점검 근거에 쓰인 조문인지 | 실존하지만 무관한 조항 인용도 차단 |
| 데이터 출처 | 각 CSV의 날짜 컬럼 | `manifest.json` 추가 | 샘플/실데이터 구분을 보고서에 표시 |
| `law` 점검 | (선택) | 미구현 | `kic_act_sample.json`이 비어 있음. 채우면 `orchestrator.run_checks`에 추가 |
| CLI `--staff` | DoD 예시엔 없음 | 필수 | 02번 명세상 담당자는 필수값 → 없으면 질문하고 중단 |

## 5. 확장할 때 손댈 곳
- **실데이터 교체**: `data/` 파일만 바꾸고 `manifest.json` 갱신. 코드 수정 불필요.
- **섹터 한도 판정**: `limits.sector()`의 TODO — 벤치마크 섹터 비중 CSV를 추가해 ±5%p 비교.
- **새 점검 항목**: `CheckResult`를 돌려주는 함수를 만들고 `orchestrator.run_checks`에 한 줄 추가. `check_id`는 `schemas.py`의 Literal에도 추가.
- **LangGraph 이관**: 각 점검 함수가 `Proposal → CheckResult` 순수 함수라서 그대로 노드로 옮기면 됩니다.
