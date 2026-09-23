"""헬스체크 (API 계층).

명세서 §8 — 준비 실패 시 이유·재시도 경로를 표시한다.
명세서 §10 — 키 값을 응답·로그에 넣지 않는다. 이름과 건수만 보고한다.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from fastapi import APIRouter

from axport import __version__
from axport.config.settings import ConfigError, get_settings

router = APIRouter(tags=["health"])


def _api_vault_status(settings) -> dict:
    """api-vault 를 참조만 해서 상태를 본다. 키 값은 읽어도 반환하지 않는다."""
    try:
        vault = settings.resolve_path("storage.api_vault_dir")
    except ConfigError as exc:
        return {"reachable": False, "reason": str(exc)}

    if not vault.is_dir():
        return {"reachable": False, "reason": f"api-vault 폴더 없음: {vault}"}

    scripts = vault / "scripts"
    if not (scripts / "api_keys.py").is_file():
        return {"reachable": False, "reason": "api_keys.py 없음"}

    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    try:
        import api_keys  # noqa: PLC0415 — 런타임에 경로가 정해진다
    except Exception as exc:  # noqa: BLE001
        return {"reachable": False, "reason": f"{type(exc).__name__}"}

    # 이름과 건수만. 값은 절대 반환하지 않는다.
    return {
        "reachable": True,
        "keys_configured_count": len(api_keys.available()),
        "keys_missing_count": len(api_keys.missing()),
        "registry_present": (vault / "registry" / "api_registry.csv").is_file(),
        "manifest_present": (
            vault / "reference_data" / "MANIFEST.csv"
        ).is_file(),
    }


@router.get("/health")
def health() -> dict:
    """서버·설정·api-vault 참조 상태를 보고한다."""
    checks: dict[str, object] = {}
    status = "ok"

    try:
        settings = get_settings()
    except ConfigError as exc:
        return {
            "status": "error",
            "app_version": __version__,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "checks": {"config": {"loaded": False, "reason": str(exc)}},
        }

    undecided = settings.undecided_paths()
    checks["config"] = {
        "loaded": True,
        "source": str(settings.source.name),
        "config_version": settings.get("config_version"),
        "undecided_count": len(undecided),
    }

    checks["runtime"] = {
        "env": settings.get("runtime.env"),
        "demo_mode": settings.get("features.demo_mode"),
        "display_timezone": settings.get("locale.display_timezone"),
        "event_time_storage": settings.get("locale.event_time_storage"),
    }

    checks["versions"] = {
        "template_version": settings.get("versions.template_version"),
        "rule_set_version": settings.get("versions.rule_set_version") or None,
        "calc_engine_version": settings.get("versions.calc_engine_version") or None,
        "rule_set_usable_in_production": settings.get(
            "versions.rule_set_usable_in_production"
        ),
    }

    storage: dict[str, bool] = {}
    for key in ("uploads_dir", "reports_dir", "cache_dir",
                "reference_raw_dir", "reference_processed_dir",
                "samples_dir", "rules_dir"):
        try:
            storage[key] = settings.resolve_path(f"storage.{key}").is_dir()
        except ConfigError:
            storage[key] = False
    checks["storage"] = storage
    if not all(storage.values()):
        status = "degraded"

    vault = _api_vault_status(settings)
    checks["api_vault"] = vault
    if not vault.get("reachable"):
        status = "degraded"

    # 아직 만들지 않은 계층은 그대로 보고한다. 되는 것처럼 쓰지 않는다.
    checks["features"] = {
        name: settings.get(f"features.{name}")
        for name in ("upload", "evaluation", "reports", "ai_explain", "auth")
    }

    return {
        "status": status,
        "app_version": __version__,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }


@router.get("/health/config/undecided")
def undecided_settings() -> dict:
    """미정 설정 목록. 명세서 §2 항목이 비어 있는지 확인용."""
    settings = get_settings()
    paths = settings.undecided_paths()
    return {"count": len(paths), "paths": paths}
