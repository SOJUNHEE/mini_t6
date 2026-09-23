"""⑤ 3층 판정 결과와 종합 게이트 (명세서 §6, rules/README.md §2·§3).

1층 mandatory_review   필수 조건 검토
2층 business_fitness   사업적 적합도
3층 evidence_status    근거 충족 상태
     overall           G1~G5 게이트로 도출

금지
    사업성 점수로 필수 조건 미충족을 상쇄하지 않는다.
    게이트 입력은 1층·3층뿐이다. business_fitness 를 읽지 않는다.
    점수 기준·가중치·임계값을 여기서 만들지 않는다. 설정에서 온다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from axport.config.settings import Settings
from axport.rules_engine import values as V
from axport.rules_engine.subject import MARKET_EXPLORATION, Subject
from axport.upload_validation import schema
from axport.upload_validation.reader import WorkbookData
from axport.upload_validation.validate import ERROR, ValidationReport

# design.md 메인 5개 항목 ↔ 층 배치 (rules/README.md §5.1)
REGULATION = "regulation"          # 1층
MARKET = "market"
PRICE = "price"
LOGISTICS = "logistics"
STABILITY = "stability"
BUSINESS_AREAS = (MARKET, PRICE, LOGISTICS, STABILITY)

AREA_LABEL = {
    REGULATION: "규제",
    MARKET: "시장성",
    PRICE: "가격",
    LOGISTICS: "물류",
    STABILITY: "안정성",
}

# 영역별로 필요한 업로드 입력 (없으면 '자료 부족')
AREA_REQUIRED_INPUTS: dict[str, tuple[tuple[str, str], ...]] = {
    MARKET: (("수출예정거래", "목적국코드"), ("제품정보", "HS코드")),
    PRICE: (("제품정보", "HS코드"), ("제품정보", "제조국코드"),
            ("수출예정거래", "단가"), ("수출예정거래", "통화"),
            ("수출예정거래", "금액배율"), ("원가·비용", "제조원가")),
    LOGISTICS: (("물류", "운임"), ("물류", "통화"), ("물류", "출발예정일"),
                ("물류", "도착예정일"), ("재고·생산", "공급가능수량")),
    STABILITY: (("거래처", "국가코드"), ("거래처", "주소"),
                ("거래처", "등록번호"), ("거래처", "최종사용자관계")),
}

# 영역별로 필요한 외부 자료 — api_registry.csv 의 verified 로 판단한다
AREA_REQUIRED_SOURCES: dict[str, tuple[str, ...]] = {
    MARKET: ("관세청_품목별 국가별 수출입실적(GW)", "UN Comtrade"),
    PRICE: ("관세청_품목번호별 관세율표", "WTO Timeseries API", "ECOS 통계 API"),
    LOGISTICS: ("해양수산부_선박운항정보",),
    STABILITY: ("한국무역보험공사_국가신용등급", "Consolidated Screening List"),
}

# 종합 판정
NOT_EVALUATED = "not_evaluated"
WITHHELD = "withheld"
BLOCKED_MANDATORY = "blocked_mandatory"
NEEDS_MORE_INFO = "needs_more_info"
PROCEED_WITH_CONDITIONS = "proceed_with_conditions"

DECISION_LABEL = {
    NOT_EVALUATED: "평가 보류",
    WITHHELD: "평가 보류",
    BLOCKED_MANDATORY: "필수 조건 미충족",
    NEEDS_MORE_INFO: "추가 확인 필요",
    PROCEED_WITH_CONDITIONS: "조건부 진행 가능",
}

DISCLAIMER = (
    "사업적 적합도 점수는 성공 확률이나 법적 허가 여부와 다르다. "
    "필수 조건 미충족을 점수로 상쇄하지 않는다. (명세서 §6)"
)


@dataclass
class Layer1:
    status: str
    status_reason_code: str | None
    confirmed_conditions: list[dict] = field(default_factory=list)
    unsatisfied_conditions: list[dict] = field(default_factory=list)
    pending_checks: list[dict] = field(default_factory=list)
    blocking_unsatisfied_count: int = 0
    blocking_pending_count: int = 0

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "status_reason_code": self.status_reason_code,
            "display_label": V.DISPLAY_LABEL.get(V.NOT_EVALUATED)
            if self.status in (NOT_EVALUATED, WITHHELD) else None,
            "confirmed_conditions": self.confirmed_conditions,
            "unsatisfied_conditions": self.unsatisfied_conditions,
            "pending_checks": self.pending_checks,
            "blocking_unsatisfied_count": self.blocking_unsatisfied_count,
            "blocking_pending_count": self.blocking_pending_count,
        }


@dataclass
class AreaResult:
    area_code: str
    label: str
    status: str
    subscore: V.MeasuredValue
    metrics: list[dict] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)
    missing_sources: list[dict] = field(default_factory=list)
    required_to_evaluate: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "area_code": self.area_code,
            "label": self.label,
            "status": self.status,
            "subscore": self.subscore.as_dict(),
            "metrics": self.metrics,
            "missing_inputs": self.missing_inputs,
            "missing_sources": self.missing_sources,
            "required_to_evaluate": self.required_to_evaluate,
        }


@dataclass
class Layer2:
    status: str
    areas: list[AreaResult]
    composite: V.MeasuredValue
    scoring_config_ref: dict

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "areas": [a.as_dict() for a in self.areas],
            "composite": self.composite.as_dict(),
            "scoring_config_ref": self.scoring_config_ref,
        }


@dataclass
class Layer3:
    overall: str
    input_completeness_by_area: list[dict]
    missing_inputs: list[dict]
    data_sources: list[dict]
    rule_readiness: list[dict]
    validation_summary: dict

    def as_dict(self) -> dict:
        return {
            "overall": self.overall,
            "input_completeness_by_area": self.input_completeness_by_area,
            "missing_inputs": self.missing_inputs,
            "data_sources": self.data_sources,
            "rule_readiness": self.rule_readiness,
            "validation_summary": self.validation_summary,
        }


def _cell_present(data: WorkbookData, sheet_name: str, column: str) -> bool:
    sd = data.sheets.get(sheet_name)
    if not sd or not sd.rows:
        return False
    for record in sd.rows:
        cell = record.get(column)
        if cell and cell.is_present and cell.text not in schema.NOT_APPLICABLE_TOKENS:
            return True
    return False


def build_layer1(rule_readiness: list[dict]) -> Layer1:
    """필수 조건 검토.

    현재 판정 규칙이 미확보·미검토이므로 조건 집합을 만들지 않는다.
    규칙 내용을 추측해 채우지 않는다 (명세서 §6·§7).
    """
    unusable = [r for r in rule_readiness if not r["usable_in_production"]]
    if unusable:
        pending = [{
            "check_id": f"rules.{r['rule_set_id']}",
            "question": "판정 규칙 원문 확보·대조가 필요합니다.",
            "required_sources": r["source_files"],
            "blocking": True,
            "reason_code": r["reason_code"],
        } for r in unusable]
        return Layer1(
            status=WITHHELD,
            status_reason_code=V.RULE_SOURCE_MISSING,
            pending_checks=pending,
            blocking_pending_count=len(pending),
        )
    return Layer1(status=NOT_EVALUATED, status_reason_code=V.RULE_SET_UNREVIEWED)


def build_layer2(data: WorkbookData, subject: Subject,
                 settings: Settings, source_status: dict) -> Layer2:
    """사업적 적합도. 가중치·임계값이 미승인이면 계산하지 않는다."""
    scoring_ref = {
        "config_id": settings.get("versions.scoring_config_version") or None,
        "version": settings.get("versions.scoring_config_version") or None,
        "review_status": "미검토",
        "approved_by": None,
        "approved_at": None,
    }
    scoring_approved = settings.is_decided("versions.scoring_config_version")

    areas: list[AreaResult] = []
    for code in BUSINESS_AREAS:
        missing_inputs = [
            f"{s}.{c}" for s, c in AREA_REQUIRED_INPUTS[code]
            if not _cell_present(data, s, c)
        ]
        missing_sources = [
            src for src in source_status.get(code, [])
            if src["verified"] != "검증완료"
        ]

        required: list[str] = []
        if missing_inputs:
            required.append("업로드 입력 보완: " + ", ".join(missing_inputs))
        if missing_sources:
            required.append(
                "외부 자료 검증: "
                + ", ".join(s["api_name"] for s in missing_sources)
            )
        if not scoring_approved:
            required.append(
                "점수 항목·가중치·임계값 승인 (명세서 §2)"
            )

        if not scoring_approved:
            reason = V.SCORING_CONFIG_UNAPPROVED
            subscore = V.not_evaluated(reason, tuple(missing_inputs))
        elif missing_inputs:
            subscore = V.not_entered(required_inputs=tuple(missing_inputs))
        elif missing_sources:
            subscore = V.not_evaluated(V.SOURCE_NOT_VERIFIED)
        else:
            subscore = V.not_evaluated(V.UPSTREAM_NOT_EVALUATED)

        areas.append(AreaResult(
            area_code=code,
            label=AREA_LABEL[code],
            status=NOT_EVALUATED,
            subscore=subscore,
            metrics=[],   # 지표 계산 미구현. 없는 것을 있다고 하지 않는다
            missing_inputs=missing_inputs,
            missing_sources=missing_sources,
            required_to_evaluate=required,
        ))

    composite = V.not_evaluated(
        V.SCORING_CONFIG_UNAPPROVED if not scoring_approved
        else V.UPSTREAM_NOT_EVALUATED
    )
    return Layer2(status=NOT_EVALUATED, areas=areas,
                  composite=composite, scoring_config_ref=scoring_ref)


def build_layer3(data: WorkbookData, validation: ValidationReport,
                 subject: Subject, rule_readiness: list[dict],
                 source_status: dict) -> Layer3:
    completeness: list[dict] = []
    for code in BUSINESS_AREAS:
        required = AREA_REQUIRED_INPUTS[code]
        missing = [f"{s}.{c}" for s, c in required if not _cell_present(data, s, c)]
        completeness.append({
            "area_code": code,
            "label": AREA_LABEL[code],
            "required_total": len(required),
            "present": len(required) - len(missing),
            "missing_fields": missing,
            "state": V.NOT_ENTERED if missing else V.ACTUAL,
        })

    missing_inputs = [
        {"sheet": f.sheet, "row": f.row, "column": f.column,
         "requirement_class": (f.detail or {}).get("requirement", "area_required"),
         "code": f.code, "message": f.message}
        for f in validation.findings
        if f.code in ("required_missing", "area_required_missing")
    ]

    sources: list[dict] = []
    for code, entries in source_status.items():
        for e in entries:
            sources.append({**e, "area_code": code})

    has_blocking_errors = validation.counts.get(ERROR, 0) > 0
    unverified = [s for s in sources if s["verified"] != "검증완료"]
    overall = "insufficient" if (has_blocking_errors or missing_inputs
                                 or unverified) else "sufficient"

    return Layer3(
        overall=overall,
        input_completeness_by_area=completeness,
        missing_inputs=missing_inputs,
        data_sources=sources,
        rule_readiness=rule_readiness,
        validation_summary={
            "counts": validation.counts,
            "blocking": validation.blocking,
            "row_counts": validation.row_counts,
        },
    )


def apply_gates(layer1: Layer1, layer3: Layer3) -> dict:
    """G1~G5. 입력은 1층·3층뿐이다. layer2 를 읽지 않는다."""
    trace: list[dict] = []
    decision = PROCEED_WITH_CONDITIONS
    reasons: list[str] = []

    g1_fail = any(not r["usable_in_production"] for r in layer3.rule_readiness)
    trace.append({"gate_id": "G1", "check": "rule_readiness.usable_in_production",
                  "passed": not g1_fail})
    if g1_fail:
        decision = WITHHELD
        reasons.append(V.RULE_SOURCE_MISSING)

    g2_fail = layer1.blocking_unsatisfied_count > 0
    trace.append({"gate_id": "G2", "check": "blocking_unsatisfied_count",
                  "passed": not g2_fail})
    if decision == PROCEED_WITH_CONDITIONS and g2_fail:
        decision = BLOCKED_MANDATORY
        reasons.append("blocking_unsatisfied_condition")

    g3_fail = layer1.blocking_pending_count > 0
    trace.append({"gate_id": "G3", "check": "blocking_pending_count",
                  "passed": not g3_fail})
    if decision == PROCEED_WITH_CONDITIONS and g3_fail:
        decision = NEEDS_MORE_INFO
        reasons.append("blocking_pending_check")

    g4_fail = layer3.overall == "insufficient"
    trace.append({"gate_id": "G4", "check": "evidence_status.overall",
                  "passed": not g4_fail})
    if decision == PROCEED_WITH_CONDITIONS and g4_fail:
        decision = NEEDS_MORE_INFO
        reasons.append("evidence_insufficient")

    trace.append({"gate_id": "G5", "check": "all_previous_passed",
                  "passed": decision == PROCEED_WITH_CONDITIONS})

    return {
        "decision": decision,
        "decision_label": DECISION_LABEL[decision],
        "decision_reason_codes": reasons,
        "gate_trace": trace,
        "gate_inputs": ["mandatory_review", "evidence_status"],
        "business_fitness_is_gate_input": False,
        "disclaimer": DISCLAIMER,
    }


def build_main_summary(layer1: Layer1, layer2: Layer2) -> list[dict]:
    """design.md 메인 5개 항목. 핵심 결과 1개 + 짧은 설명 1줄.

    상세 수치·차트는 여기 넣지 않는다. 책갈피 탭 소관이다.
    """
    items = [{
        "item": REGULATION,
        "label": AREA_LABEL[REGULATION],
        "layer": "mandatory_review",
        "headline": DECISION_LABEL.get(layer1.status, layer1.status),
        "note": "판정 규칙 원문 미확보·미대조로 평가를 시작하지 않았습니다.",
        "state": V.NOT_EVALUATED,
    }]
    for area in layer2.areas:
        items.append({
            "item": area.area_code,
            "label": area.label,
            "layer": "business_fitness",
            "headline": area.subscore.display_label,
            "note": (area.required_to_evaluate[0]
                     if area.required_to_evaluate else ""),
            "state": area.subscore.state,
        })
    return items
