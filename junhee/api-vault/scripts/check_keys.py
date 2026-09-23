"""키 설정 현황 점검 — 프로젝트 무관 공통 스크립트.

실행:
    python scripts/check_keys.py

하는 일:
    1) credentials/.env 를 읽어 어떤 키가 채워졌는지 표시
    2) registry/api_registry.csv 의 상태별 건수 요약
    3) 아직 값이 없는 항목 목록 출력

키 값 자체는 절대 출력하지 않는다. 길이와 앞 4자리만 보여준다.
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import api_keys  # noqa: E402

VAULT = Path(__file__).resolve().parent.parent
REGISTRY = VAULT / "registry" / "api_registry.csv"
ENV_FILE = VAULT / "credentials" / ".env"


def mask(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * (len(value) - 4)}  (길이 {len(value)})"


def main() -> int:
    print("=" * 60)
    print("API 키 설정 현황")
    print("=" * 60)

    if not ENV_FILE.is_file():
        print(f"\n[!] {ENV_FILE} 가 없습니다.")
        print("    credentials/.env.example 을 .env 로 복사한 뒤 키를 입력하세요.\n")

    api_keys.load()
    ok = api_keys.available()
    no = api_keys.missing()

    print(f"\n설정됨 {len(ok)}건")
    for name in ok:
        print(f"  [O] {name:<28} {mask(api_keys.get_key(name) or '')}")

    print(f"\n미설정 {len(no)}건")
    for name in no:
        print(f"  [ ] {name}")

    if REGISTRY.is_file():
        with REGISTRY.open(encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        counts = Counter(r["status"] for r in rows)
        print(f"\n대장(api_registry.csv) 총 {len(rows)}건")
        for status, n in counts.most_common():
            print(f"  {status:<10} {n}건")

        todo = [r for r in rows if r["status"] == "미신청"]
        if todo:
            print(f"\n아직 신청하지 않은 API {len(todo)}건")
            for r in todo:
                print(f"  - [{r['provider']}] {r['api_name']}")
    else:
        print(f"\n[!] {REGISTRY} 를 찾을 수 없습니다.")

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
