"""금액·수량 계산 — 계산과 화면 반올림을 분리한다 (명세서 §4).

계산은 Decimal 로 한다. 부동소수 오차를 만들지 않는다.
직렬화는 문자열로 한다. JSON float 로 내보내면 정밀도가 깨진다.

화면 반올림은 계산 결과를 바꾸지 않는다. `display` 블록에만 적용한다.
통화별 정밀도·반올림 정책(`currency.rounding_policy`)은 **미정**이다.
미정인 동안 반올림하지 않고 원값을 그대로 표시하며 그 사실을 표시한다.
임의의 소수점 자리수를 만들지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

POLICY_UNDECIDED = "미정"


class AmountError(ValueError):
    pass


def to_decimal(raw: object) -> Decimal | None:
    """문자열·숫자를 Decimal 로. 변환 불가면 None (0 으로 바꾸지 않는다)."""
    if raw is None:
        return None
    if isinstance(raw, Decimal):
        return raw
    if isinstance(raw, bool):
        return None
    text = str(raw).strip().replace(",", "")
    if text == "":
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def total(values: list[object]) -> Decimal | None:
    """합계. 변환 불가 값이 하나라도 있으면 None 을 돌려준다.

    부분 합산으로 낙관적 값을 만들지 않는다 (rules/README.md §1.3).
    """
    acc = Decimal(0)
    for v in values:
        d = to_decimal(v)
        if d is None:
            return None
        acc += d
    return acc


def share(part: Decimal | None, whole: Decimal | None) -> Decimal | None:
    """비중. 분모가 0 이거나 없으면 None. 0 으로 나누어 채우지 않는다."""
    if part is None or whole is None or whole == 0:
        return None
    return part / whole


@dataclass
class Display:
    """화면 표기. 계산값을 바꾸지 않는다."""

    text: str
    rounding_policy: str
    decimals: int | None
    rounded: bool

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "rounding_policy": self.rounding_policy,
            "decimals": self.decimals,
            "rounded": self.rounded,
        }


def format_for_display(value: Decimal, *, rounding_policy: str | None,
                       thousands: bool = True) -> Display:
    """표시 문자열을 만든다.

    rounding_policy 가 미정이면 반올림하지 않는다. 자리수를 추측하지 않는다.
    """
    if not rounding_policy:
        text = f"{value:,f}" if thousands else f"{value:f}"
        # 불필요한 소수점 0 은 정규화하되 값은 바꾸지 않는다
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return Display(text=text, rounding_policy=POLICY_UNDECIDED,
                       decimals=None, rounded=False)

    # 정책이 생기면 여기서 적용한다. 지금은 정책 문자열을 그대로 기록만 한다.
    raise AmountError(
        f"반올림 정책 '{rounding_policy}' 의 적용 규칙이 아직 구현되지 않았습니다. "
        "currency.rounding_policy 승인 후 구현합니다."
    )


def serialize(value: Decimal | None) -> str | None:
    """JSON 에 넣을 값. float 로 바꾸지 않는다."""
    return None if value is None else format(value, "f")
