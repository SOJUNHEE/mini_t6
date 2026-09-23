"""④ 평가 대상 선택 — 평가 단위 (명세서 §3).

평가 단위
    기업 + 제품·모델 + 목적국 + 거래 조건 + 평가 기준일

거래 조건이 없으면 `market_exploration`(시장 탐색)으로 표시하고
**완결된 거래 판정으로 표시하지 않는다.**

HS 코드는 제품을 연결하는 분류 정보이며 단독으로 종합 판정을 확정하는
입력이 아니다. 이름·표시명은 식별자로 사용하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field

from axport.upload_validation import schema
from axport.upload_validation.reader import Cell, WorkbookData

DEAL_EVALUATION = "deal_evaluation"      # 구체적인 거래 평가
MARKET_EXPLORATION = "market_exploration"  # 시장 탐색

MODE_LABEL = {
    DEAL_EVALUATION: "거래 평가",
    MARKET_EXPLORATION: "시장 탐색",
}

# 거래 조건으로 인정하는 항목 (명세서 §3)
TRADE_TERM_FIELDS = (
    "거래처ID", "최종사용자명", "최종용도", "수량", "수량단위",
    "단가", "통화", "금액배율", "납기일", "인도조건",
)
# 이 중 하나라도 비면 '완결된 거래 평가'로 보지 않는다
TRADE_TERM_ESSENTIALS = ("수량", "수량단위", "단가", "통화", "금액배율",
                         "납기일", "인도조건")


class SubjectError(ValueError):
    pass


@dataclass
class Subject:
    subject_id: str
    company_id: str
    product_id: str
    model_name: str | None
    hs_code: str | None
    hs_version: str | None
    manufacture_country: str | None
    destination_country_code: str
    destination_country_raw: str | None
    evaluation_base_date: str | None
    analysis_mode: str
    analysis_mode_label: str
    trade_terms: dict = field(default_factory=dict)
    missing_trade_terms: list[str] = field(default_factory=list)
    source_rows: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = asdict(self)
        if self.analysis_mode == MARKET_EXPLORATION:
            d["disclaimer"] = (
                "거래 조건이 확보되지 않았습니다. 시장 탐색 결과이며 "
                "완결된 거래 판정이 아닙니다. (명세서 §3)"
            )
        return d


def _text(record: dict[str, Cell], name: str) -> str | None:
    cell = record.get(name)
    if not cell or cell.is_blank:
        return None
    if cell.text in schema.NOT_APPLICABLE_TOKENS:
        return None
    return cell.text


def _value(record: dict[str, Cell], name: str):
    cell = record.get(name)
    if not cell or cell.is_blank:
        return None
    return cell.raw if not isinstance(cell.raw, str) else cell.text


def list_candidates(data: WorkbookData) -> list[Subject]:
    """수출예정거래 시트에서 평가 대상 후보를 만든다.

    거래 조건이 불완전한 행도 버리지 않는다. 시장 탐색으로 표시한다.
    """
    products = {}
    psd = data.sheets.get("제품정보")
    if psd:
        for record in psd.rows:
            pid = _text(record, "제품ID")
            if pid:
                products[pid] = record

    tsd = data.sheets.get("수출예정거래")
    if not tsd:
        return []

    subjects: list[Subject] = []
    for record, row_no in zip(tsd.rows, tsd.row_numbers):
        company = _text(record, "기업ID")
        deal_id = _text(record, "거래ID")
        product_id = _text(record, "제품ID")
        destination = _text(record, "목적국코드")

        warnings: list[str] = []
        if not company or not product_id or not destination:
            # 평가 단위를 구성할 수 없다. 값을 추측해 채우지 않는다.
            warnings.append(
                "기업ID·제품ID·목적국코드 중 비어 있는 항목이 있어 "
                "평가 단위를 구성할 수 없습니다."
            )

        product = products.get(product_id) if product_id else None
        if product_id and product is None:
            warnings.append(
                f"제품ID '{product_id}' 가 제품정보 시트에 없습니다."
            )

        terms: dict = {}
        missing: list[str] = []
        for name in TRADE_TERM_FIELDS:
            val = _value(record, name)
            if val is None:
                missing.append(name)
            else:
                terms[name] = val

        essentials_missing = [f for f in TRADE_TERM_ESSENTIALS if f in missing]
        mode = MARKET_EXPLORATION if essentials_missing else DEAL_EVALUATION

        subjects.append(Subject(
            subject_id=f"{company or '?'}|{product_id or '?'}|"
                       f"{destination or '?'}|{deal_id or f'row{row_no}'}",
            company_id=company or "",
            product_id=product_id or "",
            model_name=_text(product, "모델명") if product else None,
            hs_code=_text(product, "HS코드") if product else None,
            hs_version=_text(product, "HS버전") if product else None,
            manufacture_country=_text(product, "제조국코드") if product else None,
            destination_country_code=destination or "",
            destination_country_raw=_text(record, "목적국명_원본"),
            evaluation_base_date=_text(record, "평가기준일"),
            analysis_mode=mode,
            analysis_mode_label=MODE_LABEL[mode],
            trade_terms=terms,
            missing_trade_terms=missing,
            source_rows={"수출예정거래": row_no,
                         "제품정보": None},
            warnings=warnings,
        ))
    return subjects


def select(data: WorkbookData, subject_id: str) -> Subject:
    for s in list_candidates(data):
        if s.subject_id == subject_id:
            return s
    raise SubjectError(f"평가 대상을 찾을 수 없습니다: {subject_id}")
