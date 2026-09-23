# AXPORT

기업의 엑셀 데이터와 HS 코드로 수출적합도를 분석하는 서비스.

- 상태: **시연용 마감 단계.** 홈(`/`)·앱(`/app`)·업로드→검증→매핑→평가대상→분석→보고서 흐름이 동작한다.
  지표 계산은 **검증완료 API 1건(관세청 수출입실적) 범위**에서만 실제 값을 낸다.
- **시연 데이터 환경이다. 실제 기업 자료를 받지 않는다.** 로그인·기업별 소유권·역할별 접근 통제는
  구현하지 않았다 → 아래 「운영 전 필요 작업」.
- 기준 문서: [초기 개발 명세](../AXPORT_초기개발명세.md) · [디자인 원칙](../design.md) · [협업 규칙](../CONTRIBUTING.md) · [판정 구조 설계](../rules/README.md)

## 스택

| 항목 | 값 | 근거 |
|---|---|---|
| Python | **3.14.7** (`.python-version`) | 사용자 확정 |
| 백엔드 | **FastAPI** + uvicorn | 사용자 확정 |
| 의존성 관리 | **pip + requirements** (`requirements.in` 소스 명세 / `requirements.txt` 잠금) | 사용자 확정. CONTRIBUTING §1 — 한 가지 방식만 |
| 프런트엔드 | **순수 CSS/JS** (ES 모듈), FastAPI 가 제공. Node·빌드 도구 없음 | 사용자 확정 |
| 설정 | `config/settings.toml` (stdlib `tomllib`) | 명세서 §11 |

패키징을 위한 `pyproject.toml` 은 두지 않는다. 의존성 출처가 둘로 갈리는 것을 막기 위해
`uvicorn --app-dir src` 와 `pytest.ini` 의 `pythonpath=src` 로 import 경로를 잡는다.

---

## 설치

저장소 루트(`axport/`)에서 실행한다. 누구나 같은 순서로 실행한다 (CONTRIBUTING §12).

### Windows PowerShell

```powershell
python --version                      # .python-version 과 같은지 확인
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env           # 선택. 기본값으로도 동작한다
```

### macOS / Linux

```bash
python3 --version
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env                  # 선택
```

가상환경 활성화는 선택 사항이다. 위처럼 `.venv` 의 Python 을 직접 지정하면
시스템 Python 과 혼동을 줄일 수 있다 (CONTRIBUTING §4).

## 개발 서버 실행

```powershell
# Windows
.\.venv\Scripts\python.exe -m uvicorn axport.main:app --app-dir src --reload
```

```bash
# macOS / Linux
.venv/bin/python -m uvicorn axport.main:app --app-dir src --reload
```

기동되면 다음이 뜬다.

```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

기동 직전에 **미정 설정 건수**를 경고 로그로 남긴다. 명세서 §2 승인 대기 항목이다.
이 로그가 사라지면 설정이 임의로 채워졌다는 뜻이므로 확인한다.

## 검증

```powershell
# 1) 테스트 — 비밀키 없이 재현 가능하다
.\.venv\Scripts\python.exe -m pytest

# 2) 헬스체크 (서버를 띄운 다른 터미널에서)
curl http://127.0.0.1:8000/health

# 3) 미정 설정 목록
curl http://127.0.0.1:8000/health/config/undecided

# 4) API 문서
#    브라우저에서 http://127.0.0.1:8000/docs
```

### api-vault 키 점검 (별도 저장소 밖 폴더)

```powershell
cd ..\api-vault
python scripts\check_keys.py          # 키 값은 출력되지 않는다
python scripts\verify_apis.py --list  # 검증 대상 API 목록
```

---

## 엔드포인트

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/` | 홈 — 네이비 히어로·CSS 3D·스크롤 이후 흰 배경·우측 상단 앱 진입 (라이브러리 없음) |
| GET | `/app` | 대시보드 앱 화면 (홈과 별개 시안, 상태 분리) |
| GET | `/static/...` | 화면 자산 (`web/`) |
| GET | `/health` | 설정 로드·저장 경로·api-vault 참조·기능 활성화 상태 |
| GET | `/health/config/undecided` | 미정 설정 경로 목록 |
| GET | `/uploads` | 업로드 목록 (바탕화면 '최근 분석') |
| POST | `/uploads` | ① 업로드 — 제한 검증 후 원본 보존 |
| POST | `/uploads/{id}/validate` | ② 검증 — 오류/경고/정보 + 행 번호 |
| POST | `/uploads/{id}/mapping` | ③ 매핑 후보 생성 (확정하지 않음) |
| POST | `/uploads/{id}/mapping/confirm` | ③ 매핑 사용자 확인 |
| GET | `/uploads/{id}/subjects` | ④ 평가 대상 후보 (평가 단위) |
| POST | `/uploads/{id}/analyze` | ⑤ 분석 — 평가 실행(run) 생성·저장. `filters.analysis_period` 를 바꾸면 새 run |
| GET | `/uploads/{id}/runs` | 이 업로드의 평가 실행 목록 |
| GET | `/evaluations/{run_id}` | 평가 실행 조회 — 화면·보고서 공용 |
| GET | `/evaluations/{run_id}/tabs/{tab_id}` | 탭 상세 5구성 (평가대상·결과·차트/표·근거·미확인) |
| POST | `/reports` | 보고서 생성 — 저장된 run 을 그대로 옮김, 재계산 없음 |
| GET | `/reports/{id}` · `/reports/{id}/download.csv` | 보고서 조회 · CSV (수식 주입 방어) |
| POST | `/ai/explain?dry_run=true` | AI 설명 — 전송 대상 미리보기. 설정 미정이면 호출하지 않음 |
| GET | `/ai/policy` | AI 전송 허용·제외 목록, 요청·비용 상한 |
| GET | `/docs` | OpenAPI 문서 (FastAPI 자동 생성) |

### 업로드 기능을 켜려면

`config/settings.toml` 의 업로드 제한값은 **미정(`""`)** 이다 (명세서 §2 승인 대기).
미정인 동안 업로드는 `503 limits_undecided` 로 거부된다. 승인 전 시험용으로는
환경변수로 주입한다 — **`settings.toml` 에 넣지 않는다.**

```powershell
$env:AXPORT_FEATURES__UPLOAD="true"
$env:AXPORT_UPLOAD__ENABLED="true"
$env:AXPORT_UPLOAD__MAX_FILE_BYTES="10485760"
$env:AXPORT_UPLOAD__MAX_DECOMPRESSED_BYTES="52428800"
$env:AXPORT_UPLOAD__MAX_ROWS_PER_SHEET="10000"
$env:AXPORT_UPLOAD__MAX_SHEETS="20"
$env:AXPORT_UPLOAD__MAX_CELLS="200000"
$env:AXPORT_UPLOAD__PROCESSING_TIMEOUT_SECONDS="30"
```

`/health` 는 **키 값을 절대 반환하지 않는다.** 설정된 키의 **건수**만 보고한다 (명세서 §10).
이를 `tests/test_health.py::test_health_never_exposes_key_values` 에서 검증한다.

## 폴더 구조

```
axport/
├── config/
│   └── settings.toml         중앙 설정 — 단일 출처 (명세서 §11)
├── src/axport/
│   ├── main.py               ASGI 진입점
│   ├── config/               설정 로더
│   ├── api/                  API 계층 — HTTP 입출력만
│   ├── upload_validation/    업로드 검증 — limits/storage/reader/
│   │                         validate/mapping/pipeline
│   ├── metrics/              지표 계산          (미구현)
│   ├── rules_engine/         판정 규칙 — values/subject/result
│   ├── external_data/        외부 데이터 연결 — registry (대장 조회)
│   ├── reports/              보고서             (미구현)
│   └── ai_explain/           AI 설명            (미구현)
├── web/                      UI·창 관리 — /app 화면 (web/README.md)
├── data/
│   ├── reference/raw/        공식 외부 원본, 버전별 보관
│   ├── reference/processed/   추출·정규화 결과
│   └── samples/              가상 기업 데이터·업로드 양식
├── rules/                    검토된 판정 규칙
├── instance/                 Git 제외 — 실행 중 생성
│   ├── uploads/              실제 기업 업로드
│   ├── reports/              생성 보고서
│   └── cache/                API 캐시
└── tests/
```

`data/`·`rules/`·`instance/` 구성은 CONTRIBUTING §7 을 그대로 따른다.
`src/axport/` 의 하위 폴더는 명세서 §11 의 계층 분리를 그대로 옮긴 것이다.

### 계층 규칙 (명세서 §11)

- **판정·계산 로직을 `api/` 나 `web/` 에 넣지 않는다.** 계산은 `metrics/`, 판정은 `rules_engine/`.
- 화면과 보고서는 동일한 서버 계산 결과를 사용한다. 같은 `run_id` 를 참조한다.
- 설정값을 UI·서버·보고서에 중복 하드코딩하지 않는다. `config/settings.toml` 이 단일 출처다.

## api-vault 참조

`api-vault` 는 이 저장소 **바깥**에 있고, 이 프로젝트는 **참조만** 한다 (명세서 §1-12).

- 기본 경로: `../api-vault` (`config/settings.toml` 의 `storage.api_vault_dir`)
- 키 읽기: `api-vault/scripts/api_keys.py` 의 `get_key` / `require_key` **만** 사용
- **`api-vault/API_KEYS_FORM.txt` 와 `credentials/` 는 열지 않는다.**
- 키 값을 코드·로그·응답·커밋에 넣지 않는다.
- 사용 가능한 소스 판단은 `api-vault/registry/api_registry.csv` 의 `status`·`verified` 로 한다.

자세한 규칙은 [../CLAUDE.md](../CLAUDE.md) §3.

## 환경변수

`.env.example` 을 복사해 `.env` 로 쓴다. **API 키는 여기에 넣지 않는다** — api-vault 에서만 관리한다.

형식은 `AXPORT_<섹션>__<키>` 다. 예: `AXPORT_RUNTIME__PORT=8001`.
환경변수를 추가·변경하면 `.env.example`·이 README·설정 검증을 함께 고친다 (CONTRIBUTING §6).

---

## 현재 확인된 것 / 확인하지 않은 것

CONTRIBUTING §9·§12 — 실행하지 않은 것을 실행했다고 쓰지 않는다.

### 실제로 실행해 확인함 (2026-09-22, Windows 11 / Python 3.14.7)

- `pip install -r requirements.txt` 설치 성공 (fastapi 0.141.1, pydantic 2.13.5, openpyxl 3.1.5)
- `pytest` — **104 passed, 1 deselected(external)** — 외부 API 테스트 1건은 `pytest -m external` 로 분리
- `uvicorn` 기동 성공, `GET /health` → **HTTP 200**, `status: "ok"`
- `GET /health/config/undecided` → **HTTP 200**, 미정 설정 **27건**
- `/health` 의 api-vault 참조 성공, 설정된 키 14건·미설정 4건 (건수만)
- `GET /` → **HTTP 200** (홈), `GET /app` → **HTTP 200**, `/static/*` 12개 파일 200
- 홈 자산 합계 37,083 bytes (36.2 KB), 3D 전용 1,496 bytes, localhost 순차 로드 합산 87.5 ms (5회 평균)
- 검증완료 API(관세청 수출입실적) **실제 호출**로 시장성 지표 산출 (HS 854232·US·2026-01~03), 화면·JSON 보고서·CSV 지표 11개 **불일치 0건**
- 필터(분석 기간) 변경 → 새 run_id, 이전 run 불변 확인
- 샘플 엑셀로 ①②③④⑤ 전 단계 HTTP 호출 성공.
  의도적으로 심은 오류 4종(중복 행·날짜 형식·연결 끊김·0/미입력 구분)이
  모두 검출됨 — error 4 / warning 12 / info 10
- 분석 결과 `overall.decision = withheld` (G1 게이트에서 차단),
  `business_fitness_is_gate_input = false`

### 실행하지 않음 · 미검증

- **macOS / Linux 에서 실행하지 않았다.** README 의 해당 명령은 미검증이다.
- **`--reload` 모드로 실행하지 않았다.** 기동 확인은 `--reload` 없이 했다.
- **브라우저에서 화면을 열어 보지 않았다.** 자동화 브라우저를 도입하지 않았으므로
  홈 로딩 오버레이·재시도, 3D 회전·정적 대체 전환, 창 드래그·크기 조절·탭 전환·키보드 조작,
  새로고침·작은 화면·창 배치 복원은 **미검증**이다. 검증한 것은 HTTP 제공 여부와 자산·규칙의 정적 검사뿐이다.
- 지표 계산(`metrics/`)이 비어 있어 탭별 수치·차트가 없다. 표시할 실제 값이 없다.
- 컬럼 매핑 확인 UI 가 없다. 서버 엔드포인트는 동작한다.
- AI 공급자 연결이 없다. 전송 정책·상한·숫자 검사·dry-run 미리보기만 있다 (`ai.provider/model` 미정).
- 외부 API 재시도·호출량 제한(tps)이 구현되지 않았다. `api_limits.max_retries` 설정은 읽히지 않는다.
- 린트·포매터·타입체크를 도입하지 않았다. 필수 CI 명령은 미정이다 (CONTRIBUTING §1).
- CI 를 설정하지 않았다. 문서 작성 완료와 GitHub 설정 완료는 다르다 (CONTRIBUTING §13).
- 이 폴더는 **아직 Git 저장소가 아니다.** `git init` 은 하지 않았다.
- `metrics/`·`reports/`·`ai_explain/` 계층은 **비어 있다.**
- `config/settings.toml` 의 `features.*` 는 전부 `false` 다. 업로드를 켜려면 위
  「업로드 기능을 켜려면」의 환경변수가 필요하다. 제한값이 승인되기 전까지
  기본 상태에서는 업로드가 거부된다.
- `pytest` 실행 시 `starlette` 의 `httpx2` 권장 DeprecationWarning 이 뜬다. 동작에는 영향이 없으나 추후 정리 대상이다.

## 운영 전 필요 작업 — 시연용이라 구현하지 않은 것 (명세서 §10)

숨기지 않고 그대로 적는다 (CONTRIBUTING §9). 아래가 없는 상태로 **실제 기업 자료를 받으면 안 된다.**

| 명세서 §10 항목 | 상태 | 현재 동작 |
|---|---|---|
| 로그인 | **미구현** | 누구나 `/app` 과 모든 API 를 쓴다 |
| 기업별 소유권 | **미구현** | 업로드·평가 실행에 소유자 개념이 없다. `executed_by.user_id = null` |
| 역할별 접근 정책 | **미구현** | 역할이 없다 |
| 서버측 권한 검사 (조회·수정·삭제·다운로드) | **미구현** | `GET /uploads`, `/evaluations/*`, `/reports/*` 가 무인증 |
| 시연 환경 / 실제 환경 분리 | 표시만 | `features.demo_mode=true` 를 화면·run·보고서에 표기. 환경 분리 인프라는 없다 |
| 언어·화면 모드·클라이언트 값을 권한으로 쓰지 않음 | 해당 | 권한 자체가 없다 |
| 키·비밀값을 서버 환경설정에만 보관 | **적용** | api-vault `require_key` 만 사용, 응답·로그·저장에 키 없음 (테스트로 검사) |
| 개발·테스트·운영 키 분리 | 부분 | 키 저장소는 하나(api-vault). 환경별 분리 없음 |
| 운영 비밀키 미설정 시 고정 개발 키로 동작 금지 | **적용** | 키 없으면 `no_permission` 으로 보고. 기본 키 없음 |
| 외부 AI 전송 대상·제외 항목 정의 | **적용(정책)** | `ai.send_fields_allowlist` / `denylist` + 코드 `ALWAYS_DENY`. 공급자 연결은 미구현 |
| 보관·삭제 정책 (원본·정규화·보고서·로그·백업) | **미구현** | `retention.*` 전부 미정. 아무것도 자동 삭제되지 않는다 |
| 감사 이력 (변경·분석·다운로드) | **미구현** | 평가 실행 인덱스(`runs_index.json`)만 있다. 다운로드·조회 이력 없음 |
| 시연 세션 저장과 장기 기업 계정 저장 구분 | **주석·구조로 구분** | 브라우저 localStorage = UI 편의 저장(`STORAGE_SCOPE`), 서버 `instance/` = 시연 세션 보관. 기업 계정 저장소는 존재하지 않는다 |
| 업로드 제한값 (크기·행·셀·처리시간) | **미정** | 승인 전. 환경변수로 시험용 값 주입 시에만 업로드 동작 |
| 점수 항목·가중치·임계값 | **미정** | `composite` 는 항상 `not_evaluated` |
| 수출규제 판정 규칙 | **차단** | 별표2의2·별표6 미확보, 별표1~4 원문대조 필요 → 규제는 항상 `withheld` |

## 다음 단계 (명세서 §13)

1. 평가 범위·데이터 모델·표준 엑셀 양식 확정 — 양식 v0.1 은 `data/samples/` 에 있음
2. **보유 API 의 실제 조회 및 파일 버전·내용 검증** — 현재 26건 중 2건만 `검증완료`
3. 판정 기준표와 근거 저장 구조 작성 — 구조는 `rules/README.md`, 내용은 별표2의2 확보 후
4. ~~업로드 → 검증 → 평가 대상 선택 → 결과 흐름 구현~~ — 완료 (`/uploads/*`)
5. ~~바탕화면·창 관리자·책갈피 탭 구현~~ — 완료 (`/app`, `web/README.md`)
6. 검증된 데이터 범위부터 분석·보고서 연결 — `metrics/` 구현 대기
7. 홈 화면(`/`) 디자인·3D 연출 — 별도 시안
