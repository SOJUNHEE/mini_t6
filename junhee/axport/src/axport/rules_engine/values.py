"""값 상태 타입 — MeasuredValue (명세서 §4, rules/README.md §1).

실제 값 0 / 미입력 / 미평가 / 해당 없음 / 조회 실패 를
**절대 같은 값으로 표현하지 않는다.**

`value` 는 state == ACTUAL 일 때만 직렬화에 포함된다. 다른 상태에서
`value` 키 자체가 없으므로, null 하나로 뭉개지지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ACTUAL = "actual"
NOT_ENTERED = "not_entered"
NOT_EVALUATED = "not_evaluated"
NOT_APPLICABLE = "not_applicable"
FETCH_FAILED = "fetch_failed"

STATES = (ACTUAL, NOT_ENTERED, NOT_EVALUATED, NOT_APPLICABLE, FETCH_FAILED)

# 화면 표기 (design.md). 색상만으로 구분하지 않는다 (명세서 §9).
DISPLAY_LABEL = {
    ACTUAL: None,                 # 값을 그대로 표시
    NOT_ENTERED: "자료 부족",
    NOT_EVALUATED: "평가 보류",
    NOT_APPLICABLE: "해당 없음",
    FETCH_FAILED: "조회 실패",
}

# reason_code (rules/README.md §1.1)
MISSING_REQUIRED_INPUT = "missing_required_input"
RULE_SET_UNREVIEWED = "rule_set_unreviewed"
RULE_SOURCE_MISSING = "rule_source_missing"
SCORING_CONFIG_UNAPPROVED = "scoring_config_unapproved"
UPSTREAM_NOT_EVALUATED = "upstream_value_not_evaluated"
API_CONNECTION_FAILED = "api_connection_failed"
API_NO_DATA = "api_no_data"
SOURCE_NOT_VERIFIED = "source_not_verified"
NOT_IN_SCOPE = "not_in_scope"


class ValueStateError(ValueError):
    """상태와 값이 어긋날 때."""


@dataclass(frozen=True)
class MeasuredValue:
    state: str
    value: Any = None
    unit: str | None = None
    currency: str | None = None
    amount_multiplier: int | None = None
    period: dict | None = None
    reason_code: str | None = None
    source_id: str | None = None
    asof_date: str | None = None
    required_inputs: tuple[str, ...] = field(default=())
    # 화면 표기. 계산값을 바꾸지 않는다 (명세서 §4)
    display: dict | None = None
    # real / user_input / sample / assumption (명세서 §7)
    data_class: str | None = None
    formula: str | None = None

    def __post_init__(self) -> None:
        if self.state not in STATES:
            raise ValueStateError(f"알 수 없는 state: {self.state}")
        if self.state == ACTUAL:
            if self.value is None:
                raise ValueStateError(
                    "state=actual 인데 value 가 없습니다. "
                    "미입력은 NOT_ENTERED 로 표현합니다."
                )
        else:
            if self.value is not None:
                raise ValueStateError(
                    f"state={self.state} 에는 value 를 넣지 않습니다."
                )
            if not self.reason_code:
                raise ValueStateError(
                    f"state={self.state} 에는 reason_code 가 필요합니다."
                )

    @property
    def is_actual(self) -> bool:
        return self.state == ACTUAL

    @property
    def display_label(self) -> str | None:
        return DISPLAY_LABEL[self.state]

    def as_dict(self) -> dict:
        out: dict[str, Any] = {"state": self.state}
        if self.state == ACTUAL:
            out["value"] = self.value
        else:
            out["reason_code"] = self.reason_code
            out["display_label"] = self.display_label
        for key in ("unit", "currency", "amount_multiplier", "period",
                    "source_id", "asof_date", "display", "data_class",
                    "formula"):
            v = getattr(self, key)
            if v is not None:
                out[key] = v
        if self.required_inputs:
            out["required_inputs"] = list(self.required_inputs)
        return out


def actual(value: Any, **kw: Any) -> MeasuredValue:
    return MeasuredValue(ACTUAL, value=value, **kw)


def not_entered(reason_code: str = MISSING_REQUIRED_INPUT,
                required_inputs: tuple[str, ...] = (), **kw) -> MeasuredValue:
    return MeasuredValue(NOT_ENTERED, reason_code=reason_code,
                         required_inputs=required_inputs, **kw)


def not_evaluated(reason_code: str, required_inputs: tuple[str, ...] = (),
                  **kw) -> MeasuredValue:
    return MeasuredValue(NOT_EVALUATED, reason_code=reason_code,
                         required_inputs=required_inputs, **kw)


def not_applicable(reason_code: str = NOT_IN_SCOPE, **kw) -> MeasuredValue:
    return MeasuredValue(NOT_APPLICABLE, reason_code=reason_code, **kw)


def fetch_failed(reason_code: str = API_CONNECTION_FAILED, **kw) -> MeasuredValue:
    return MeasuredValue(FETCH_FAILED, reason_code=reason_code, **kw)


def combine(inputs: list[MeasuredValue], reason_code: str = UPSTREAM_NOT_EVALUATED):
    """입력 중 actual 이 아닌 것이 있으면 결과는 not_evaluated 다.

    부분 합산으로 낙관적 값을 만들지 않는다 (rules/README.md §1.3).
    호출부는 반환값이 None 일 때만 계산을 진행한다.
    """
    bad = [v for v in inputs if not v.is_actual]
    if not bad:
        return None
    if all(v.state == NOT_APPLICABLE for v in bad) and len(bad) == len(inputs):
        return not_applicable()
    return not_evaluated(reason_code)
