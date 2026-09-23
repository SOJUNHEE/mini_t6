"""대장 조회 — api_registry.csv 의 status·verified 를 읽는다 (명세서 §7).

api-vault 는 **읽기만** 한다. 수정하지 않는다.
키 값은 읽지 않는다. 이 모듈은 대장 메타데이터만 다룬다.
"""

from __future__ import annotations

import csv
from pathlib import Path

VERIFIED_OK_PREFIX = "검증완료"


def load_registry(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def load_manifest(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _normalize_verified(raw: str) -> str:
    raw = (raw or "").strip()
    if raw.startswith(VERIFIED_OK_PREFIX):
        return "검증완료"
    return raw or "미검증"


def source_status(registry_path: Path, manifest_path: Path,
                  wanted: dict[str, tuple[str, ...]]) -> dict[str, list[dict]]:
    """영역별로 필요한 소스의 상태를 돌려준다.

    wanted: {영역코드: (api_name 부분문자열, ...)}
    """
    rows = load_registry(registry_path)
    manifest = {r.get("path", ""): r for r in load_manifest(manifest_path)}

    out: dict[str, list[dict]] = {}
    for area, names in wanted.items():
        entries: list[dict] = []
        for needle in names:
            match = next(
                (r for r in rows if needle in (r.get("api_name") or "")), None
            )
            if match is None:
                entries.append({
                    "api_name": needle,
                    "status": "대장에 없음",
                    "verified": "미검증",
                    "kind": "unknown",
                    "note": "api_registry.csv 에서 찾지 못했습니다.",
                })
                continue

            kind = "file" if match["status"] in ("다운로드완료", "미다운로드") else "api"
            verified = _normalize_verified(match.get("verified", ""))

            # 파일 자료는 MANIFEST 의 검증 상태가 더 구체적이다
            if kind == "file":
                for mpath, mrow in manifest.items():
                    if needle.split("_")[-1] in mpath or needle in mpath:
                        verified = _normalize_verified(mrow.get("verified", ""))
                        break

            entries.append({
                "api_name": match.get("api_name"),
                "provider": match.get("provider"),
                "status": match.get("status"),
                "verified": verified,
                "kind": kind,
                "env_var": match.get("env_var") or None,
                "expires_date": match.get("expires_date") or None,
                "note": match.get("note"),
            })
        out[area] = entries
    return out


def rule_readiness(strategic_files_present: bool = False) -> list[dict]:
    """판정 규칙 사용 가능 여부.

    별표2의2(상황허가 대상품목)·별표6 이 미확보이고 별표1~4 가
    '원문대조 필요' 이므로 운영 판정에 사용할 수 없다 (rules/README.md §6).
    """
    return [{
        "rule_set_id": "export_control",
        "version": None,
        "review_status": "source_missing",
        "reason_code": "rule_source_missing",
        "source_files": [
            "전략물자수출입고시 별표2의2 상황허가 대상품목 (미다운로드)",
            "전략물자수출입고시 별표6 전략물자 수출지역 구분 (미다운로드)",
            "별표1~4 (다운로드완료, 원문대조 필요)",
        ],
        "usable_in_production": False,
    }]
