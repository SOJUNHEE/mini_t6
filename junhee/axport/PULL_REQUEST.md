# PR — AXPORT 시연용 마감: §13-6 실제 분석 · §13-7 홈 · §13-8 시연 환경 · §12 검증

> 이 폴더는 아직 Git 저장소가 아니다 (`git init` 미실행). 이 문서는 CONTRIBUTING §9 양식으로 작성한
> PR 본문이며, 저장소 초기화·브랜치(`feat/13-6-analysis-home-demo`) 생성 후 그대로 붙여 넣는다.
> 4단계 코드 검토에서 **차단 1건, 병합 전 수정 4건**이 나왔다. 아래에 숨기지 않고 적었다.

## 목적

- 검증된 데이터 범위(registry `verified=검증완료` API)에서 **실제 지표**를 붙이고, 탭별 상세 5구성·보고서·AI 설명 정책을 완성한다 (명세서 §13-6).
- 홈 화면 `/` 를 별도 시안으로 만든다 — 네이비 히어로·3D·스크롤 이후 흰 배경·우측 상단 앱 진입·실제 준비 상태와 연결된 로딩 (명세서 §13-7, §1-2~5).
- 시연 환경으로 마감한다. 로그인·소유권·권한은 **구현하지 않고** 화면·README 에 명시한다 (명세서 §13-8, §10).
- 명세서 §12 완료 검증 12항목을 실제로 실행해 기록한다.

변경 후 동작: `/` → 앱 진입 → 업로드 → 검증 → 매핑 → 평가 대상 → **평가 실행(run) 저장** → 8개 탭 상세 → 보고서(JSON/CSV) → AI 전송 미리보기.
시장성·수출실적 탭만 실제 값이 나오고 나머지 4개 탭은 **소스 미검증으로 평가 보류**를 표시한다. 규제는 규칙 미확보로 항상 보류다.

## 주요 변경

### 서버 (`src/axport/`)
| 계층 | 파일 | 내용 |
|---|---|---|
| 외부 데이터 | `external_data/providers/customs_trade.py` | 관세청 수출입실적(검증완료) 연결. XML 전용, 조회기간 1년 검사, 총계 행 제외, **10자리 HS 0건 → 6자리 조회를 명시**(`hs_broadened`). 연결실패/자료없음/권한없음/오래된 캐시 4종 구분 |
| | `external_data/cache.py` | 캐시 경과시간·`max_age` 정책 미정 시 초과 판정 안 함 |
| | `external_data/sources.py` | **소스 게이트** — `검증완료` API 만 지표 계산. MANIFEST 파일은 인벤토리로만 (현재 계산가능 0건) |
| 지표 | `metrics/money.py`, `market.py`, `trade_history.py` | Decimal 계산, 문자열 직렬화, `display` 블록 분리(반올림 정책 미정 → 원값), 모든 지표에 통화·단위·기간·계산식·data_class |
| 판정 | `rules_engine/detail.py` | 탭별 **상세 5구성** 서버 조립. `chart.series === table.rows` |
| | `rules_engine/run_store.py`, `evaluate.py` | 평가 실행 저장(`sealed`, `input_fingerprint`, `run_seq`, `supersedes`). 필터 변경 → 새 run |
| | `rules_engine/values.py` | `MeasuredValue` 에 `display`·`data_class`·`formula` 추가 |
| 보고서 | `reports/builder.py`, `csv_safe.py` | 저장된 run 을 그대로 옮김(재계산 없음). CSV 수식 주입 방어(`= + - @` 접두, 숫자는 보존) |
| AI | `ai_explain/service.py` | 허용목록·제외목록(`ALWAYS_DENY` 포함), 요청·비용 상한 미정 시 호출 안 함, **응답 숫자 검사**(입력에 없는 숫자 거부), dry-run |
| API | `api/evaluations.py`, `api/uploads.py`, `api/pages.py` | `/evaluations/*`, `/reports/*`, `/ai/*`, `/uploads/{id}/runs`, 홈 `/` |
| 설정 | `config/settings.toml` | `ai.send_fields_allowlist/denylist`, `external_data.max_age_days.customs_nitemtrade`(미정) |

### 화면 (`web/`)
- `home/index.html`, `css/home.css`, `js/home.js`, `js/home-3d.js` — **신규**. 앱 파일 미수정. 3D 는 CSS transform (라이브러리 없음, 1,496 B). 동적 import 실패 → 정적 SVG.
- `js/analysis-window.js` — 상세 5구성 렌더, 인라인 SVG 차트 + 표 토글, 출처 상태·데이터 구분 배지, 분석 기간 필터(새 run, 화면 먼저 비움), 보고서·AI 버튼.
- `js/desktop.js`, `js/app.js`, `js/window-manager.js` — 시연 환경 배너, `STORAGE_SCOPE` 주석(시연용 UI 저장 ≠ 기업 계정 저장).
- `js/screens.js` — `dataClassBadge`, `fetchBadge`.

### 문서
- `README.md` — 엔드포인트 표, **「운영 전 필요 작업」**(명세서 §10 미구현 전부), 실행/미실행 항목 갱신.
- `web/README.md` — 홈·시연 환경 절.

### 의존성
변경 없음. 3D 라이브러리를 추가하지 않았다 (CONTRIBUTING §5 해당 없음).

## 검증

### 실행 환경
Windows 11 / Python 3.14.7 / `.venv` / 2026-09-22. 외부 API 는 실제 키(api-vault)·네트워크로 1회 호출.

### 명세서 §12 완료 검증 — 12항목

판정은 통과·실패·미검증 셋 중 하나. **출력을 붙이지 못한 항목은 미검증.**

| # | 항목 | 실행한 명령 또는 조작 | 실제 출력 | 판정 |
|---|---|---|---|---|
| 1 | 홈에서 앱 진입, 로딩 성공·실패·재시도 | `curl /`, `/health`, `/app`; 서버 종료 후 `curl -m 3 /health` | `/ → 200`, `/health → 200 status=ok`, `/app → 200`; 종료 후 `curl exit=7`. `home.js` 에 `fetch("/health")`, `setTimeout` 없음, `loader-retry` 존재(정적 검사 통과) | **미검증** — 로딩 오버레이·재시도 버튼은 브라우저 JS. 자동화 브라우저 없음. 서버측 성공/실패 경로만 확인 |
| 2 | 창 이동·크기조절·책갈피 전환 후 평가 맥락 유지 | 정적 검사 `test_context_preserved_across_tabs` 등 | `record.context` 보유, `bookmark-tabs.js` 에 `company_id`/`subject_id` 없음 — PASSED | **미검증** — 드래그·리사이즈·탭 클릭은 브라우저 동작. 정적 검사만 통과 |
| 3 | 새로고침·작은 화면·창 배치 복원 시 조작부 접근 | 정적 검사 `test_controls_kept_on_screen`, `@media (max-width: 720px)` 존재 | `clamp`, `KEEP_VISIBLE_X`, `resize` 리스너, `reflowAll` — PASSED | **미검증** — 실제 브라우저 리플로우 미확인 |
| 4 | 정상·오류·누락·중복 엑셀 검증 결과 구분 | 4개 파일 업로드→`/validate` | 양식: error 0 / 샘플: error 4 `[broken_reference, duplicate_key, duplicate_row, invalid_date]` / 누락+중복 사본: error 3 `[duplicate_key, duplicate_row, required_missing]` / 오류제거 사본: error 0 warning 12 | **통과** |
| 5 | 0과 미입력, 해당 없음과 미평가 구분 | 샘플 검증 결과 + 분석 결과 | `value_is_real_zero: 수출실적5행.수량…` / `area_required_missing: 수출예정거래5행.단가…` / `value_not_applicable: 증빙목록4행.만료일` / `composite.state=not_evaluated`, `'value' 키 있음=False` / `kr_export_amount=319,490,719 USD state=actual` | **통과** |
| 6 | 외부 API 장애·자료 없음·오래된 자료 사용 명시 | `pytest -v -k "no_data or permission or connection or stale or max_age"` | `test_no_data_is_reported_not_zero PASSED`, `test_permission_error_is_fetch_failed PASSED`(코드 30→`no_permission`), `test_connection_failure_is_fetch_failed PASSED`, `test_stale_cache_is_flagged PASSED`, `test_max_age_policy_undecided_is_stated PASSED` — 5 passed | **통과** |
| 7 | 필수 자료 부족 시 낙관적 확정 판정 없음 | 실제 분석 run 의 `result.overall` | `decision=withheld (평가 보류) reasons=['rule_source_missing']`, `gate_inputs=['mandatory_review','evidence_status']`, `business_fitness_is_gate_input=False`, 'proceed' 값 존재=False | **통과** |
| 8 | 근거·계산식·출처·자료 및 규칙 버전 확인 | `tab_details.market.reasoning`, `run.engine` | 계산식 `kr_export_amount=sum(expDlr) over rows`…; 출처 `관세청_품목별 국가별 수출입실적(GW) verified=검증완료 fetch=ok endpoint=https://apis.data.go.kr/…`; 조회조건 `{strtYymm:202601, endYymm:202603, cntyCd:US, hsSgn:854232}` HS단위 `6자리(요청보다 넓음)`; 버전 `template 0.1 / rule_set None / calc_engine None / scoring None`; 인벤토리 API 2 / 파일 13 (계산가능 0) | **통과** |
| 9 | 같은 평가 실행의 화면·보고서 수치 일치 | `GET /evaluations/{run}` vs `POST /reports` vs CSV 다운로드 대조 | 화면 run_id = 보고서 run_id (`run_071bc1471bc04a20b6841e22`) 같음=True; 지표 11개 JSON 불일치 0 / CSV 불일치 0; 예 `upload_export_amount 384750 / 384750 / 384750`; CSV `=` 시작 셀 0개. 재계산 없음은 `test_report_matches_screen_and_does_not_recompute` (외부 호출 시 실패하도록 패치) PASSED | **통과** |
| 10 | 데모 자료·실제 자료·가정값 식별 | `run.environment`, 지표 `data_class` | `{'demo_mode': True, 'label': '시연 데이터 환경', 'storage_scope': 'instance/ (시연용 세션 보관, 기업 계정 저장 아님)'}`; data_class 집합 `[('real','실제 자료'), ('user_input','사용자 입력')]`; 보고서 CSV `# 환경` 행 포함 True | **통과** |
| 11 | 실행한 테스트와 미검증 항목 구분 기록 | `pytest -o addopts="-q -m 'not external' -rs"` | `104 passed, 1 deselected` (external 1건 분리). README 「실행하지 않음 · 미검증」·이 표의 미검증 3건 | **통과** |
| 12 | 사용자·기업 간 데이터·보고서 접근 차단 | — | 시연용. 로그인·소유권·권한 미구현 (README 「운영 전 필요 작업」) | **해당 없음** |

미검증 3건(1·2·3)은 모두 브라우저 상호작용이다. 자동화 브라우저를 도입하지 않았고, 이 PR 에서 코드를 고치지 않았다.

### 실행한 명령
```
.venv\Scripts\python.exe -m pytest                    # 104 passed, 1 deselected
.venv\Scripts\python.exe -m pytest -m external        # 실행하지 않음 (기본 제외; 별도 실행 필요)
uvicorn axport.main:app --app-dir src --port 8040     # / /health /app → 200
```
홈 자산: HTML 9,513 + tokens.css 8,553 + home.css 11,021 + home.js 6,500 + home-3d.js 1,496 = **37,083 B (36.2 KB)**, localhost 순차 합산 **87.5 ms** (5회 평균, `/` 20.9 ms).

### 실행하지 않음
- macOS/Linux, `--reload`, 브라우저 렌더링 전반, `pytest -m external`(이번 실행에서는 in-process 스크립트가 실제 API 를 호출했고 마커 테스트 자체는 돌리지 않았다).

## 호환성·운영 영향

- **환경변수·설정**: `ai.send_fields_allowlist/denylist`(제안값 채움, 승인 대상), `external_data.max_age_days.customs_nitemtrade`(미정). 업로드 제한값은 여전히 미정 → 기본 상태에서 업로드 503.
- **의존성**: 변경 없음.
- **API**: `POST /uploads/{id}/analyze` 본문이 `{subject_id}` → `{subject_id, filters}` 로 바뀜(하위 호환: filters 생략 가능). 응답이 3층 결과 → **평가 실행(run) 전체**로 확장. 신규 `/evaluations/*`, `/reports/*`, `/ai/*`, `/uploads/{id}/runs`, `/`.
- **데이터 구조**: `instance/uploads/<id>/runs/*.json`, `runs_index.json`, `instance/reports/<id>/`, `instance/cache/<source>/`. 마이그레이션 없음(신규).
- **규칙·계산 버전**: `rule_set_version`·`calc_engine_version` 은 미정 그대로. 이 PR 은 판정 규칙을 만들지 않았다.
- **되돌릴 때**: `web/home/`, `css/home.css`, `js/home*.js`, `api/evaluations.py`, `reports/builder.py`, `ai_explain/service.py`, `rules_engine/{detail,evaluate,run_store}.py`, `metrics/*`, `external_data/{cache,sources,providers/*}` 제거 + `api/uploads.py analyze`·`pages.py` 원복. `instance/` 산출물은 삭제해도 된다.
- **운영 반영 차단**: 아래 4단계 검토의 차단 항목 해소 전 실제 기업 자료 환경에 올리지 않는다.

## 4단계 코드 검토 결과 (CONTRIBUTING §11 기준 — 읽고 판정, 수정하지 않음)

### 차단
| # | 위치 | 문제 |
|---|---|---|
| B-1 | `api/uploads.py`, `api/evaluations.py` 전체 | **무인증·무소유권.** `GET /uploads`, `/evaluations/{run}`, `/reports/{id}/download.csv` 를 누구나 호출한다. 시연 전제로 의도된 상태지만 **실제 기업 자료 환경 반영은 차단**이다 (명세서 §10, CONTRIBUTING §11 「서버에서 기업·사용자 소유권을 확인하는가」= 아니오). README 「운영 전 필요 작업」에 명시 |

### 병합 전 수정
| # | 위치 | 문제 | 근거 |
|---|---|---|---|
| M-1 | `upload_validation/validate.py:216` | 금액배율 허용값 `(1, 1000, 1000000)` 하드코딩. `config/settings.toml currency.allowed_amount_multipliers` 와 **중복** | 명세서 §11 설정 중복 하드코딩 금지 |
| M-2 | `external_data/registry.py:rule_readiness()` | 별표 파일 목록·`usable_in_production=False` 를 코드에 박아 둠. registry `status=미다운로드`·MANIFEST `verified` 에서 파생해야 함. 별표를 내려받아도 코드가 바뀌기 전엔 보류가 풀리지 않음 | 명세서 §7 자료 상태 추적 |
| M-3 | `config/settings.toml api_limits.max_retries/retry_backoff_seconds`, `customs_trade.TPS_LIMIT` | 설정·상수는 있으나 **재시도·호출량 제한이 구현되지 않음**. 설정이 동작을 약속하는데 읽히지 않는다 | CONTRIBUTING §11 「외부 API 실패·시간 초과·호출 제한을 처리하는가」— 시간 초과·실패 O, 호출 제한 X |
| M-4 | 검증 항목 1·2·3 | 브라우저 상호작용 미검증. 병합 전 수동 QA 기록 또는 브라우저 스모크 테스트 필요 | CONTRIBUTING §12 |

### 개선 권장
| # | 위치 | 내용 |
|---|---|---|
| R-1 | `rules_engine/detail.py` · `web/js/bookmark-tabs.js` · `web/js/analysis-window.js` | 탭 id/라벨 3곳 정의. 서버 `tab_order` 를 화면이 받아 쓰도록 단일화 |
| R-2 | `rules_engine/result.py AREA_REQUIRED_INPUTS` | 시트·컬럼명이 `upload_validation/schema.py` 와 별도 문자열로 중복 |
| R-3 | `tests/conftest.py TEST/UPLOAD_ENV` · `tests/test_pipeline.py TEST_ENV` · `README` | 시험용 제한값 3곳 중복 |
| R-4 | `external_data/providers/customs_trade.py:256` | serviceKey 를 URL 문자열에 넣음. 예외 메시지에 URL 이 실리는 라이브러리 경로가 생기면 유출 위험. 호출 직후 문자열 폐기·리댁션 래퍼 권장 |
| R-5 | `tests/test_home.py::test_app_untouched_by_home` | `A or B` 형태로 항상 참이 될 수 있는 약한 단언 |
| R-6 | `rules_engine/subject.py TRADE_TERM_ESSENTIALS` | 시장 탐색/거래 평가 구분 기준(필수 거래 조건 7개)이 코드 상수. 승인·용어사전 관리 대상 |
| R-7 | `web/js/desktop.js` | `this.health` 를 기동 시 1회만 읽어 기능 플래그가 바뀌어도 반영되지 않음 |
| R-8 | `rules_engine/evaluate.py` | `from axport.rules_engine import values as V` 미사용 import |
| R-9 | `web/js/analysis-window.js renderAnalysisWindow` | `a && b || !c` 우선순위 의존 조건식 — 괄호로 의도 명시 |

### 검토 통과 항목 (근거)
- 0/미입력/미평가/해당없음 구분 — `MeasuredValue` `value` 키 존재 여부로 타입 수준 분리, 검증 항목 5 통과
- 사업성 점수 상쇄 없음 — `apply_gates` 입력에 `business_fitness` 없음, `business_fitness_is_gate_input=False`
- 단위·통화·기간·HS 버전 — 모든 `actual` 지표에 currency/unit·period·formula (`test_every_actual_metric_has_unit_or_currency_and_period`)
- 결과·보고서 같은 run — 항목 9 통과, 재계산 시 실패하는 테스트 통과
- 과거 결과 불변 — `test_filter_change_creates_new_run_and_keeps_old`
- 키·민감정보 — 코드·응답·저장 파일에 키 없음 (`test_health_never_exposes_key_values`, 캐시 `query` 에서 키 제외), 개인 절대경로 없음(스캔 A: CSS 클래스 `desktop` 오탐만)
- api-vault 키 접근 — `api_keys.require_key`/`available`/`missing` 경유만 (스캔 B)
- 화면 JS 내 판정·계산 — 차트 좌표 계산(Number/Math)뿐, 점수·임계값·결측 보정 없음 (`test_no_judgement_or_scoring_logic_in_frontend`)
- 임의 점수 기준·가중치 — 없음 (스캔 C). `composite` 항상 `not_evaluated`
- 원본 훼손 — api-vault registry/MANIFEST·samples 이번 작업 중 미변경 (타임스탬프 20:27/19:55/20:42)

## 관련 작업

- 선행: CLAUDE.md, api-vault 검증(nitemtrade 검증완료 2026-09-22), 양식 v0.1, rules/README.md 판정 구조, 골격, §13-4 파이프라인, §13-5 /app
- 후속(차단 해제): 별표2의2·별표6 다운로드 → 별표1~4 원문대조 → `rule_set_usable_in_production`; 업로드 제한값·가중치·반올림 정책·AI 공급자·`max_age` 승인; 로그인·소유권·권한·보관·감사 (운영 전 필요 작업); 브라우저 스모크 테스트

🤖 Generated with [Claude Code](https://claude.com/claude-code)
