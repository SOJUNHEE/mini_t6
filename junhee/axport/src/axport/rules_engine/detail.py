"""탭별 상세 화면 공통 구성 (명세서 §8).

① 평가 대상과 기준일
② 영역별 결과·핵심 수치
③ 차트·상세 표
④ 판단 이유·계산식·근거 출처
⑤ 미확인 사항·필요한 추가 자료·후속 조치

**서버에서 조립한다.** 화면과 보고서가 같은 평가 실행의 같은 결과를 쓰기
위해서다 (명세서 §11). 화면은 이 구조를 표시만 한다.

차트는 표와 같은 값을 쓴다. `chart.series` 와 `table.rows` 가 같은 배열이다
(명세서 §9 — 차트를 표 형태로도 확인할 수 있게 한다).
"""

from __future__ import annotations

from axport.external_data.providers import customs_trade as ct
from axport.external_data.sources import DATA_CLASS_LABEL
from axport.metrics import market, trade_history
from axport.rules_engine import values as V

# 탭 id — web/js/bookmark-tabs.js 의 TABS 와 같아야 한다
TAB_OVERALL = "overall"
TAB_TRADE_HISTORY = "trade_history"
TAB_MARKET = "market"
TAB_TARIFF_ORIGIN = "tariff_origin"
TAB_EXPORT_CONTROL = "export_control"
TAB_COUNTERPARTY = "counterparty"
TAB_PROFIT_FX = "profit_fx"
TAB_SUPPLY_LOGISTICS = "supply_logistics"

TAB_LABEL = {
    TAB_OVERALL: "종합판정",
    TAB_TRADE_HISTORY: "수출실적",
    TAB_MARKET: "시장성",
    TAB_TARIFF_ORIGIN: "관세·원산지",
    TAB_EXPORT_CONTROL: "수출규제",
    TAB_COUNTERPARTY: "거래처",
    TAB_PROFIT_FX: "수익성·환율",
    TAB_SUPPLY_LOGISTICS: "공급·물류",
}

TAB_ORDER = (TAB_OVERALL, TAB_TRADE_HISTORY, TAB_MARKET, TAB_TARIFF_ORIGIN,
             TAB_EXPORT_CONTROL, TAB_COUNTERPARTY, TAB_PROFIT_FX,
             TAB_SUPPLY_LOGISTICS)


def _subject_section(subject: dict, filters: dict) -> dict:
    """① 평가 대상과 기준일."""
    return {
        "company_id": subject.get("company_id"),
        "product_id": subject.get("product_id"),
        "model_name": subject.get("model_name"),
        "hs_code": subject.get("hs_code"),
        "hs_version": subject.get("hs_version"),
        "destination_country_code": subject.get("destination_country_code"),
        "destination_country_raw": subject.get("destination_country_raw"),
        "evaluation_base_date": subject.get("evaluation_base_date"),
        "analysis_mode": subject.get("analysis_mode"),
        "analysis_mode_label": subject.get("analysis_mode_label"),
        "analysis_period": filters.get("analysis_period"),
        "filters_applied": filters,
    }


def _metric_entries(metrics: dict, labels: dict) -> list[dict]:
    """② 핵심 수치. 모든 지표에 통화·단위·기간이 붙어 있어야 한다."""
    out = []
    for metric_id, label in labels.items():
        mv: V.MeasuredValue = metrics[metric_id]
        entry = {"metric_id": metric_id, "label": label, **mv.as_dict()}
        if mv.data_class:
            entry["data_class_label"] = DATA_CLASS_LABEL.get(mv.data_class)
        out.append(entry)
    return out


def _empty_detail(tab_id: str, subject: dict, filters: dict, *,
                  reason_code: str, reason_text: str,
                  required_inputs: list[str] | None = None,
                  required_sources: list[dict] | None = None,
                  actions: list[str] | None = None) -> dict:
    """계산할 수 없는 탭. 값을 만들지 않고 이유와 필요한 것을 돌려준다."""
    return {
        "tab_id": tab_id,
        "label": TAB_LABEL[tab_id],
        "subject": _subject_section(subject, filters),
        "results": {
            "state": V.NOT_EVALUATED,
            "reason_code": reason_code,
            "display_label": V.DISPLAY_LABEL[V.NOT_EVALUATED],
            "metrics": [],
        },
        "chart": None,
        "tables": [],
        "reasoning": {
            "text": reason_text,
            "formulas": [],
            "sources": [s for s in (required_sources or [])],
        },
        "open_items": {
            "unconfirmed": [reason_text],
            "required_inputs": required_inputs or [],
            "required_sources": [s.get("api_name") or s.get("path")
                                 for s in (required_sources or [])],
            "next_actions": actions or [],
        },
    }


# ── 시장성 (검증완료 API) ─────────────────────────────────────────────
def market_detail(subject: dict, filters: dict, fetch: ct.FetchResult,
                  metrics: dict, *, gate_note: str) -> dict:
    series = market.monthly_series(fetch) if fetch.ok else []
    breakdown = market.hs_breakdown(fetch) if fetch.ok else []

    source_entry = {
        "source_id": fetch.source_id,
        "api_name": fetch.api_name,
        "provider": fetch.provider,
        "endpoint": ct.ENDPOINT,
        "verified": fetch.verified,
        "fetch_result": fetch.fetch_result,
        "error_code": fetch.error_code,
        "error_message": fetch.error_message,
        "query": fetch.query,
        "period": fetch.period,
        "currency": fetch.currency,
        "weight_unit": fetch.weight_unit,
        "data_class": fetch.data_class,
        "data_class_label": DATA_CLASS_LABEL[fetch.data_class],
        "cache": fetch.cache,
        "fetched_at": fetch.fetched_at,
        "requested_hs": fetch.requested_hs,
        "hs_granularity_used": fetch.hs_granularity_used,
        "hs_broadened": fetch.hs_broadened,
    }

    unconfirmed: list[str] = []
    if fetch.hs_broadened:
        unconfirmed.append(
            f"요청한 HS {fetch.requested_hs} 로는 실적이 없어 "
            f"{fetch.hs_granularity_used} 로 조회했습니다. "
            "제품 단위보다 넓은 범위이므로 제품 실적과 같지 않습니다."
        )
    if fetch.fetch_result == ct.STALE_CACHE_USED:
        unconfirmed.append(
            f"최대 허용 경과시간을 넘긴 저장 자료를 사용했습니다 "
            f"(경과 {fetch.cache.get('age_days')}일)."
        )
    if fetch.cache.get("max_age_policy") == "미정":
        unconfirmed.append(
            "external_data.max_age_days_default 가 미정이라 "
            "자료 경과시간 초과를 판정하지 않았습니다."
        )
    if not fetch.ok:
        unconfirmed.append(
            f"외부 조회 상태: {fetch.fetch_result} / {fetch.error_message or ''}")

    return {
        "tab_id": TAB_MARKET,
        "label": TAB_LABEL[TAB_MARKET],
        "subject": _subject_section(subject, filters),
        "results": {
            "state": V.ACTUAL if fetch.ok else V.NOT_ENTERED,
            "reason_code": None if fetch.ok else fetch.error_code,
            "display_label": None if fetch.ok
                             else V.DISPLAY_LABEL[V.NOT_ENTERED],
            "metrics": _metric_entries(metrics, market.METRIC_LABEL),
        },
        "chart": {
            "chart_id": "market_monthly",
            "type": "line",
            "title": "월별 수출·수입 금액",
            "x_key": "period",
            "y_keys": ["export_amount", "import_amount"],
            "currency": fetch.currency,
            "unit": None,
            "period": fetch.period,
            # 차트와 표가 같은 배열을 쓴다 (명세서 §9)
            "series": series,
            "table_ref": "market_monthly_table",
        },
        "tables": [
            {
                "table_id": "market_monthly_table",
                "title": "월별 수출·수입 (차트와 같은 값)",
                "columns": [
                    {"key": "period", "label": "기간"},
                    {"key": "export_amount", "label": "수출금액",
                     "currency": fetch.currency},
                    {"key": "import_amount", "label": "수입금액",
                     "currency": fetch.currency},
                    {"key": "export_weight", "label": "수출중량",
                     "unit": fetch.weight_unit},
                    {"key": "row_count", "label": "행 수", "unit": "건"},
                    {"key": "incomplete", "label": "결측 포함"},
                ],
                "rows": series,
            },
            {
                "table_id": "market_hs_table",
                "title": "세번별 수출·수입",
                "columns": [
                    {"key": "hs_code", "label": "HS"},
                    {"key": "item_name", "label": "품목명"},
                    {"key": "export_amount", "label": "수출금액",
                     "currency": fetch.currency},
                    {"key": "import_amount", "label": "수입금액",
                     "currency": fetch.currency},
                ],
                "rows": breakdown,
            },
        ],
        "reasoning": {
            "text": "한국 관세청 수출입통계에서 대상국·세번·기간 조건으로 조회한 "
                    "실적을 합산했습니다. 이 값은 한국 전체의 대상국 교역 실적이며 "
                    "특정 기업의 실적이 아닙니다. " + gate_note,
            "formulas": [
                {"metric_id": mid, "formula": metrics[mid].formula}
                for mid in market.METRIC_LABEL
                if metrics[mid].formula
            ],
            "sources": [source_entry],
        },
        "open_items": {
            "unconfirmed": unconfirmed,
            "required_inputs": [],
            "required_sources": [],
            "next_actions": [
                "제품 단위 실적이 필요하면 기업 업로드 실적(수출실적 탭)과 대조",
                "대상국 수입시장 규모는 UN Comtrade 검증 후 추가",
            ],
        },
    }


# ── 수출실적 (업로드 = 사용자 입력) ───────────────────────────────────
def trade_history_detail(subject: dict, filters: dict, computed: dict,
                         *, validation_summary: dict) -> dict:
    table_rows = computed["table"]
    unconfirmed: list[str] = []
    if computed["currency_mixed"]:
        unconfirmed.append("통화가 섞여 있어 금액을 합산하지 않았습니다.")
    if computed["row_count"] == 0:
        unconfirmed.append("이 제품·목적국·기간에 해당하는 업로드 실적이 없습니다.")

    return {
        "tab_id": TAB_TRADE_HISTORY,
        "label": TAB_LABEL[TAB_TRADE_HISTORY],
        "subject": _subject_section(subject, filters),
        "results": {
            "state": V.ACTUAL if computed["row_count"] else V.NOT_ENTERED,
            "reason_code": None if computed["row_count"]
                           else V.MISSING_REQUIRED_INPUT,
            "display_label": None if computed["row_count"]
                             else V.DISPLAY_LABEL[V.NOT_ENTERED],
            "metrics": _metric_entries(computed["metrics"],
                                       trade_history.METRIC_LABEL),
        },
        "chart": {
            "chart_id": "upload_history",
            "type": "bar",
            "title": "업로드 실적 (거래일별)",
            "x_key": "trade_date",
            "y_keys": ["amount"],
            "currency": None,
            "period": filters.get("analysis_period"),
            "series": table_rows,
            "table_ref": "upload_history_table",
        },
        "tables": [{
            "table_id": "upload_history_table",
            "title": "업로드 실적 원본 행 (차트와 같은 값)",
            "columns": [
                {"key": "row", "label": "행"},
                {"key": "trade_date", "label": "거래일"},
                {"key": "quantity", "label": "수량"},
                {"key": "quantity_unit", "label": "수량단위"},
                {"key": "amount", "label": "금액"},
                {"key": "currency", "label": "통화"},
                {"key": "amount_multiplier", "label": "금액배율"},
                {"key": "cancelled", "label": "취소"},
                {"key": "return_quantity", "label": "반품수량"},
                {"key": "data_class", "label": "데이터 구분"},
            ],
            "rows": table_rows,
        }],
        "reasoning": {
            "text": "기업이 업로드한 수출실적 시트에서 이 제품·목적국·기간에 "
                    "해당하는 행만 골라 합산했습니다. 외부 검증 자료가 아니라 "
                    "사용자 입력입니다. 미입력 행이 있으면 합산하지 않고 "
                    "'자료 부족'으로 남깁니다.",
            "formulas": [
                {"metric_id": mid, "formula": computed["metrics"][mid].formula}
                for mid in trade_history.METRIC_LABEL
                if computed["metrics"][mid].formula
            ],
            "sources": [{
                "source_id": "upload",
                "api_name": "기업 업로드 (수출실적 시트)",
                "data_class": trade_history.DATA_CLASS,
                "data_class_label": DATA_CLASS_LABEL[trade_history.DATA_CLASS],
                "verified": "사용자 입력 — 외부 검증 대상 아님",
                "validation_summary": validation_summary,
            }],
        },
        "open_items": {
            "unconfirmed": unconfirmed,
            "required_inputs": sorted({
                inp for mv in computed["metrics"].values()
                for inp in mv.required_inputs
            }),
            "required_sources": [],
            "next_actions": [
                "업로드 실적과 관세청 통계(시장성 탭)의 기간·단위를 대조",
            ],
        },
    }


# ── 수출규제 (규칙 미확보 → 보류) ─────────────────────────────────────
def export_control_detail(subject: dict, filters: dict,
                          mandatory: dict, rule_readiness: list[dict]) -> dict:
    reasons: list[str] = []
    sources: list[dict] = []
    for r in rule_readiness:
        for f in r["source_files"]:
            reasons.append(f)
            sources.append({"path": f, "verified": r["review_status"],
                            "usable_for_metrics": False})

    detail = _empty_detail(
        TAB_EXPORT_CONTROL, subject, filters,
        reason_code=mandatory.get("status_reason_code") or "rule_source_missing",
        reason_text="판정 규칙 원문이 확보·대조되지 않아 평가를 시작하지 "
                    "않았습니다. 미검토 규칙을 운영 판정에 사용하지 않습니다 "
                    "(명세서 §7).",
        required_sources=sources,
        actions=[
            "전략물자수출입고시 별표2의2(상황허가 대상품목) 다운로드",
            "별표6(수출지역 구분) 다운로드",
            "별표1~4 원문 대조 후 검토 승인",
        ],
    )
    detail["results"]["mandatory_review"] = mandatory
    detail["open_items"]["unconfirmed"] = reasons or detail["open_items"]["unconfirmed"]
    return detail


# ── 나머지 탭 ─────────────────────────────────────────────────────────
UNVERIFIED_TABS = {
    TAB_TARIFF_ORIGIN: {
        "reason": "관세율 계산에 필요한 자료가 아직 검증되지 않았습니다.",
        "sources": ["관세청_품목번호별 관세율표 (미검증)",
                    "관세청_국가별 관세율표 (미검증 · 법적효력 없는 참고용)",
                    "WTO Timeseries API (미검증)",
                    "US ITA FTA Tariff Rates (미검증)"],
        "actions": ["관세율표 적용 범위·세율 조건·주석 검증",
                    "특혜관세 적용 조건 규칙 검토 승인"],
    },
    TAB_COUNTERPARTY: {
        "reason": "거래 상대 대조에 필요한 목록이 아직 검증되지 않았습니다.",
        "sources": ["US ITA Consolidated Screening List (미검증)",
                    "한국무역보험공사_국가신용등급 (미검증)"],
        "actions": ["CSL 조회 검증 후 미국 CSL 기준임을 화면에 명시",
                    "거래처 시트 등록번호·주소 확보"],
    },
    TAB_PROFIT_FX: {
        "reason": "환율 주 출처가 선정되지 않았고 원가 항목이 미검증입니다.",
        "sources": ["ECOS 통계 API (미검증)",
                    "관세청_관세환율정보 (미검증)",
                    "Frankfurter ECB 환율 (미검증)"],
        "actions": ["환율 주 출처 선정 (명세서 §7)",
                    "currency.rounding_policy 승인",
                    "수익성 계산식·가중치 승인"],
    },
    TAB_SUPPLY_LOGISTICS: {
        "reason": "선박운항정보는 스케줄만 제공하며 실제 운임·납기가 아닙니다.",
        "sources": ["해양수산부_선박운항정보 (미검증 · 스케줄만)",
                    "관세청 UNI-PASS (미신청)"],
        "actions": ["업로드 물류 시트의 운임·예정일 확보",
                    "납기 판정 기준(검사기간 포함 여부) 승인"],
    },
}


def unverified_detail(tab_id: str, subject: dict, filters: dict,
                      area: dict | None) -> dict:
    spec = UNVERIFIED_TABS[tab_id]
    sources = [{"api_name": s, "verified": "미검증",
                "usable_for_metrics": False} for s in spec["sources"]]
    detail = _empty_detail(
        tab_id, subject, filters,
        reason_code=V.SOURCE_NOT_VERIFIED,
        reason_text=spec["reason"] + " 미검증 소스로 화면을 채우지 않습니다 "
                    "(명세서 §13-6).",
        required_inputs=(area or {}).get("missing_inputs", []),
        required_sources=sources,
        actions=spec["actions"],
    )
    if area:
        detail["results"]["area"] = area
    return detail
