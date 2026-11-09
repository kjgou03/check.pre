# PreCheck — 투자안 사전 점검 에이전트 (MVP)

투자안(기업·금액·담당자)을 넣으면 **법령·배제목록·제재목록·투자한도·이해상충**을 대조해
**근거가 붙은 신호등 보고서 1장**을 만듭니다. 최종 판단은 사람이 합니다.

| 모드 | 하는 일 |
|---|---|
| A. 사전 점검 | 투자안 1건 → 6개 항목 병렬 점검 → 신호등 보고서 (🟢적합 🟡확인 필요 🔴위반 가능 ⚪확인 불가) |
| B. 정기 스크리닝 | 보유 종목 전체를 배제·제재 목록, 단일종목 한도와 다시 대조 |
| B-2. 규정 변경 영향 | 새 목록(CSV)·공지 문서를 넣으면 보유 종목 중 새로 걸리는 종목 산출 |

> ⚠️ 지금 `data/`에 든 데이터는 **샘플·모의 데이터**입니다. 발표 전에 [data/README.md](data/README.md)를 보고 실데이터로 교체하세요.

## 설치·실행

```bash
pip install -r requirements.txt
```

```bash
cp .env.example .env   # (선택) ANTHROPIC_API_KEY 입력. 없어도 전부 동작합니다
```

```bash
streamlit run app.py
```

## 데모 명령

```bash
python -m precheck.orchestrator --company "Altria Group" --amount 15000000000 --staff S002
```

```bash
python -m precheck.batch
```

```bash
python -m precheck.impact data/samples/new_list_example.csv
```

담당자를 `S001`(알트리아 보유)로 바꾸면 이해상충 RED가 추가됩니다. 금액은 `--amount 150억`처럼 써도 됩니다.
자유 입력은 `--text "Altria Group에 150억 투자, 담당자 S001"`.

## 테스트

```bash
pytest
```

API 키 없이(템플릿 폴백) 59개 테스트가 돕니다. 04번 문서 시나리오는 `tests/test_scenarios.py`.
실제 LLM까지 태워 보려면 `.env`에 키를 넣고 `PRECHECK_TEST_LLM=1 pytest`.

## 구조

코드를 어떤 순서로 읽으면 되는지, 각 파일이 무슨 일을 하는지는 **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** 에 정리했습니다.

```
config.py            설정 한 곳 (모델명, 환율, 매칭 임계값, 경로)
precheck/
  schemas.py         데이터 모양 (Proposal → CheckResult → Report)
  data.py            CSV/JSON 로더 + 기업명 정규화·매칭
  rules.py           ② 규정 조회 + 법령 점검 (조문 ID 실존 확인)
  intake.py          ① 입력 → Proposal          (LLM, 없으면 정규식)
  screening.py       ③ 배제·제재 대조            (코드)
  limits.py          ④ 한도·비중 계산            (코드)
  conflicts.py       ⑤ 이해상충                  (코드)
  report.py          ⑥ 보고서 + 근거 검증        (요약만 LLM)
  llm.py             LLM 호출 단일 창구
  orchestrator.py    모드 A (투자안 1건, 6개 점검 병렬)
  batch.py           모드 B (보유내역 전체)
  impact.py          모드 B-2 (규정 변경 영향 분석)
  audit.py           감사 로그 (output/audit.db, SQLite)
app.py               Streamlit 화면 (탭 3개)
data/                샘플 데이터 + manifest.json(출처·기준일·샘플 여부) + samples/(B-2 예시, 가상)
tests/               단계별 테스트 + 시나리오 테스트
```

## 데이터 출처 (실데이터 교체용)
- 보유내역: [SEC EDGAR](https://www.sec.gov/edgar/search/) — Korea Investment Corp, Form 13F-HR
- 배제목록: [NBIM Exclusion of companies](https://www.nbim.no/en/responsible-investment/ethical-exclusions/exclusion-of-companies/), [Urgewald Global Coal Exit List](https://www.coalexit.org/)
- 제재목록: [OFAC SDN List](https://ofac.treasury.gov/specially-designated-nationals-and-blocked-persons-list-sdn-human-readable-lists)
- 법령: [국가법령정보센터 — 한국투자공사법](https://www.law.go.kr/)

## 고지
본 보고서는 참고용이며 최종 판단은 담당자가 합니다.
