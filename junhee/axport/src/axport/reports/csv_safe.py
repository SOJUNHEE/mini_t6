"""CSV·다운로드 표 수식 주입 방어 (명세서 §5, CONTRIBUTING §7).

Excel·Sheets 는 셀이 = + - @ 또는 탭·개행으로 시작하면 수식으로 해석한다.
값을 바꾸지 않고 앞에 작은따옴표를 붙여 텍스트로 고정한다.

숫자는 그대로 둔다. '-1500' 같은 음수는 수식이 아니다. 판별은
'수식으로 해석될 수 있는 문자로 시작하는데 숫자로 파싱되지 않는' 경우만 한다.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

RISKY_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")
GUARD = "'"


def is_numeric(text: str) -> bool:
    try:
        Decimal(text)
        return True
    except InvalidOperation:
        return False


def sanitize(value: object) -> str:
    """셀 하나를 안전한 문자열로 만든다. 값의 의미는 바꾸지 않는다."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    text = str(value)
    if text == "":
        return ""
    # 개행·탭은 셀을 깨뜨린다. 공백으로 치환한다.
    cleaned = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    cleaned = cleaned.replace("\t", " ")
    if cleaned.startswith(RISKY_PREFIXES) and not is_numeric(cleaned):
        return GUARD + cleaned
    if cleaned[:1] in ("=", "@"):
        return GUARD + cleaned
    return cleaned


def sanitize_row(row: list[object]) -> list[str]:
    return [sanitize(v) for v in row]
