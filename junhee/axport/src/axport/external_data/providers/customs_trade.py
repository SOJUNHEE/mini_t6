"""관세청 품목별 국가별 수출입실적 (nitemtrade) — 검증완료 2026-09-22.

명세: api-vault/specs/관세청_품목별 국가별 수출입실적(GW).docx
검증: api-vault/scripts/verify_apis.py nitemtrade
응답 원문: api-vault/specs/samples/nitemtrade_response.xml

문서에서 확인한 사실만 반영한다.
    오퍼레이션 getNitemtradeList / **XML 전용** (JSON 파라미터 금지)
    필수 serviceKey(URL Encode), strtYymm, endYymm, cntyCd / 옵션 hsSgn
    조회기간 1년 이내 · 30 tps · 최대 4000 byte
    금액 단위 달러(USD), 중량 단위 kg, 기간 YYYY.MM
    응답 첫 item 이 총계일 수 있다 → year == '총계' 로 판별한다

실측으로 확인한 사실
    10자리 HS 로 조회하면 items 0건이 온다. 6자리로는 데이터가 있다.
    조회 단위를 조용히 바꾸지 않는다. 바꿨으면 그 사실을 반환한다.

연결 실패 / 자료 없음 / 권한 없음 / 오래된 저장 자료 사용을 구분해 반환한다.
장애 시 샘플 자료로 대체하지 않는다.
"""

from __future__ import annotations

import datetime as dt
import ssl
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

SOURCE_ID = "customs_nitemtrade"
API_NAME = "관세청_품목별 국가별 수출입실적(GW)"
PROVIDER = "공공데이터포털 / 관세청"
ENV_VAR = "DATA_GO_KR_API_KEY"
ENDPOINT = "https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList"
DOC_URL = "https://www.data.go.kr"
FORMAT = "xml"
TPS_LIMIT = 30
MAX_QUERY_MONTHS = 12          # 조회기간 1년 이내
AMOUNT_CURRENCY = "USD"        # 문서: 수출금액(달러)
WEIGHT_UNIT = "kg"             # 문서: 수출중량(kg)
TOTAL_ROW_MARKER = "총계"

# fetch_result — 네 가지 실패를 구분한다 (명세서 §7)
OK = "ok"
NO_DATA = "no_data"
NO_PERMISSION = "no_permission"
CONNECTION_FAILED = "connection_failed"
STALE_CACHE_USED = "stale_cache_used"

# 포털·제공기관 에러코드 (활용가이드 §2)
PORTAL_ERRORS = {
    "4": "HTTP_ERROR", "12": "NO_OPENAPI_SERVICE_ERROR",
    "20": "SERVICE_ACCESS_DENIED_ERROR",
    "22": "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR",
    "30": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR",
    "31": "DEADLINE_HAS_EXPIRED_ERROR", "32": "UNREGISTERED_IP_ERROR",
    "99": "UNKNOWN_ERROR",
}
PERMISSION_CODES = {"20", "30", "31", "32", "02", "03"}


@dataclass
class TradeRow:
    period: str          # YYYY.MM 또는 '총계'
    hs_code: str
    country_code: str
    country_name: str
    item_name: str
    export_weight: str   # 문자열로 보존 — 부동소수 오차를 만들지 않는다
    export_amount: str
    import_weight: str
    import_amount: str
    balance: str

    @property
    def is_total(self) -> bool:
        return self.period == TOTAL_ROW_MARKER

    def as_dict(self) -> dict:
        return {
            "period": self.period, "hs_code": self.hs_code,
            "country_code": self.country_code, "country_name": self.country_name,
            "item_name": self.item_name,
            "export_weight": self.export_weight, "export_amount": self.export_amount,
            "import_weight": self.import_weight, "import_amount": self.import_amount,
            "balance": self.balance,
            "is_total": self.is_total,
        }


@dataclass
class FetchResult:
    """표준화된 출력 구조 (명세서 §7)."""

    source_id: str = SOURCE_ID
    api_name: str = API_NAME
    provider: str = PROVIDER
    fetch_result: str = OK
    error_code: str | None = None
    error_message: str | None = None
    rows: list[TradeRow] = field(default_factory=list)
    query: dict = field(default_factory=dict)
    requested_hs: str | None = None
    hs_granularity_used: str | None = None
    hs_broadened: bool = False       # 요청보다 넓은 단위로 조회했는가
    period: dict = field(default_factory=dict)
    currency: str = AMOUNT_CURRENCY
    weight_unit: str = WEIGHT_UNIT
    data_class: str = "real"         # real / sample / user_input / assumption
    cache: dict = field(default_factory=dict)
    fetched_at: str | None = None
    verified: str | None = None

    @property
    def ok(self) -> bool:
        return self.fetch_result in (OK, STALE_CACHE_USED)

    @property
    def detail_rows(self) -> list[TradeRow]:
        return [r for r in self.rows if not r.is_total]

    def as_dict(self) -> dict:
        return {
            "source_id": self.source_id, "api_name": self.api_name,
            "provider": self.provider, "endpoint": ENDPOINT,
            "format": FORMAT, "doc_url": DOC_URL,
            "fetch_result": self.fetch_result,
            "error_code": self.error_code, "error_message": self.error_message,
            "query": self.query,
            "requested_hs": self.requested_hs,
            "hs_granularity_used": self.hs_granularity_used,
            "hs_broadened": self.hs_broadened,
            "period": self.period,
            "currency": self.currency, "weight_unit": self.weight_unit,
            "data_class": self.data_class,
            "cache": self.cache,
            "fetched_at": self.fetched_at,
            "verified": self.verified,
            "row_count": len(self.detail_rows),
            "rows": [r.as_dict() for r in self.rows],
        }


class PeriodError(ValueError):
    pass


def month_range(start: str, end: str) -> dict:
    """YYYYMM 두 개를 검사한다. 조회기간 1년 이내 (문서 명시)."""
    for v in (start, end):
        if not (len(v) == 6 and v.isdigit()):
            raise PeriodError(f"YYYYMM 형식이 아닙니다: {v}")
    if end < start:
        raise PeriodError("종료년월이 시작년월보다 빠릅니다.")
    sy, sm = int(start[:4]), int(start[4:])
    ey, em = int(end[:4]), int(end[4:])
    if not (1 <= sm <= 12 and 1 <= em <= 12):
        raise PeriodError("월이 1~12 범위를 벗어났습니다.")
    months = (ey - sy) * 12 + (em - sm) + 1
    if months > MAX_QUERY_MONTHS:
        raise PeriodError(
            f"조회기간은 1년 이내만 가능합니다 (요청 {months}개월)."
        )
    return {"start": f"{start[:4]}-{start[4:]}",
            "end": f"{end[:4]}-{end[4:]}",
            "months": months, "granularity": "month"}


def _parse(body: bytes) -> tuple[str | None, str | None, list[TradeRow]]:
    text = body.decode("utf-8", errors="replace")
    root = ET.fromstring(text)
    if root.tag.split("}")[-1] == "OpenAPI_ServiceResponse":
        return ((root.findtext(".//returnReasonCode") or "").strip(),
                (root.findtext(".//returnAuthMsg") or "").strip(), [])

    code = (root.findtext(".//resultCode") or "").strip()
    msg = (root.findtext(".//resultMsg") or "").strip()
    rows = []
    for item in root.findall(".//item"):
        def g(tag: str) -> str:
            return (item.findtext(tag) or "").strip()
        rows.append(TradeRow(
            period=g("year"), hs_code=g("hsCd"),
            country_code=g("statCd"), country_name=g("statCdCntnKor1"),
            item_name=g("statKor"),
            export_weight=g("expWgt"), export_amount=g("expDlr"),
            import_weight=g("impWgt"), import_amount=g("impDlr"),
            balance=g("balPayments"),
        ))
    return code, msg, rows


def _http_get(url: str, timeout: int) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"Accept": "application/xml"})
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def fetch(*, service_key: str, country_code: str, start_yymm: str,
          end_yymm: str, hs_code: str | None = None,
          cache=None, timeout: int = 30,
          allow_hs_broadening: bool = True,
          verified: str | None = None) -> FetchResult:
    """한 번 조회한다. 실패를 성공으로 바꾸지 않는다.

    service_key 는 호출부가 api_keys.require_key 로 읽어서 넘긴다.
    이 함수는 키를 로그·반환값에 넣지 않는다.
    """
    try:
        period = month_range(start_yymm, end_yymm)
    except PeriodError as exc:
        return FetchResult(fetch_result=NO_DATA, error_code="period_invalid",
                           error_message=str(exc), verified=verified)

    attempts: list[tuple[str | None, str]] = []
    if hs_code:
        attempts.append((hs_code, f"{len(hs_code)}자리"))
        if allow_hs_broadening and len(hs_code) > 6:
            attempts.append((hs_code[:6], "6자리(요청보다 넓음)"))
    else:
        attempts.append((None, "전체"))

    last: FetchResult | None = None
    for hs, granularity in attempts:
        params = {"strtYymm": start_yymm, "endYymm": end_yymm,
                  "cntyCd": country_code}
        if hs:
            params["hsSgn"] = hs

        cache_info = {}
        if cache is not None:
            entry = cache.get(SOURCE_ID, params)
            cache_info = entry.as_dict()
            if entry.hit and entry.payload:
                rows = [TradeRow(**{k: v for k, v in r.items() if k != "is_total"})
                        for r in entry.payload.get("rows", [])]
                detail = [r for r in rows if not r.is_total]
                if detail:
                    return FetchResult(
                        fetch_result=(STALE_CACHE_USED
                                      if entry.max_age_exceeded else OK),
                        rows=rows, query=params, requested_hs=hs_code,
                        hs_granularity_used=granularity,
                        hs_broadened=bool(hs_code and hs != hs_code),
                        period=period, cache=cache_info,
                        fetched_at=entry.fetched_at, verified=verified,
                    )

        url = f"{ENDPOINT}?serviceKey={service_key}&{urllib.parse.urlencode(params)}"
        try:
            status, body = _http_get(url, timeout)
        except Exception as exc:  # noqa: BLE001 — 원인을 그대로 보고
            return FetchResult(fetch_result=CONNECTION_FAILED,
                               error_code=type(exc).__name__,
                               error_message="외부 API 연결에 실패했습니다.",
                               query=params, period=period,
                               requested_hs=hs_code, verified=verified)

        try:
            code, msg, rows = _parse(body)
        except ET.ParseError as exc:
            return FetchResult(fetch_result=CONNECTION_FAILED,
                               error_code="xml_parse_error",
                               error_message=str(exc), query=params,
                               period=period, requested_hs=hs_code,
                               verified=verified)

        if code in PERMISSION_CODES:
            return FetchResult(fetch_result=NO_PERMISSION, error_code=code,
                               error_message=PORTAL_ERRORS.get(code, msg),
                               query=params, period=period,
                               requested_hs=hs_code, verified=verified)
        if code not in ("00", "0"):
            return FetchResult(fetch_result=CONNECTION_FAILED, error_code=code,
                               error_message=PORTAL_ERRORS.get(code, msg),
                               query=params, period=period,
                               requested_hs=hs_code, verified=verified)

        detail = [r for r in rows if not r.is_total]
        result = FetchResult(
            fetch_result=OK if detail else NO_DATA,
            error_code=None if detail else "no_rows",
            error_message=None if detail else
                f"조회 조건에 해당하는 실적이 없습니다 ({granularity}).",
            rows=rows, query=params, requested_hs=hs_code,
            hs_granularity_used=granularity,
            hs_broadened=bool(hs_code and hs != hs_code),
            period=period, cache=cache_info,
            fetched_at=dt.datetime.now(dt.timezone.utc).isoformat(),
            verified=verified,
        )
        if detail:
            if cache is not None:
                cache.put(SOURCE_ID, params,
                          {"rows": [r.as_dict() for r in rows]})
            return result
        last = result

    return last or FetchResult(fetch_result=NO_DATA, error_code="no_rows",
                               verified=verified)
