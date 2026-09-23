# AXPORT 판정 구조 설계

- 작성일: 2026-09-22
- 버전: 0.1
- 상태: **설계 초안 — 스키마 구조만 정의함. 판정 규칙 내용·점수 기준은 비어 있다.**
- 기준 문서: [AXPORT 초기개발명세](../../AXPORT_초기개발명세.md) §3·§4·§6·§7 / [design.md](../../design.md)
- 위치 근거: CONTRIBUTING §7 — `rules/` = 검토된 판정 규칙

## 이 문서가 정하지 않는 것

명세서 §6 에 따라 아래는 **의도적으로 비워 둔다.** 채우려면 사용자 승인과 검토 절차가 필요하다.

| 비워 둔 것 | 이유 |
|---|---|
| 점수 항목·가중치·임계값의 구체적 숫자 | 명세서 §6 — 중앙 설정으로 관리하고 근거·검토 상태를 기록한다. 모델이 임의로 생성해 확정하지 않는다. §2 「점수 항목·가중치·임계값의 검토 및 승인 절차」 미정 |
| 수출규제 판정 규칙의 내용 | **별표2의2(상황허가 대상품목, HS코드 명시) 와 별표6(수출지역 구분) 이 미다운로드 상태.** 별표1~4 도 `원문대조 필요`. 명세서 §7 — 미검토 규칙을 운영 판정에 사용하지 않는다 |
| 판정 라벨 문자열의 최종 확정 | 명세서 §4 — 용어사전에서 관리한다. 아래 enum 은 구조를 보이기 위한 제안이며 승인 대상 |

구조적으로 금지한 것: **사업적 적합도 점수가 필수 조건 미충족을 상쇄할 수 있는 경로를 만들지 않았다.** 근거는 §3.4 종합 판정 도출.

---

## 1. 값 상태 타입 — `MeasuredValue` (명세서 §4)

다섯 상태를 **절대 같은 값으로 표현하지 않는다.** 모든 지표·필드는 원시 스칼라가 아니라 이 구조로 감싼다.

```
MeasuredValue
├─ state              (필수) 아래 5개 중 하나
├─ value              state = actual 일 때만 존재. 그 외에는 필드 자체가 없다
├─ unit               수량 단위
├─ currency           ISO 4217
├─ amount_multiplier  1 / 1000 / 1000000  (값과 분리 보관, 명세서 §3)
├─ period             { start, end }  기간 지표인 경우
├─ reason_code        state ≠ actual 일 때 필수
├─ source_id          external_sources[].source_id 참조
└─ asof_date          자료 기준일 (YYYY-MM-DD, 날짜형)
```

### 1.1 다섯 상태

| state | 뜻 | `value` 필드 | 화면 표기 (design.md) | 집계 처리 |
|---|---|---|---|---|
| `actual` | 실제 측정·계산된 값. **0 도 여기에 속한다** | 존재 (0 가능) | 값 + 단위·통화·기간 | 합산·평균에 포함 |
| `not_entered` | 업로드에 값이 없음 (미입력) | **없음** | `자료 부족` | **포함 불가.** 이 값을 쓰는 지표 전체가 `not_evaluated` 가 된다 |
| `not_evaluated` | 계산·판정을 시도하지 않음 (규칙 미확보, 설정 미승인, 선행 입력 부족) | **없음** | `평가 보류` | 포함 불가 |
| `not_applicable` | 이 행·이 맥락에 해당 없음 | **없음** | `해당 없음` | 분모에서 제외 |
| `fetch_failed` | 외부 조회 실패 (연결 실패·권한 없음·자료 없음·오래된 캐시) | **없음** | `조회 실패` + 재시도 경로 | 포함 불가 |

`reason_code` 권장 값 — 목록 확정은 승인 대상:
`missing_required_input`, `rule_set_unreviewed`, `rule_source_missing`, `scoring_config_unapproved`, `upstream_value_not_evaluated`, `api_connection_failed`, `api_no_data`, `api_no_permission`, `cache_stale_exceeded`, `not_in_scope`

### 1.2 금지 표현

- 결측을 `0` 으로 치환하지 않는다. `0` 은 `state=actual, value=0` 뿐이다.
- 다섯 상태를 `null` 하나로 합치지 않는다. `null` 만 보고는 미입력/미평가/해당없음/조회실패를 구분할 수 없다.
- `""`, `"-"`, `"N/A"`, `"미정"` 같은 문자열을 값 칸에 섞지 않는다. 업로드 양식의 `N/A` 는 파싱 단계에서 `state=not_applicable` 로 변환한다.
- `NaN`, `-1`, `999`, `9999-12-31` 같은 센티넬 값을 쓰지 않는다.
- 색상만으로 상태를 구분하지 않는다 (명세서 §9). 상태 문구를 함께 표시한다.

### 1.3 전파 규칙

- 입력 중 하나라도 `not_entered` / `fetch_failed` / `not_evaluated` 면 파생 지표는 `not_evaluated` + `reason_code=upstream_value_not_evaluated` 가 된다. **부분 합산으로 낙관적 값을 만들지 않는다.**
- `not_applicable` 만으로 구성된 집계는 `not_applicable` 이다.
- 금액 계산과 화면 반올림을 분리한다 (명세서 §4). `MeasuredValue` 는 계산값을 담고, 반올림은 표시 계층에서 `rounding_policy_ref` 로 적용한다.

---

## 2. 판정 결과 3층 구조 (명세서 §6)

세 층은 **서로 독립 저장**된다. 한 층의 값이 다른 층의 값을 바꾸지 못한다.

```
EvaluationResult
├─ mandatory_review    1층 · 필수 조건 검토
├─ business_fitness    2층 · 사업적 적합도
├─ evidence_status     3층 · 근거 충족 상태
└─ overall             세 층에서 도출 (§3.4 규칙)
```

### 2.1 1층 — `mandatory_review` (필수 조건 검토)

규제·허가·원산지 등 **법적 가능 여부**를 다룬다. 점수가 아니다 (명세서 §6 — 점수는 성공 확률·법적 허가 여부와 구분한다).

| 필드 | 타입 | 설명 |
|---|---|---|
| `status` | enum | `not_evaluated` / `withheld` / `satisfied` / `unsatisfied` / `needs_more_info` |
| `status_reason_code` | string | `status` 가 `satisfied` 가 아닌 이유 |
| `confirmed_conditions[]` | list | **확인된 조건** |
| `unsatisfied_conditions[]` | list | **미충족 조건** |
| `pending_checks[]` | list | **추가 확인 사항** |
| `blocking_unsatisfied_count` | int | `unsatisfied_conditions` 중 `blocking=true` 개수 |
| `blocking_pending_count` | int | `pending_checks` 중 `blocking=true` 개수 |

`confirmed_conditions[]` 항목:

| 필드 | 설명 |
|---|---|
| `condition_id` | 이 평가 실행 안의 조건 식별자 |
| `rule_id`, `rule_version` | 적용한 규칙과 버전 |
| `rule_review_status` | `reviewed` / `unreviewed` / `source_missing`. **`reviewed` 가 아니면 운영 판정에 쓰지 않는다** (§7) |
| `title` | 조건명 |
| `legal_basis` | 근거 규정명·조항 |
| `announced_date`, `effective_date` | 발표일과 시행일을 구분한다 (§7) |
| `source_ref` | `evidence_locations[].evidence_id` |
| `verdict` | `met` / `met_with_condition` |
| `evidence_refs[]` | 증빙목록 시트의 증빙ID 등 |
| `checked_at` | UTC 타임스탬프 |

`unsatisfied_conditions[]` 항목: 위 필드 + `reason_code`, `blocking`(bool), `required_action`, `remediable`(bool)

`pending_checks[]` 항목:

| 필드 | 설명 |
|---|---|
| `check_id` | 식별자 |
| `question` | 무엇을 확인해야 하는지 |
| `required_inputs[]` | 필요한 업로드 필드 경로 |
| `required_sources[]` | 필요한 외부 자료 `source_id` |
| `blocking` | true 면 종합 판정을 막는다 |
| `owner_role` | 확인 주체 |

> **현재 상태**: 수출규제 조건 집합은 비어 있다. 별표2의2·별표6 미확보, 별표1~4 `원문대조 필요`. 따라서 규제 영역의 `status` 는 `withheld` + `reason_code=rule_source_missing` 으로 고정된다.

### 2.2 2층 — `business_fitness` (사업적 적합도)

**계산 가능한 영역만** 평가한다. 이 층은 1층을 바꾸지 못한다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `status` | enum | `not_evaluated` / `partial` / `evaluated` |
| `areas[]` | list | 영역별 평가. 영역 코드: `market` / `price` / `logistics` / `stability` |
| `composite` | `MeasuredValue` | 종합 사업성. **가중치 미승인 상태에서는 `not_evaluated`** |
| `scoring_config_ref` | object | `{ config_id, version, review_status, approved_by, approved_at }` |
| `excluded_areas[]` | list | `{ area_code, reason_code, required_inputs[], required_sources[] }` |

`areas[]` 항목:

| 필드 | 설명 |
|---|---|
| `area_code` | `market` / `price` / `logistics` / `stability` |
| `status` | `not_evaluated` / `partial` / `evaluated` |
| `metrics[]` | `{ metric_id, label_key, value: MeasuredValue, formula_ref, calc_id, source_refs[] }` |
| `subscore` | `MeasuredValue`. 임계값·가중치 미승인 시 `not_evaluated` |
| `coverage` | `{ metrics_total, metrics_actual, metrics_not_evaluated, metrics_not_applicable }` |
| `notes_key` | design.md 의 "짧은 설명 1줄" 번역 키 |

제약:

- `composite` 는 `subscore` 들로부터만 계산한다. `mandatory_review` 값을 입력으로 받지 않는다.
- 같은 비용·위험이 여러 영역에서 중복 반영되지 않도록 `metrics[].metric_id` 를 단일 출처로 유지한다 (§6).
- 비교 화면에서는 `coverage` 가 다른 평가끼리 차이를 표시한다 (§6).

### 2.3 3층 — `evidence_status` (근거 충족 상태)

| 필드 | 설명 |
|---|---|
| `overall` | `insufficient` / `partial` / `sufficient` |
| `required_inputs[]` | `{ field_path, sheet, requirement_class, state, blocking_for[] }` |
| `requirement_class` | `common_required` / `area_required` / `optional` — 업로드 양식의 필수 구분과 1:1 대응 |
| `input_completeness_by_area[]` | `{ area_code, required_total, present, missing_fields[], state }` |
| `data_sources[]` | 아래 표 |
| `rule_readiness[]` | `{ rule_set_id, version, review_status, source_files[], usable_in_production }` |
| `assumption_flags[]` | `{ field_path, assumption_note, set_by }` — 가정값은 실제 자료와 구분 표시 (§7) |

`data_sources[]` 항목 — 명세서 §7 수집·저장 정책 전체를 필드로 만든다:

| 필드 | 설명 |
|---|---|
| `source_id` | 내부 식별자 |
| `kind` | `api` / `file` |
| `provider`, `service_name` | 제공기관·서비스명 |
| `registry_status` | `api_registry.csv` 의 `status` 사본 |
| `registry_verified` | `api_registry.csv` 의 `verified` 사본. **`검증완료` 가 아니면 확정 판정 근거로 쓰지 않는다** |
| `source_url`, `endpoint` | 출처 |
| `asof_date` | 자료 기준일 |
| `announced_date`, `effective_date` | 발표일 / 시행일 (규정 자료) |
| `collected_at` | 수집일 |
| `applies_from`, `applies_to` | 적용 시작·종료일 |
| `file_sha256`, `file_bytes` | 파일 자료의 해시·용량 (MANIFEST.csv 와 대조) |
| `version` | 자료 버전·개정판 |
| `license`, `redistribution` | 이용조건·재배포 범위 |
| `maintainer` | 갱신 담당 |
| `query_params` | API 조회 조건 (키 값은 저장하지 않는다) |
| `fetch_result` | `ok` / `no_data` / `no_permission` / `connection_failed` / `stale_cache_used` — **네 가지 실패를 구분해 반환한다** (§7) |
| `error_code`, `error_message` | 제공기관 에러코드 원문 |
| `cache_hit`, `age_days`, `max_age_config_ref`, `max_age_exceeded` | 오래된 자료 사용 여부 |
| `data_class` | `real` / `sample` / `user_input` / `assumption` — **화면·보고서에 구분 표시** (§7) |

> `data_class=sample` 인 자료는 `overall` 을 `sufficient` 로 올리지 못한다. **장애 시 샘플로 자동 대체해 실제 결과처럼 표시하지 않는다** (§7).

---

## 3. 종합 판정 도출 — 상쇄 불가 구조

### 3.1 `overall` 필드

| 필드 | 설명 |
|---|---|
| `decision` | `not_evaluated` / `withheld` / `blocked_mandatory` / `needs_more_info` / `proceed_with_conditions` |
| `decision_reason_codes[]` | 근거 코드 목록 |
| `gate_trace[]` | `{ gate_id, input_refs[], passed }` — 어느 게이트에서 막혔는지 |
| `business_fitness_ref` | 2층 참조. **참고 표시 전용** |
| `disclaimer_key` | "점수는 성공 확률·법적 허가 여부와 다르다" 문구 키 (§6) |

### 3.2 게이트 순서 (숫자 임계값 없음 — 존재 여부만 본다)

```
G1  rule_readiness 에 usable_in_production = false 가 있으면
        → decision = withheld            (규칙 미검토·원문 미확보)
G2  mandatory_review.blocking_unsatisfied_count > 0
        → decision = blocked_mandatory
G3  mandatory_review.blocking_pending_count > 0
        → decision = needs_more_info
G4  evidence_status.overall = insufficient
        → decision = needs_more_info
G5  위 전부 통과
        → decision = proceed_with_conditions
```

### 3.3 상쇄 금지를 보장하는 구조적 장치

1. `business_fitness` 는 **G1~G4 의 입력이 아니다.** 게이트 입력은 1층·3층뿐이다.
2. `decision` 에는 `proceed`(무조건 적합)에 해당하는 값이 없다. 최상위가 `proceed_with_conditions` 다.
3. `composite` 점수는 `overall` 안에 **참조로만** 들어간다. 계산 입력으로 들어가지 않는다.
4. 화면에서 규제 항목은 1층 소속이므로 점수 축에 올라가지 않는다 (§4 표).
5. 자료가 부족한 상태와 위험이 낮은 상태를 구분한다 — `not_evaluated` ≠ `actual` 이므로 타입 차원에서 섞이지 않는다 (§6).

---

## 4. 평가 실행 저장 구조 — `EvaluationRun` (명세서 §6)

§6 「평가 실행마다 보존할 정보」를 전부 필드로 만든다.

| 그룹 | 필드 | 설명 |
|---|---|---|
| **식별** | `run_id` | 평가 실행 고유 ID |
| | `run_seq` | 같은 대상의 실행 순번 |
| | `company_id` | 기업 고유 ID (표시명 아님, §3) |
| **입력 데이터셋·사용자 수정 버전** | `dataset.dataset_id` | 데이터셋 고유 ID |
| | `dataset.upload_id` | 업로드 건 ID |
| | `dataset.template_version` | 업로드 양식 버전 |
| | `dataset.original_file` | `{ display_name, server_path, sha256, bytes, uploaded_at }` — 파일명은 표시 정보, 저장 경로는 서버 생성 (§5) |
| | `dataset.normalized_version` | 정규화 데이터 버전 |
| | `dataset.user_correction_version` | 사용자 보정 버전 |
| | `dataset.correction_log_ref` | 보정 이력 위치 |
| **기업·제품·목적국·거래 조건** | `subject.product_id` | 제품 고유 ID |
| | `subject.product_snapshot_ref` | 평가 시점 제품 속성 스냅샷 |
| | `subject.hs_code`, `subject.hs_version`, `subject.hs_country` | 문자열 저장, 체계·버전·국가별 세번 구분 (§3) |
| | `subject.destination_country_code` / `_raw` | 표준 국가 코드 + 원본 값 보존 (§3) |
| | `subject.trade_terms` | `{ buyer_id, end_user, end_use, quantity, quantity_unit, unit_price, currency, amount_multiplier, incoterms, payment_terms, delivery_date }` |
| | `subject.analysis_mode` | `market_exploration` / `deal_evaluation` — 거래 조건 없는 탐색을 완결된 거래 판정으로 표시하지 않는다 (§3) |
| **분석 기간·기준일** | `subject.evaluation_base_date` | 평가 기준일 (날짜형) |
| | `subject.analysis_period` | `{ start, end }` 실적 분석 시작·종료일 (§3 별도 필드) |
| **규칙·엔진 버전** | `engine.rule_set_id`, `engine.rule_set_version` | 판정 규칙 버전 |
| | `engine.calc_engine_version` | 계산 엔진 버전 |
| | `engine.config_snapshot_id` | 중앙 설정 스냅샷 (§11) |
| | `engine.scoring_config_version` | 가중치·임계값 설정 버전 |
| **외부 자료** | `external_sources[]` | §2.3 `data_sources[]` 와 동일 스키마. 버전·기준일·조회 조건을 실행마다 고정 보관 |
| | `external_sources[].response_sample_ref` | 응답 원문 보관 위치 (예: `api-vault/specs/samples/`) |
| **결과** | `result.mandatory_review` / `.business_fitness` / `.evidence_status` / `.overall` | §2·§3 구조 |
| **계산식** | `calculations[]` | `{ calc_id, metric_id, formula_text, formula_ref, input_refs[], output: MeasuredValue, rounding_policy_ref, unit, currency, period }` |
| **근거 위치** | `evidence_locations[]` | `{ evidence_id, kind, source_id, locator, quote_ref }` |
| | `evidence_locations[].locator` | 파일: `{ file, page, table, row }` / API: `{ endpoint, field_path }` / 규정: `{ 고시번호, 별표, 항목 }` — 원문 위치를 유지한다 (§4) |
| **누락 입력** | `missing_inputs[]` | `{ field_path, sheet, requirement_class, blocking_for[], message_key }` |
| **후속 조치** | `follow_up_actions[]` | `{ action_id, description_key, owner_role, blocking, related_condition_id, due_hint }` |
| **실행 시각·주체** | `executed_at` | **UTC 타임스탬프** (§4) |
| | `executed_by` | `{ actor_type: user\|system\|schedule, user_id, org_id, role }` |
| | `display_timezone` | 화면 변환용 (기본 제안 Asia/Seoul, §2 제안) |
| | `duration_ms` | 실행 소요 시간 |
| **불변성** | `sealed` | true 면 이후 재계산 금지 |
| | `supersedes_run_id` / `superseded_by_run_id` | 재실행 체인 |
| | `new_run_reason` | `input_changed` / `rule_changed` / `source_changed` / `user_requested` |

### 4.1 불변성 규칙 (명세서 §6)

- 입력·규칙·외부 자료가 변경되면 **새 `EvaluationRun` 을 만든다.** 기존 run 을 수정하지 않는다.
- 과거 결과를 재조회할 때 **최신 자료로 조용히 다시 계산하지 않는다.** 최신 자료와 차이가 있으면 "다시 평가" 를 제안만 한다.
- 화면과 보고서는 **같은 `run_id`** 를 참조한다 (§6, §11).
- 필터·언어·테마 변경은 새 run 을 만들지 않는다. 필터 변경 후 이전 결과를 최신 결과처럼 표시하지 않는다 (§9).

---

## 5. design.md 메인 5개 항목 ↔ 구조 연결

design.md: 메인 화면에는 **규제·시장성·가격·물류·안정성** 5개만, 각 항목 **핵심 결과 1개 + 설명 1줄.** 상세는 책갈피 탭.

### 5.1 층 배치

| design.md 항목 | 소속 층 | 구조 경로 | 근거 |
|---|---|---|---|
| **규제** | **1층 필수 조건 검토** | `result.mandatory_review` | 법적 허가 여부. 점수가 아니다 (§6) |
| **시장성** | 2층 사업적 적합도 | `business_fitness.areas[market]` | 계산 가능 영역 |
| **가격** | 2층 사업적 적합도 | `business_fitness.areas[price]` | 계산 가능 영역 |
| **물류** | 2층 사업적 적합도 | `business_fitness.areas[logistics]` | 계산 가능 영역 |
| **안정성** | 2층 사업적 적합도 | `business_fitness.areas[stability]` | 계산 가능 영역 |

**규제를 1층에 둔 것이 상쇄 금지의 핵심이다.** 규제는 `composite` 계산에 들어가지 않으므로, 시장성·가격이 높아도 규제 미충족을 덮을 수 없다.

5개 항목 전부 `evidence_status` 에 대응하는 `input_completeness_by_area` 와 `data_sources` 항목을 갖는다.

### 5.2 데이터 소스와 현재 확보 상태

출처: `api-vault/registry/api_registry.csv`, `api-vault/reference_data/MANIFEST.csv` (2026-09-22 대조)

#### 규제

| 소스 | 종류 | 상태 | verified |
|---|---|---|---|
| 전략물자수출입고시 별표2의2 상황허가 대상품목 | 파일 | **미다운로드** | — |
| 전략물자수출입고시 별표6 수출지역 구분 | 파일 | **미다운로드** | — |
| 별표1 전략물자·기술 색인 | 파일 | 다운로드완료 | **원문대조 필요** |
| 별표2 이중용도품목 | 파일 | 다운로드완료 | **원문대조 필요** |
| 별표3 군용물자목록 | 파일 | 다운로드완료 | **원문대조 필요** |
| 별표4 통제번호 국제수출통제체제별 분류 | 파일 | 다운로드완료 | **원문대조 필요** |
| 관세청_세관장확인대상물품(GW) | API | 발급완료 | 미검증 |
| KOTRA_해외인증정보 | API | 발급완료 | 미검증 |
| KOTRA_국가 목록 (대한 수입규제 현황) | API | 발급완료 | 미검증 |
| US ITA Consolidated Screening List | API | 발급완료 | 미검증 (미국 CSL 기준임을 명시 필수) |
| 국가법령정보 Open API | API | 발급완료 | **검증완료 2026-09-22** |

**→ 현재 판정 불가.** `status=withheld`, `reason_code=rule_source_missing`.

#### 시장성

| 소스 | 종류 | 상태 | verified |
|---|---|---|---|
| 관세청_품목별 국가별 수출입실적(GW) | API | 발급완료 | **검증완료 2026-09-22** |
| UN Comtrade | API | 발급완료 | 미검증 |
| KOTRA_국가정보 | API | 발급완료 | 미검증 |
| 관세청_월별 품목별 국가별 수출입실적 | 파일 | 미다운로드 | — |
| World Bank Indicators / WITS, IMF, Eurostat Comext, OTS | API | 키불필요 | 미검증 |

**→ 부분 가능.** 한국 수출 추이는 검증된 소스가 있다. 대상국 수입시장(Comtrade)은 미검증.

#### 가격

| 소스 | 종류 | 상태 | verified |
|---|---|---|---|
| 관세청_품목번호별 관세율표 | 파일 | 다운로드완료 | **미검증** (MANIFEST) |
| 관세청_국가별 관세율표 43개국 | 파일 | 다운로드완료 | **미검증 · 법적효력 없는 참고용** |
| WTO Timeseries API (양허·실행·특혜) | API | 발급완료 | 미검증 |
| US ITA FTA Tariff Rates | API | 발급완료 | 미검증 |
| USITC HTS REST | API | 키불필요 | 미검증 |
| 관세청_관세환율정보(GW) | API | 발급완료 | 미검증 (관세율·결제환율과 구분) |
| ECOS 통계 API | API | 발급완료 | 미검증 |
| Frankfurter (ECB 환율) | API | 키불필요 | 미검증 |
| 원가·운송비·보험료·포장비 | 업로드 | 양식 `원가·비용` 시트 | 기업 입력 |

**→ 부분 가능·주의.** 관세율표는 참고용이며 미검증. 미국 관세표를 다른 국가에 쓰지 않는다 (§7).

#### 물류

| 소스 | 종류 | 상태 | verified |
|---|---|---|---|
| 해양수산부_선박운항정보 | API | 발급완료 | 미검증 (**스케줄만. 실제 운임·납기 아님**) |
| 해양수산부_항만별 선박입출항실적 | API | 발급완료 | 미검증 |
| 인천항만공사_인천항 입출항 정보 | API | 발급완료 | 미검증 (심의승인 대상) |
| 관세청 UNI-PASS 화물통관진행정보 | API | **미신청** | — |
| 운임·출발도착지·예정일·견적만료일 | 업로드 | 양식 `물류` 시트 | 기업 입력 |

**→ 실제 운임·납기는 외부 API 로 대체 불가.** 업로드 `물류`·`재고·생산` 시트가 유일한 출처다.

#### 안정성

| 소스 | 종류 | 상태 | verified |
|---|---|---|---|
| 한국무역보험공사_국가신용등급 (1~7등급) | 파일 | 다운로드완료 | **미검증** (MANIFEST) |
| 한국무역보험공사_국가목록 | API | 발급완료 | 미검증 |
| OECD Country Risk Classification | 파일 | 다운로드완료 | **본문 'Valid as of' 공란 — 원본 확인 필요** |
| KOTRA_국가 목록 (대한 수입규제 현황) | API | 발급완료 | 미검증 |
| OpenDART 전자공시 (국내 상장사) | API | 발급완료 | 미검증 |
| Finnhub (해외 시세·재무) | API | 발급완료 | 미검증 |
| NewsData.io / NewsAPI.org / GDELT | API | 발급완료 / 키불필요 | 미검증 |
| 거래처 법인명·주소·등록번호 | 업로드 | 양식 `거래처` 시트 | 기업 입력 |

**→ 부분 가능.** OECD 의 `-`/미분류를 0 이나 최저위험으로 환산하지 않는다.

### 5.3 `자료 부족` / `평가 보류` 표시 조건

두 표현을 구분한다 (design.md 용어, §4 용어사전).

| 표시 | 뜻 | `MeasuredValue.state` |
|---|---|---|
| **자료 부족** | 입력 또는 외부 자료가 없어 **계산할 수 없다** | `not_entered` 또는 `fetch_failed` |
| **평가 보류** | 판정 규칙·설정 자체가 미확보·미승인이라 **계산을 시도하지 않는다** | `not_evaluated` |

#### 항목별 조건

| 항목 | `평가 보류` 조건 | `자료 부족` 조건 |
|---|---|---|
| **규제** | 별표2의2·별표6 중 하나라도 미확보 **또는** 별표1~4 의 `verified ≠ 원문대조 완료` **또는** `세관장확인대상물품` 미검증 → **현재 무조건 보류** | 위가 해소된 뒤, 제품정보 `HS코드`·`제조국코드`·`전략물자해당` 또는 수출예정거래 `최종사용자명`·`최종용도` 가 `not_entered` |
| **시장성** | 시장성 지표 항목·가중치가 설정에서 미승인 | 목적국코드 미입력 / Comtrade `fetch_failed` / 조회 기간이 분석 기간을 못 덮음 / `관세청_월별 실적` 필요 시 미확보 |
| **가격** | 관세율 적용 규칙이 원문대조 전 **또는** 특혜관세 적용 조건 규칙 미검토 | HS코드·제조국코드·목적국코드 중 하나라도 미입력 / `단가`·`통화`·`금액배율` 미입력 / `원가·비용` 시트 해당 제품 행 없음 / 환율 소스 `fetch_failed` / 관세율표에 해당 세번 없음 |
| **물류** | 납기 판정 기준(검사기간 포함 여부 등) 미승인 | `물류` 시트 `운임`·`통화`·`금액배율` 미입력 / `출발예정일`·`도착예정일` 미입력 / 견적만료일이 평가기준일보다 과거 / `재고·생산` 시트 `공급가능수량` 미입력 |
| **안정성** | 국가위험 등급 → 안정성 환산 규칙 미승인 **또는** OECD 자료 `Valid as of` 미확인 | 목적국이 국가신용등급 파일에 없음 / OECD 분류가 `-`(미분류) → `not_applicable` 로 두고 그 사실을 표시 / `거래처` 시트 `법인명`·`국가코드`·`주소`·`등록번호` 미입력으로 CSL 대조 불가 / CSL `fetch_failed` |

공통 규칙:

- 어느 항목이든 그 값을 쓰는 외부 자료의 `registry_verified ≠ 검증완료` 면 **확정 판정 근거로 쓰지 않는다.** 표시는 하되 `평가 보류` 로 둔다.
- `max_age_exceeded = true` 면 `stale_cache_used` 로 표시하고 갱신 경로를 함께 보인다.
- 5개 항목 중 하나라도 보류·부족이면 메인 화면 상단에 누락 상태를 표시한다 (§8 — 종합 화면에 누락 상태 표시).

---

## 6. 설정으로 빼는 자리 (값 비움)

명세서 §6·§11 — 가중치·임계값·기업 정책은 중앙 설정으로 관리하고 근거·검토 상태를 기록한다. **아래 값은 비어 있다. 채우는 것은 승인 사항이다.**

```
scoring_config
├─ config_id            : (미정)
├─ version              : (미정)
├─ review_status        : 미검토
├─ approved_by          : (미정)
├─ approved_at          : (미정)
├─ basis_document       : (미정)   근거 문서·산출 방법
├─ area_weights
│   ├─ market           : (비움)
│   ├─ price            : (비움)
│   ├─ logistics        : (비움)
│   └─ stability        : (비움)
├─ metric_definitions[] : (비움)   metric_id, label_key, formula_ref, unit, direction
├─ thresholds[]         : (비움)   metric_id, band_label_key, lower, upper
├─ composite_method     : (미정)   가중합 여부 자체가 미결정
├─ rounding_policy      : (미정)   통화별 정밀도·반올림
└─ company_overrides[]  : (비움)   기업 정책 예외
```

```
freshness_config
├─ max_age_days         : (비움)   source_id 별
└─ cache_ttl            : (비움)
```

```
rule_set
├─ rule_set_id          : (미정)
├─ version              : (미정)
├─ review_status        : 미검토
├─ source_files[]       : 별표1~4 (원문대조 필요), 별표2의2·별표6 (미확보)
├─ usable_in_production : false
└─ conditions[]         : (비움)   ★ 별표2의2 원문 확보 후 원문대조를 거쳐 채운다
```

`usable_in_production = false` 인 동안 G1 게이트가 `overall.decision = withheld` 를 강제한다. 설정을 UI·서버·보고서에 중복 하드코딩하지 않는다 (§11).

---

## 7. 미확정·차단 항목

| 항목 | 상태 | 해소 조건 |
|---|---|---|
| 수출규제 판정 규칙 내용 | **차단** | 별표2의2·별표6 다운로드 → 별표1~4 원문대조 → 검토 승인 |
| 점수 항목·가중치·임계값 | **미정** | 명세서 §2 「점수 항목·가중치·임계값의 검토 및 승인 절차」 확정 |
| 판정 라벨 문자열 | 제안 | §4 용어사전 확정 |
| 저장 방식 (DB·파일·스키마 언어) | 미정 | 기술 스택 결정 (§2) |
| 상세 탭 최종 구성 | 미정 | §2 |
| 점수 → 화면 표현 방식 | 미정 | 앱 디자인 시안 |

이 문서는 스키마 **구조**만 정의한다. 저장 형식(JSON Schema·DB DDL·타입 정의)은 기술 스택 확정 후 이 구조를 옮겨 적는다.

## 8. 변경 관리

| 날짜 | 내용 | 상태 |
|---|---|---|
| 2026-09-22 | 3층 판정 구조·평가 실행 저장 구조·값 상태 타입·5개 항목 매핑 초안 | 설계 초안 |

규칙·계산 의미가 바뀌면 `rule_set.version` 과 `engine.calc_engine_version` 을 올린다 (명세서 §14).
