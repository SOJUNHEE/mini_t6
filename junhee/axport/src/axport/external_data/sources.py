"""소스 게이트 — 지표 계산에 쓸 수 있는 소스를 제한한다 (명세서 §7, §13-6).

규칙
    `api_registry.csv` 의 verified 가 '검증완료' 인 API 만 **지표 값 계산**에 쓴다.
    그 밖의 소스는 근거 인벤토리로 **표시만** 한다. 값을 환산하지 않는다.
    미검증 소스로 화면을 채우지 않는다.

MANIFEST 파일 자료는 현재 검증완료가 0건이다(미검증 / 원문대조 필요 등).
따라서 파일은 인벤토리로만 노출하고, 어떤 지표도 파일에서 계산하지 않는다.
이 상태는 MANIFEST 의 verified 가 바뀌면 자동으로 따라온다.

데이터 구분 (명세서 §7)
    real        검증된 외부 실제 자료
    user_input  기업이 업로드한 값
    sample      시연용 가상 자료
    assumption  가정값
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from axport.external_data import registry as reg

REAL = "real"
USER_INPUT = "user_input"
SAMPLE = "sample"
ASSUMPTION = "assumption"

DATA_CLASS_LABEL = {
    REAL: "실제 자료",
    USER_INPUT: "사용자 입력",
    SAMPLE: "샘플 자료",
    ASSUMPTION: "가정값",
}

VERIFIED_OK = "검증완료"


@dataclass
class SourceGate:
    """어떤 소스를 계산에 쓸 수 있는지 판단한다."""

    registry_rows: list[dict]
    manifest_rows: list[dict]

    @classmethod
    def load(cls, registry_path: Path, manifest_path: Path) -> SourceGate:
        return cls(reg.load_registry(registry_path),
                   reg.load_manifest(manifest_path))

    # ── API ───────────────────────────────────────────────────────────
    def api_row(self, api_name: str) -> dict | None:
        return next((r for r in self.registry_rows
                     if api_name in (r.get("api_name") or "")), None)

    def api_verified(self, api_name: str) -> str:
        row = self.api_row(api_name)
        if row is None:
            return "대장에 없음"
        raw = (row.get("verified") or "").strip()
        return VERIFIED_OK if raw.startswith(VERIFIED_OK) else (raw or "미검증")

    def may_compute_from_api(self, api_name: str) -> bool:
        """이 API 값으로 지표를 계산해도 되는가."""
        return self.api_verified(api_name) == VERIFIED_OK

    def verified_apis(self) -> list[dict]:
        out = []
        for r in self.registry_rows:
            raw = (r.get("verified") or "").strip()
            if raw.startswith(VERIFIED_OK):
                out.append({
                    "api_name": r.get("api_name"),
                    "provider": r.get("provider"),
                    "env_var": r.get("env_var") or None,
                    "verified": raw,
                    "expires_date": r.get("expires_date") or None,
                    "daily_limit": r.get("daily_limit") or None,
                    "doc_url": r.get("doc_url"),
                })
        return out

    # ── 파일 (MANIFEST) ───────────────────────────────────────────────
    def file_inventory(self) -> list[dict]:
        """근거 인벤토리. 값을 계산에 쓰지 않는다."""
        out = []
        for r in self.manifest_rows:
            verified_raw = (r.get("verified") or "").strip()
            out.append({
                "path": r.get("path"),
                "source": r.get("source"),
                "asof": r.get("asof") or None,
                "effective": r.get("effective") or None,
                "collected": r.get("collected") or None,
                "sha256": (r.get("sha256") or "")[:16] + "…"
                          if r.get("sha256") else None,
                "bytes": r.get("bytes") or None,
                "license": r.get("license"),
                "verified": verified_raw or "미검증",
                "usable_for_metrics": verified_raw.startswith(VERIFIED_OK),
                "data_class": REAL,
            })
        return out

    def files_usable_for_metrics(self) -> list[dict]:
        return [f for f in self.file_inventory() if f["usable_for_metrics"]]

    # ── 요약 ──────────────────────────────────────────────────────────
    def scope(self) -> dict:
        """이번 분석이 실제로 사용할 수 있는 범위 (명세서 §13-6)."""
        files = self.file_inventory()
        return {
            "verified_apis": self.verified_apis(),
            "verified_api_count": len(self.verified_apis()),
            "file_total": len(files),
            "file_usable_for_metrics": len(
                [f for f in files if f["usable_for_metrics"]]),
            "note": "verified 가 '검증완료' 인 API 만 지표 계산에 사용한다. "
                    "그 밖의 소스는 근거 인벤토리로 표시만 한다.",
        }
