"""기업 업로드 실적 지표 — 데이터 구분은 user_input 이다 (명세서 §7).

외부 자료가 아니라 기업이 올린 값이다. 화면에서 실제 외부 자료와
구분해 표시해야 하므로 data_class 를 user_input 으로 고정한다.

취소 건과 실제 값 0 을 구분한다. 미입력을 0 으로 채우지 않는다.
통화가 섞여 있으면 합산하지 않는다 (명세서 §4 — 단위·통화 일치 검토).
"""

from __future__ import annotations

from decimal import Decimal

from axport.metrics import money
from axport.rules_engine import values as V
from axport.upload_validation import schema
from axport.upload_validation.reader import WorkbookData

DATA_CLASS = "user_input"
SHEET = "수출실적"


def _cell_text(record, name):
    cell = record.get(name)
    if not cell or cell.is_blank:
        return None
    if cell.text in schema.NOT_APPLICABLE_TOKENS:
        return None
    return cell.text


def _rows_in_scope(data: WorkbookData, *, product_id: str,
                   destination: str, period: dict | None) -> list[dict]:
    sd = data.sheets.get(SHEET)
    if not sd:
        return []
    out = []
    for record, row_no in zip(sd.rows, sd.row_numbers):
        if _cell_text(record, "제품ID") != product_id:
            continue
        if _cell_text(record, "목적국코드") != destination:
            continue
        trade_date = _cell_text(record, "거래일")
        if period and trade_date:
            ym = trade_date[:7].replace("/", "-")
            if not (period["start"] <= ym <= period["end"]):
                continue
        out.append({"row": row_no, "record": record, "date": trade_date})
    return out


def compute(data: WorkbookData, *, product_id: str, destination: str,
            period: dict | None = None,
            rounding_policy: str | None = None) -> dict:
    """업로드 실적에서 지표를 만든다."""
    rows = _rows_in_scope(data, product_id=product_id,
                          destination=destination, period=period)

    if not rows:
        missing = (f"{SHEET} 시트에 제품 {product_id} / 목적국 {destination} "
                   f"행이 없습니다")
        nv = V.not_entered(V.MISSING_REQUIRED_INPUT,
                           required_inputs=(missing,), period=period)
        return {
            "metrics": {k: nv for k in METRIC_LABEL},
            "table": [],
            "currency_mixed": False,
            "row_count": 0,
        }

    currencies = {_cell_text(r["record"], "통화") for r in rows}
    currencies.discard(None)
    mixed = len(currencies) > 1
    currency = next(iter(currencies)) if len(currencies) == 1 else None

    amounts: list[object] = []
    quantities: list[object] = []
    units = set()
    cancelled = 0
    returns: list[object] = []
    incomplete_amount = False
    incomplete_qty = False

    table = []
    for r in rows:
        rec = r["record"]
        amt = _cell_text(rec, "금액")
        qty = _cell_text(rec, "수량")
        unit = _cell_text(rec, "수량단위")
        cancel = _cell_text(rec, "취소여부")
        ret = _cell_text(rec, "반품수량")
        if unit:
            units.add(unit)
        if cancel == "Y":
            cancelled += 1
        if amt is None:
            incomplete_amount = True
        else:
            amounts.append(amt)
        if qty is None:
            incomplete_qty = True
        else:
            quantities.append(qty)
        if ret is not None:
            returns.append(ret)

        table.append({
            "row": r["row"],
            "trade_date": r["date"],
            "quantity": qty, "quantity_unit": unit,
            "amount": amt, "currency": _cell_text(rec, "통화"),
            "amount_multiplier": _cell_text(rec, "금액배율"),
            "cancelled": cancel,
            "return_quantity": ret,
            "data_class": DATA_CLASS,
        })

    metrics: dict[str, V.MeasuredValue] = {}

    def amount_metric(values, formula):
        if mixed:
            return V.not_evaluated(
                "currency_mixed",
                required_inputs=(f"통화가 섞여 있습니다: {sorted(currencies)}",),
                period=period)
        if incomplete_amount or not values:
            return V.not_entered(
                V.MISSING_REQUIRED_INPUT,
                required_inputs=(f"{SHEET}.금액 미입력 행이 있습니다",),
                period=period, currency=currency)
        total = money.total(values)
        if total is None:
            return V.not_evaluated("value_not_numeric", period=period)
        return V.actual(
            money.serialize(total), currency=currency, amount_multiplier=1,
            period=period, data_class=DATA_CLASS, formula=formula,
            display=money.format_for_display(
                total, rounding_policy=rounding_policy).as_dict(),
        )

    metrics["upload_export_amount"] = amount_metric(
        amounts, f"sum({SHEET}.금액) where 제품ID·목적국코드·기간 일치")

    if incomplete_qty or not quantities:
        metrics["upload_export_quantity"] = V.not_entered(
            V.MISSING_REQUIRED_INPUT,
            required_inputs=(f"{SHEET}.수량 미입력 행이 있습니다",), period=period)
    elif len(units) > 1:
        metrics["upload_export_quantity"] = V.not_evaluated(
            "unit_mixed",
            required_inputs=(f"수량단위가 섞여 있습니다: {sorted(units)}",),
            period=period)
    else:
        total_qty = money.total(quantities)
        metrics["upload_export_quantity"] = V.actual(
            money.serialize(total_qty), unit=next(iter(units)) if units else None,
            period=period, data_class=DATA_CLASS,
            formula=f"sum({SHEET}.수량)",
            display=money.format_for_display(
                total_qty, rounding_policy=rounding_policy).as_dict(),
        )

    metrics["upload_row_count"] = V.actual(
        len(rows), unit="건", period=period, data_class=DATA_CLASS,
        formula=f"count({SHEET} rows in scope)",
        display={"text": str(len(rows)), "rounding_policy": money.POLICY_UNDECIDED,
                 "decimals": None, "rounded": False})

    metrics["upload_cancelled_count"] = V.actual(
        cancelled, unit="건", period=period, data_class=DATA_CLASS,
        formula=f"count({SHEET}.취소여부 == 'Y')",
        display={"text": str(cancelled), "rounding_policy": money.POLICY_UNDECIDED,
                 "decimals": None, "rounded": False})

    if returns:
        total_ret = money.total(returns)
        metrics["upload_return_quantity"] = (
            V.actual(money.serialize(total_ret),
                     unit=next(iter(units)) if len(units) == 1 else None,
                     period=period, data_class=DATA_CLASS,
                     formula=f"sum({SHEET}.반품수량)",
                     display=money.format_for_display(
                         total_ret, rounding_policy=rounding_policy).as_dict())
            if total_ret is not None
            else V.not_evaluated("value_not_numeric", period=period))
    else:
        metrics["upload_return_quantity"] = V.not_entered(
            V.MISSING_REQUIRED_INPUT,
            required_inputs=(f"{SHEET}.반품수량 미입력",), period=period)

    return {
        "metrics": metrics,
        "table": sorted(table, key=lambda t: (t["trade_date"] or "", t["row"])),
        "currency_mixed": mixed,
        "row_count": len(rows),
    }


METRIC_LABEL = {
    "upload_export_amount": "업로드 실적 수출금액",
    "upload_export_quantity": "업로드 실적 수출수량",
    "upload_row_count": "해당 실적 행 수",
    "upload_cancelled_count": "취소 건수",
    "upload_return_quantity": "반품수량 합계",
}
