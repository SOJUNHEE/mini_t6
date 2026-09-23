"""③ 컬럼 매핑·단위 확인 (명세서 §5).

원칙
    자동 매핑은 **후보를 제시**한다. 불명확한 연결을 임의로 확정하지 않는다.
    확인이 필요한 항목이 하나라도 남아 있으면 분석 단계로 넘어가지 않는다.

매핑 상태
    exact          컬럼명이 정확히 일치. 확인 불필요
    needs_confirmation  별칭·유사도로 찾은 후보. **사용자 확인 필요**
    unmapped       후보가 없음. 사용자가 지정하거나 미사용으로 확정해야 함
    missing        양식에 있어야 할 컬럼이 업로드에 없음
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, asdict, field

from axport.upload_validation import schema
from axport.upload_validation.reader import WorkbookData

EXACT = "exact"
NEEDS_CONFIRMATION = "needs_confirmation"
UNMAPPED = "unmapped"
MISSING = "missing"

# 유사도 후보로 제시할 최소 점수. 이 점수로 **확정하지 않는다.**
SUGGEST_MIN_RATIO = 0.6
MAX_CANDIDATES = 3

_NORMALIZE_RE = re.compile(r"[\s_·\-()\[\]/]+")


def normalize(name: str) -> str:
    return _NORMALIZE_RE.sub("", name).strip().lower()


@dataclass
class Candidate:
    uploaded_column: str
    score: float
    basis: str      # alias | similarity


@dataclass
class ColumnMapping:
    sheet: str
    template_column: str
    requirement: str
    kind: str
    status: str
    uploaded_column: str | None = None
    candidates: list[Candidate] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["candidates"] = [asdict(c) for c in self.candidates]
        return d


@dataclass
class MappingReport:
    mappings: list[ColumnMapping]
    unused_uploaded_columns: list[dict]
    needs_confirmation_count: int
    unmapped_count: int
    missing_count: int
    confirmed: bool = False

    @property
    def ready_for_analysis(self) -> bool:
        """확인 대기 항목이 없고 사용자 확인이 끝났는가."""
        return self.needs_confirmation_count == 0 and self.unmapped_count == 0

    def as_dict(self) -> dict:
        return {
            "needs_confirmation_count": self.needs_confirmation_count,
            "unmapped_count": self.unmapped_count,
            "missing_count": self.missing_count,
            "confirmed": self.confirmed,
            "ready_for_analysis": self.ready_for_analysis,
            "mappings": [m.as_dict() for m in self.mappings],
            "unused_uploaded_columns": self.unused_uploaded_columns,
        }


def propose(data: WorkbookData) -> MappingReport:
    """업로드 컬럼과 양식 컬럼의 매핑 후보를 만든다. 확정하지 않는다."""
    mappings: list[ColumnMapping] = []
    unused: list[dict] = []

    for sheet_def in schema.SHEETS:
        sd = data.sheets.get(sheet_def.name)
        if not sd:
            continue

        uploaded = [h for h in sd.headers if h]
        norm_to_uploaded: dict[str, str] = {}
        for h in uploaded:
            norm_to_uploaded.setdefault(normalize(h), h)
        taken: set[str] = set()

        for col in sheet_def.columns:
            mapping = ColumnMapping(
                sheet=sheet_def.name,
                template_column=col.name,
                requirement=col.requirement,
                kind=col.kind,
                status=MISSING,
            )

            if col.name in uploaded:
                mapping.status = EXACT
                mapping.uploaded_column = col.name
                taken.add(col.name)
                mappings.append(mapping)
                continue

            # 정규화 일치도 완전 일치로 보지 않는다 — 확인 대상으로 둔다
            hit = norm_to_uploaded.get(normalize(col.name))
            if hit and hit not in taken:
                mapping.status = NEEDS_CONFIRMATION
                mapping.candidates.append(Candidate(hit, 1.0, "normalized"))
                taken.add(hit)
                mappings.append(mapping)
                continue

            for alias in col.aliases:
                hit = norm_to_uploaded.get(normalize(alias))
                if hit and hit not in taken:
                    mapping.status = NEEDS_CONFIRMATION
                    mapping.candidates.append(Candidate(hit, 0.95, "alias"))
                    taken.add(hit)
                    break
            if mapping.candidates:
                mappings.append(mapping)
                continue

            pool = [h for h in uploaded if h not in taken]
            scored = [
                Candidate(h, round(
                    difflib.SequenceMatcher(
                        None, normalize(col.name), normalize(h)
                    ).ratio(), 3), "similarity")
                for h in pool
            ]
            scored = [c for c in scored if c.score >= SUGGEST_MIN_RATIO]
            scored.sort(key=lambda c: c.score, reverse=True)
            if scored:
                mapping.status = NEEDS_CONFIRMATION
                mapping.candidates = scored[:MAX_CANDIDATES]
            mappings.append(mapping)

        for h in uploaded:
            if h not in taken and sheet_def.column(h) is None:
                unused.append({
                    "sheet": sheet_def.name,
                    "uploaded_column": h,
                    "status": UNMAPPED,
                    "note": "양식 컬럼과 연결되지 않았습니다. "
                            "사용자가 지정하거나 미사용으로 확정해야 합니다.",
                })

    needs = sum(1 for m in mappings if m.status == NEEDS_CONFIRMATION)
    missing = sum(1 for m in mappings if m.status == MISSING)
    return MappingReport(
        mappings=mappings,
        unused_uploaded_columns=unused,
        needs_confirmation_count=needs,
        unmapped_count=len(unused),
        missing_count=missing,
    )


def apply_confirmation(report: MappingReport,
                       decisions: dict[str, str | None]) -> MappingReport:
    """사용자 확인 결과를 반영한다.

    decisions 키는 "<시트>.<양식컬럼>", 값은 선택한 업로드 컬럼명 또는
    None(미사용으로 확정). 확인하지 않은 항목은 그대로 대기 상태로 남는다.
    """
    for m in report.mappings:
        key = f"{m.sheet}.{m.template_column}"
        if key not in decisions:
            continue
        chosen = decisions[key]
        if chosen is None:
            m.status = MISSING
            m.uploaded_column = None
        else:
            m.status = EXACT
            m.uploaded_column = chosen
        m.candidates = []

    for u in report.unused_uploaded_columns:
        key = f"{u['sheet']}.__unused__.{u['uploaded_column']}"
        if key in decisions:
            u["status"] = "confirmed_unused"

    report.needs_confirmation_count = sum(
        1 for m in report.mappings if m.status == NEEDS_CONFIRMATION
    )
    report.unmapped_count = sum(
        1 for u in report.unused_uploaded_columns if u["status"] == UNMAPPED
    )
    report.missing_count = sum(1 for m in report.mappings if m.status == MISSING)
    report.confirmed = report.ready_for_analysis
    return report


def from_dict(payload: dict) -> MappingReport:
    mappings = [
        ColumnMapping(
            sheet=m["sheet"],
            template_column=m["template_column"],
            requirement=m["requirement"],
            kind=m["kind"],
            status=m["status"],
            uploaded_column=m.get("uploaded_column"),
            candidates=[Candidate(**c) for c in m.get("candidates", [])],
        )
        for m in payload["mappings"]
    ]
    return MappingReport(
        mappings=mappings,
        unused_uploaded_columns=payload.get("unused_uploaded_columns", []),
        needs_confirmation_count=payload["needs_confirmation_count"],
        unmapped_count=payload["unmapped_count"],
        missing_count=payload["missing_count"],
        confirmed=payload.get("confirmed", False),
    )
