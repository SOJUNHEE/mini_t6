"""API_KEYS_FORM.txt 를 읽어 credentials/.env 를 만든다.

실행:
    python scripts/build_env.py

입력표에서 다음 두 줄 쌍을 찾아 환경변수로 변환한다.

    [변수] ECOS_API_KEY
    ...
    [키] = 실제키값

값이 비어 있는 항목은 .env 에 주석으로만 남기고 건너뛴다.
기존 .env 가 있으면 .env.bak 으로 백업한 뒤 새로 쓴다.
"""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
FORM = VAULT / "API_KEYS_FORM.txt"
ENV = VAULT / "credentials" / ".env"

VAR_RE = re.compile(r"^\s*\[변수\]\s*([A-Z0-9_]+)\s*$")
KEY_RE = re.compile(r"^\s*\[키\]\s*=\s*(.*)$")


def parse_form(path: Path) -> list[tuple[str, str]]:
    """(변수명, 값) 목록을 입력표에 나온 순서대로 반환한다."""
    pairs: list[tuple[str, str]] = []
    current: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        m = VAR_RE.match(raw)
        if m:
            current = m.group(1)
            continue
        m = KEY_RE.match(raw)
        if m and current:
            value = m.group(1).strip().strip('"').strip("'")
            pairs.append((current, value))
            current = None
    return pairs


def main() -> int:
    if not FORM.is_file():
        print(f"[!] {FORM} 를 찾을 수 없습니다.")
        return 1

    pairs = parse_form(FORM)
    if not pairs:
        print("[!] 입력표에서 [변수] / [키] 쌍을 찾지 못했습니다.")
        print("    [변수] 와 [키] 줄의 형식을 바꾸지 않았는지 확인하세요.")
        return 1

    filled = [(n, v) for n, v in pairs if v]
    empty = [n for n, v in pairs if not v]

    ENV.parent.mkdir(parents=True, exist_ok=True)
    if ENV.exists():
        backup = ENV.parent / ".env.bak"
        shutil.copy2(ENV, backup)
        print(f"[i] 기존 .env 를 {backup.name} 으로 백업했습니다.")

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# 이 파일은 API_KEYS_FORM.txt 에서 자동 생성되었습니다.",
        "# 직접 고치지 말고 입력표를 수정한 뒤 다시 생성하세요.",
        f"#   python scripts/build_env.py      (생성 시각 {stamp})",
        "",
    ]
    for name, value in filled:
        lines.append(f"{name}={value}")
    if empty:
        lines += ["", "# --- 아직 값이 없는 항목 ---"]
        lines += [f"# {name}=" for name in empty]
    lines.append("")

    ENV.write_text("\n".join(lines), encoding="utf-8")

    print(f"[O] {ENV} 생성 완료")
    print(f"    입력됨 {len(filled)}건 / 비어 있음 {len(empty)}건")
    for name, _ in filled:
        print(f"      - {name}")
    if empty:
        print("    비어 있는 항목:")
        for name in empty:
            print(f"      - {name}")
    print("\n    확인:  python scripts/check_keys.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
