"""시장성·수출실적 지표 — 검증완료 API 에서만 계산한다 (명세서 §13-6).

소스: 관세청 품목별 국가별 수출입실적 (verified = 검증완료 2026-09-22)
      금액 USD, 중량 kg, 기간 월 단위 (활용가이드 문서 명시)

모든 지표에 통화·단위·기간을 붙인다 (명세서 §4).
계산은 Decimal 로 하고 화면 반올림은 display 블록에만 적용한다.
조회 실패·자료 없음·권한 없음·오래된 캐시를 값 대신 상태로 반환한다.
"""

from __future__ import annotations

from decimal import Decimal

from axport.external_data.providers import customs_trade as ct
from axport.metrics import money
from axport.rules_engine import values as V

CURRENCY = ct.AMOUNT_CURRENCY
WEIGHT_UNIT = ct.WEIGHT_UNIT
MULTIPLIER = 1          # 문서: 달러 단위 그대로. 배율을 임의로 넣지 않는다

FETCH_TO_STATE = {
    ct.NO_DATA: (V.NOT_ENTERED, V.API_NO_DATA),
    ct.NO_PERMISSION: (V.FETCH_FAILED, "api_no_permission"),
    ct.CONNECTION_FAILED: (V.FETCH_FAILED, V.API_CONNECTION_FAILED),
}


def _unavailable(result: ct.FetchResult, **extra) -> V.MeasuredValue:
    """조회가 실패했으면 값 대신 상태를 만든다. 0 으로 채우지 않는다."""
    state, reason = FETCH_TO_STATE.get(
        result.fetch_result, (V.NOT_EVALUATED, V.UPSTREAM_NOT_EVALUATED))
    kw = dict(source_id=result.source_id, period=result.period or None, **extra)
    if state == V.NOT_ENTERED:
        return V.not_entered(reason, **kw)
    if state == V.FETCH_FAILED:
        return V.fetch_failed(reason, **kw)
    return V.not_evaluated(reason, **kw)


def _amount(value: Decimal, result: ct.FetchResult, formula: str,
            rounding_policy: str | None) -> V.MeasuredValue:
    return V.actual(
        money.serialize(value),
        currency=CURRENCY,
        amount_multiplier=MULTIPLIER,
        period=result.period,
        source_id=result.source_id,
        asof_date=(result.fetched_at or "")[:10] or None,
        display=money.format_for_display(
            value, rounding_policy=rounding_policy).as_dict(),
        data_class=result.data_class,
        formula=formula,
    )


def _weight(value: Decimal, result: ct.FetchResult, formula: str,
            rounding_policy: str | None) -> V.MeasuredValue:
    return V.actual(
        money.serialize(value),
        unit=WEIGHT_UNIT,
        period=result.period,
        source_id=result.source_id,
        asof_date=(result.fetched_at or "")[:10] or None,
        display=money.format_for_display(
            value, rounding_policy=rounding_policy).as_dict(),
        data_class=result.data_class,
        formula=formula,
    )


def compute(result: ct.FetchResult, *, rounding_policy: str | None = None
            ) -> dict[str, V.MeasuredValue]:
    """한 번의 조회 결과에서 지표를 만든다.

    반환 키는 metric_id 다. 값이 없는 지표는 상태로 남긴다.
    """
    rows = result.detail_rows
    if not result.ok or not rows:
        reason_kw = {}
        return {
            "kr_export_amount": _unavailable(result, **reason_kw),
            "kr_export_weight": _unavailable(result),
            "kr_import_amount": _unavailable(result),
            "kr_trade_balance": _unavailable(result),
            "kr_export_months_covered": _unavailable(result),
            "kr_export_avg_monthly": _unavailable(result),
        }

    exp_amt = money.total([r.export_amount for r in rows])
    exp_wgt = money.total([r.export_weight for r in rows])
    imp_amt = money.total([r.import_amount for r in rows])

    out: dict[str, V.MeasuredValue] = {}

    if exp_amt is None:
        out["kr_export_amount"] = V.not_evaluated(
            "source_value_not_numeric", source_id=result.source_id,
            period=result.period)
    else:
        out["kr_export_amount"] = _amount(
            exp_amt, result, "sum(expDlr) over rows", rounding_policy)

    if exp_wgt is None:
        out["kr_export_weight"] = V.not_evaluated(
            "source_value_not_numeric", source_id=result.source_id,
            period=result.period)
    else:
        out["kr_export_weight"] = _weight(
            exp_wgt, result, "sum(expWgt) over rows", rounding_policy)

    if imp_amt is None:
        out["kr_import_amount"] = V.not_evaluated(
            "source_value_not_numeric", source_id=result.source_id,
            period=result.period)
    else:
        out["kr_import_amount"] = _amount(
            imp_amt, result, "sum(impDlr) over rows", rounding_policy)

    if exp_amt is not None and imp_amt is not None:
        out["kr_trade_balance"] = _amount(
            exp_amt - imp_amt, result,
            "sum(expDlr) - sum(impDlr)", rounding_policy)
    else:
        out["kr_trade_balance"] = V.not_evaluated(V.UPSTREAM_NOT_EVALUATED,
                                                 period=result.period)

    months = sorted({r.period for r in rows if r.period})
    out["kr_export_months_covered"] = V.actual(
        len(months), unit="개월", period=result.period,
        source_id=result.source_id, data_class=result.data_class,
        formula="count(distinct year)",
        display={"text": str(len(months)), "rounding_policy": money.POLICY_UNDECIDED,
                 "decimals": None, "rounded": False},
    )

    if exp_amt is not None and months:
        avg = exp_amt / Decimal(len(months))
        out["kr_export_avg_monthly"] = _amount(
            avg, result,
            "sum(expDlr) / count(distinct year)", rounding_policy)
    else:
        out["kr_export_avg_monthly"] = V.not_evaluated(V.UPSTREAM_NOT_EVALUATED,
                                                       period=result.period)
    return out


METRIC_LABEL = {
    "kr_export_amount": "한국 → 대상국 수출금액",
    "kr_export_weight": "한국 → 대상국 수출중량",
    "kr_import_amount": "대상국 → 한국 수입금액",
    "kr_trade_balance": "무역수지",
    "kr_export_months_covered": "자료가 있는 개월 수",
    "kr_export_avg_monthly": "월평균 수출금액",
}


def monthly_series(result: ct.FetchResult) -> list[dict]:
    """월별 시계열. 차트와 **표**에 같은 값을 쓴다 (명세서 §9).

    값은 문자열로 유지한다. 화면에서 다시 계산하지 않는다.
    """
    buckets: dict[str, dict] = {}
    for r in result.detail_rows:
        b = buckets.setdefault(r.period, {
            "period": r.period,
            "export_amount": Decimal(0), "export_weight": Decimal(0),
            "import_amount": Decimal(0), "rows": 0, "incomplete": False,
        })
        for key, raw in (("export_amount", r.export_amount),
                         ("export_weight", r.export_weight),
                         ("import_amount", r.import_amount)):
            d = money.to_decimal(raw)
            if d is None:
                b["incomplete"] = True      # 0 으로 채우지 않는다
            else:
                b[key] += d
        b["rows"] += 1

    series = []
    for period in sorted(buckets):
        b = buckets[period]
        series.append({
            "period": period,
            "export_amount": money.serialize(b["export_amount"]),
            "export_weight": money.serialize(b["export_weight"]),
            "import_amount": money.serialize(b["import_amount"]),
            "row_count": b["rows"],
            "incomplete": b["incomplete"],
            "currency": CURRENCY,
            "weight_unit": WEIGHT_UNIT,
        })
    return series


def hs_breakdown(result: ct.FetchResult) -> list[dict]:
    """세번별 상세 표."""
    buckets: dict[str, dict] = {}
    for r in result.detail_rows:
        b = buckets.setdefault(r.hs_code, {
            "hs_code": r.hs_code, "item_name": r.item_name,
            "export_amount": Decimal(0), "import_amount": Decimal(0),
            "rows": 0,
        })
        for key, raw in (("export_amount", r.export_amount),
                         ("import_amount", r.import_amount)):
            d = money.to_decimal(raw)
            if d is not None:
                b[key] += d
        b["rows"] += 1

    out = []
    for hs in sorted(buckets, key=lambda h: buckets[h]["export_amount"],
                     reverse=True):
        b = buckets[hs]
        out.append({
            "hs_code": b["hs_code"], "item_name": b["item_name"],
            "export_amount": money.serialize(b["export_amount"]),
            "import_amount": money.serialize(b["import_amount"]),
            "row_count": b["rows"], "currency": CURRENCY,
        })
    return out
