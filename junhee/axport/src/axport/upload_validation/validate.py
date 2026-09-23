"""② 검증 — 숫자·날짜·중복·범위·연결 오류 (명세서 §5).

결과는 오류(error) / 경고(warning) / 정보(info) 로 구분해
**시트명과 엑셀 실제 행 번호**와 함께 반환한다.

금지
    입력 누락을 0 이나 임의 값으로 채우지 않는다. 누락은 누락으로 보고한다.
    실제 값 0 / 미입력 / 해당 없음을 같은 것으로 처리하지 않는다 (명세서 §4).
"""

from __future__ import annotations

import datetime as dt
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict

from axport.upload_validation import schema
from axport.upload_validation.reader import Cell, WorkbookData

ERROR = "error"
WARNING = "warning"
INFO = "info"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class Finding:
    severity: str
    code: str
    sheet: str
    row: int | None          # 엑셀 실제 행 번호. 시트 전체 문제면 None
    column: str | None
    message: str
    detail: dict | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ValidationReport:
    findings: list[Finding]
    row_counts: dict[str, int]
    blocking: bool
    counts: dict[str, int]

    def as_dict(self) -> dict:
        return {
            "blocking": self.blocking,
            "counts": self.counts,
            "row_counts": self.row_counts,
            "findings": [f.as_dict() for f in self.findings],
        }


def _is_na(cell: Cell) -> bool:
    return bool(cell.text and cell.text in schema.NOT_APPLICABLE_TOKENS)


def _parse_number(cell: Cell) -> float | None:
    if isinstance(cell.raw, bool):
        return None
    if isinstance(cell.raw, (int, float)):
        return float(cell.raw)
    if cell.text is None:
        return None
    text = cell.text.replace(",", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def _parse_date(cell: Cell) -> dt.date | None:
    """YYYY-MM-DD 문자열 또는 엑셀 날짜값만 인정한다."""
    if isinstance(cell.raw, dt.datetime):
        return cell.raw.date()
    if isinstance(cell.raw, dt.date):
        return cell.raw
    if not cell.text or not DATE_RE.match(cell.text):
        return None
    try:
        return dt.date.fromisoformat(cell.text)
    except ValueError:
        return None   # 2026-13-45 처럼 형식은 맞아도 존재하지 않는 날짜


def validate(data: WorkbookData) -> ValidationReport:
    findings: list[Finding] = []
    row_counts: dict[str, int] = {}

    for name in data.missing_sheets:
        findings.append(Finding(
            ERROR, "sheet_missing", name, None, None,
            f"필수 시트 '{name}' 가 없습니다.",
        ))
    for name in data.extra_sheets:
        findings.append(Finding(
            INFO, "sheet_unknown", name, None, None,
            f"양식에 없는 시트 '{name}' 입니다. 분석에 사용하지 않습니다.",
        ))

    # 참조 대상 키 수집 (연결 검사용)
    key_index: dict[str, set[str]] = defaultdict(set)
    for sheet_def in schema.SHEETS:
        sd = data.sheets.get(sheet_def.name)
        if not sd:
            continue
        for record in sd.rows:
            cell = record.get(sheet_def.primary_key)
            if cell and cell.is_present and cell.text:
                key_index[sheet_def.name].add(cell.text)

    for sheet_def in schema.SHEETS:
        sd = data.sheets.get(sheet_def.name)
        if not sd:
            continue
        row_counts[sheet_def.name] = len(sd.rows)

        _check_headers(sheet_def, sd, findings)
        for fc in sd.formula_cells:
            findings.append(Finding(
                ERROR, "formula_cell", fc["sheet"], fc["row"], fc["column"],
                "수식 셀입니다. 수식을 실행하지 않으며 값으로 사용하지 않습니다. "
                "(명세서 §5)",
            ))

        for record, row_no in zip(sd.rows, sd.row_numbers):
            _check_row(sheet_def, record, row_no, findings)
            _check_references(sheet_def, record, row_no, key_index, findings)

        _check_duplicates(sheet_def, sd, findings)

    counts = Counter(f.severity for f in findings)
    return ValidationReport(
        findings=findings,
        row_counts=row_counts,
        blocking=counts.get(ERROR, 0) > 0,
        counts={ERROR: counts.get(ERROR, 0),
                WARNING: counts.get(WARNING, 0),
                INFO: counts.get(INFO, 0)},
    )


def _check_headers(sheet_def: schema.Sheet, sd, findings: list[Finding]) -> None:
    present = set(sd.headers)
    for col in sheet_def.columns:
        if col.name not in present:
            sev = ERROR if col.requirement == schema.COMMON_REQUIRED else WARNING
            findings.append(Finding(
                sev, "column_missing", sheet_def.name, schema.HEADER_ROW, col.name,
                f"컬럼 '{col.name}' 가 없습니다.",
                {"requirement": col.requirement},
            ))
    for header in sd.headers:
        if header and sheet_def.column(header) is None:
            findings.append(Finding(
                INFO, "column_unknown", sheet_def.name, schema.HEADER_ROW, header,
                f"양식에 없는 컬럼 '{header}' 입니다. 매핑 확인 대상입니다.",
            ))


def _check_row(sheet_def: schema.Sheet, record: dict[str, Cell], row_no: int,
               findings: list[Finding]) -> None:
    for col in sheet_def.columns:
        cell = record.get(col.name)
        if cell is None:
            continue

        # 해당 없음 — 미입력과 구분해 정보로 기록한다
        if _is_na(cell):
            findings.append(Finding(
                INFO, "value_not_applicable", sheet_def.name, row_no, col.name,
                "'해당 없음'으로 입력되었습니다. 미입력과 구분해 처리합니다.",
            ))
            continue

        # 누락 — 0 으로 채우지 않는다
        if cell.is_blank:
            if col.requirement == schema.COMMON_REQUIRED:
                findings.append(Finding(
                    ERROR, "required_missing", sheet_def.name, row_no, col.name,
                    f"공통 필수 항목 '{col.name}' 가 비어 있습니다. "
                    "0 이나 임의 값으로 채우지 않습니다.",
                ))
            elif col.requirement == schema.AREA_REQUIRED:
                findings.append(Finding(
                    WARNING, "area_required_missing", sheet_def.name, row_no,
                    col.name,
                    f"'{col.name}' 가 비어 있어 '{col.area}' 영역은 "
                    "'자료 부족'으로 처리됩니다.",
                    {"area": col.area},
                ))
            continue

        if col.kind == schema.NUM:
            number = _parse_number(cell)
            if number is None:
                findings.append(Finding(
                    ERROR, "not_a_number", sheet_def.name, row_no, col.name,
                    f"숫자가 아닙니다: '{cell.text}'",
                ))
            else:
                if col.non_negative and number < 0:
                    findings.append(Finding(
                        ERROR, "out_of_range", sheet_def.name, row_no, col.name,
                        f"음수는 허용되지 않습니다: {number}",
                    ))
                if number == 0:
                    findings.append(Finding(
                        INFO, "value_is_real_zero", sheet_def.name, row_no, col.name,
                        "값 0 을 '실제 값 0' 으로 처리합니다. 미입력이 아닙니다.",
                    ))
                if col.name == "금액배율" and number not in (1, 1000, 1000000):
                    findings.append(Finding(
                        ERROR, "out_of_range", sheet_def.name, row_no, col.name,
                        f"금액배율은 1 / 1000 / 1000000 중 하나여야 합니다: {number}",
                    ))

        elif col.kind == schema.DATE:
            if _parse_date(cell) is None:
                findings.append(Finding(
                    ERROR, "invalid_date", sheet_def.name, row_no, col.name,
                    f"날짜 형식이 YYYY-MM-DD 가 아니거나 존재하지 않는 "
                    f"날짜입니다: '{cell.text}'",
                ))

    for start_col, end_col in sheet_def.date_order:
        s_cell, e_cell = record.get(start_col), record.get(end_col)
        if not s_cell or not e_cell or s_cell.is_blank or e_cell.is_blank:
            continue
        if _is_na(s_cell) or _is_na(e_cell):
            continue
        s, e = _parse_date(s_cell), _parse_date(e_cell)
        if s and e and e < s:
            findings.append(Finding(
                ERROR, "out_of_range", sheet_def.name, row_no, end_col,
                f"'{end_col}'({e}) 가 '{start_col}'({s}) 보다 빠릅니다.",
            ))


def _check_references(sheet_def: schema.Sheet, record: dict[str, Cell], row_no: int,
                      key_index: dict[str, set[str]],
                      findings: list[Finding]) -> None:
    for column, target_sheet, target_column in sheet_def.references:
        cell = record.get(column)
        if not cell or cell.is_blank or _is_na(cell):
            continue
        known = key_index.get(target_sheet)
        if known is None:
            continue  # 대상 시트가 없는 건 sheet_missing 으로 이미 보고됨
        if cell.text not in known:
            findings.append(Finding(
                ERROR, "broken_reference", sheet_def.name, row_no, column,
                f"'{cell.text}' 가 '{target_sheet}' 시트의 "
                f"'{target_column}' 에 없습니다. 연결이 끊겼습니다.",
                {"value": cell.text, "target_sheet": target_sheet,
                 "target_column": target_column},
            ))


def _check_duplicates(sheet_def: schema.Sheet, sd, findings: list[Finding]) -> None:
    # 주키 중복
    seen: dict[str, int] = {}
    for record, row_no in zip(sd.rows, sd.row_numbers):
        cell = record.get(sheet_def.primary_key)
        if not cell or cell.is_blank or not cell.text:
            continue
        if cell.text in seen:
            findings.append(Finding(
                ERROR, "duplicate_key", sheet_def.name, row_no,
                sheet_def.primary_key,
                f"'{cell.text}' 가 {seen[cell.text]}행에서 이미 사용되었습니다.",
                {"value": cell.text, "first_row": seen[cell.text]},
            ))
        else:
            seen[cell.text] = row_no

    # 전체 컬럼이 동일한 행
    identity = sheet_def.row_identity or sheet_def.column_names
    fingerprints: dict[tuple, int] = {}
    for record, row_no in zip(sd.rows, sd.row_numbers):
        key = tuple(
            (record[c].text if c in record and record[c].is_present else None)
            for c in identity
        )
        if key in fingerprints:
            findings.append(Finding(
                ERROR, "duplicate_row", sheet_def.name, row_no, None,
                f"{fingerprints[key]}행과 내용이 완전히 같은 중복 행입니다.",
                {"first_row": fingerprints[key], "compared_columns": list(identity)},
            ))
        else:
            fingerprints[key] = row_no
