# data/ — 데이터 파일 안내

> ⚠️ **지금 들어 있는 데이터는 전부 샘플·모의 데이터입니다.** 코드 흐름을 확인하기 위한 것이므로,
> 발표 전에 아래 방법으로 실데이터로 교체하고 `manifest.json`의 `status`를 `REAL`로 바꾸세요.
> 보고서 하단 "참조 데이터"에 이 status가 그대로 찍히므로, 샘플을 실데이터처럼 보여줄 일은 없습니다.

| 파일 | 지금 상태 | 교체 방법 |
|---|---|---|
| `holdings.csv` | SAMPLE (13F 형식의 가상 금액) | SEC EDGAR → "Korea Investment Corp" 최신 13F-HR → information table. 천 달러 단위면 ×1000. 상위 200개면 충분 |
| `exclusion_list.csv` | SAMPLE (NBIM·GCEL 기업명 일부 수기 입력) | NBIM "Observation and exclusion of companies" 표 복사, Urgewald GCEL 2025 다운로드 후 holdings와 겹치는 것만 |
| `sanctions.csv` | SAMPLE (OFAC SDN 법인 10곳 수기 발췌) | treasury.gov `sdn.csv` → `SDN_Type`이 `-0-`(=법인)인 행만 → `name, program, source=OFAC_SDN, list_date=다운로드일` |
| `staff_holdings.csv` | MOCK (원래 비공개) | 그대로 사용 |
| `rules/internal_guideline.json` | MOCK (원래 비공개) | 그대로 사용 |
| `rules/kic_act_sample.json` | EMPTY | law.go.kr 한국투자공사법 자산운용 조문 5~10개. `{"rule_id": "ACT-제N조", "title", "text"(원문 그대로), "category": "law", "param": {}}` |

## 규칙
- 모든 CSV는 **UTF-8**.
- `exclusion_list.csv`의 `source = KIC_theme_keyword` 행은 기업이 아니라 **키워드**입니다
  (`company_name` 칸에 `tobacco`, `coal` 등). 기업명/섹터에 이 단어가 있으면 🟡 "키워드 기반 후보"가 됩니다.
  `controversial_weapons`, `child_labor`는 이름만으로 잡을 수 없어 키워드가 없습니다.
- `staff_holdings.csv`에서 `ticker`·`company_name`이 빈 행 = "보유 종목 없음으로 등록된 담당자"(예: S002).
  아예 행이 없는 담당자(예: S999)는 **미등록** → 이해상충 점검이 UNKNOWN이 됩니다.
- 데이터를 바꾸면 `manifest.json`의 `status`, `source`, `as_of`도 같이 고치세요.

## 실데이터로 바꿀 때 예상되는 변화
- 실제 13F에서는 애플·마이크로소프트 같은 메가캡의 비중이 3%를 넘을 가능성이 큽니다.
  그러면 모의 지침 `IG-3-1`(단일종목 3%) 때문에 "정상 케이스(Microsoft)"의 `limit_single`이 RED가 됩니다.
  → 13F는 미국 상장주식만 담고 있어 "전체 주식 포트폴리오"보다 작다는 점을 감안해 분모를 정하거나, 모의 한도를 조정하세요.
