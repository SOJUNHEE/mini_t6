"""평가 실행 — 검증된 범위에서 실제 지표를 계산하고 3층 결과를 만든다.

범위 (명세서 §13-6)
    registry verified == '검증완료' 인 API 만 지표 계산에 쓴다.
    MANIFEST 파일은 근거 인벤토리로만 노출한다 (현재 검증완료 0건).

한 번 만든 평가 실행은 고치지 않는다. 필터가 바뀌면 새 실행이다.
화면과 보고서는 이 함수의 결과 하나를 공유한다 (명세서 §11).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from axport.config.settings import Settings
from axport.external_data import registry as reg
from axport.external_data.cache import Cache
from axport.external_data.providers import customs_trade as ct
from axport.external_data.sources import SourceGate
from axport.metrics import market, trade_history
from axport.rules_engine import detail as D
from axport.rules_engine import result as R
from axport.rules_engine import run_store
from axport.rules_engine import values as V
from axport.rules_engine.subject import Subject
from axport.upload_validation.reader import WorkbookData
from axport.upload_validation.validate import ValidationReport

GATE_NOTE = ("지표 계산에는 registry 의 verified 가 '검증완료' 인 소스만 "
             "사용했습니다 (명세서 §13-6).")


class KeyUnavailable(RuntimeError):
    pass


def _service_key(settings: Settings, env_var: str) -> str:
    """api-vault 의 require_key 로만 키를 읽는다 (명세서 §10).

    키 값을 로그·반환값·예외 메시지에 넣지 않는다.
    """
    import sys

    vault_scripts = settings.resolve_path("storage.api_vault_dir") / "scripts"
    if str(vault_scripts) not in sys.path:
        sys.path.insert(0, str(vault_scripts))
    import api_keys

    return api_keys.require_key(env_var)


def _analysis_period(subject: Subject, filters: dict) -> dict | None:
    """필터로 받은 분석 기간. 없으면 None (임의로 만들지 않는다)."""
    period = filters.get("analysis_period")
    if not period:
        return None
    return {"start": period.get("start"), "end": period.get("end")}


def _yymm(value: str | None) -> str | None:
    if not value:
        return None
    digits = value.replace("-", "")
    return digits[:6] if len(digits) >= 6 else None


def _fetch_market(subject: Subject, filters: dict, settings: Settings,
                  gate: SourceGate, cache: Cache) -> ct.FetchResult | None:
    """검증완료 API 조회. 게이트를 통과하지 못하면 None."""
    if not gate.may_compute_from_api(ct.API_NAME):
        return None
    period = _analysis_period(subject, filters)
    start = _yymm(period.get("start") if period else None)
    end = _yymm(period.get("end") if period else None)
    if not (start and end):
        return ct.FetchResult(
            fetch_result=ct.NO_DATA, error_code="period_missing",
            error_message="분석 기간(analysis_period)이 지정되지 않았습니다. "
                          "기간을 임의로 정하지 않습니다.",
            verified=gate.api_verified(ct.API_NAME))
    if not subject.destination_country_code:
        return ct.FetchResult(
            fetch_result=ct.NO_DATA, error_code="destination_missing",
            error_message="목적국코드가 없어 조회할 수 없습니다.",
            verified=gate.api_verified(ct.API_NAME))

    try:
        service_key = _service_key(settings, ct.ENV_VAR)
    except Exception as exc:  # noqa: BLE001
        return ct.FetchResult(
            fetch_result=ct.NO_PERMISSION, error_code="key_unavailable",
            error_message=f"{ct.ENV_VAR} 를 읽을 수 없습니다 ({type(exc).__name__}).",
            verified=gate.api_verified(ct.API_NAME))

    return ct.fetch(
        service_key=service_key,
        country_code=subject.destination_country_code,
        start_yymm=start, end_yymm=end,
        hs_code=subject.hs_code,
        cache=cache,
        timeout=int(settings.get("api_limits.request_timeout_seconds", 30)),
        verified=gate.api_verified(ct.API_NAME),
    )


def evaluate(*, data: WorkbookData, subject: Subject,
             validation: ValidationReport, settings: Settings,
             project_root: Path, upload_id: str, upload_sha256: str,
             filters: dict, upload_dir: Path,
             executed_by: dict | None = None) -> dict:
    """평가 실행 하나를 만든다. 저장은 호출부가 한다."""
    registry_path = _resolve(settings, "external_data.registry_path", project_root)
    manifest_path = _resolve(settings, "external_data.manifest_path", project_root)
    gate = SourceGate.load(registry_path, manifest_path)

    max_age = settings.get("external_data.max_age_days_default")
    cache = Cache(
        root=settings.resolve_path("storage.cache_dir"),
        max_age_days=int(max_age) if str(max_age).strip().isdigit() else None,
        enabled=bool(settings.get("external_data.cache_enabled", True)),
    )
    rounding_policy = settings.get("currency.rounding_policy") or None

    # ── 검증완료 API 에서 시장성 지표 ─────────────────────────────────
    fetch = _fetch_market(subject, filters, settings, gate, cache)
    if fetch is None:
        fetch = ct.FetchResult(
            fetch_result=ct.NO_DATA, error_code="source_not_verified",
            error_message=f"{ct.API_NAME} 의 verified 가 '검증완료'가 아닙니다.",
            verified=gate.api_verified(ct.API_NAME))
    market_metrics = market.compute(fetch, rounding_policy=rounding_policy)

    # ── 업로드 실적 지표 (사용자 입력) ────────────────────────────────
    period = _analysis_period(subject, filters)
    history = trade_history.compute(
        data, product_id=subject.product_id,
        destination=subject.destination_country_code,
        period=period, rounding_policy=rounding_policy)

    # ── 3층 결과 ──────────────────────────────────────────────────────
    source_status = reg.source_status(registry_path, manifest_path,
                                      R.AREA_REQUIRED_SOURCES)
    readiness = reg.rule_readiness()
    layer1 = R.build_layer1(readiness)
    layer2 = R.build_layer2(data, subject, settings, source_status)
    layer3 = R.build_layer3(data, validation, subject, readiness, source_status)
    overall = R.apply_gates(layer1, layer3)

    # 시장성 영역에 실제 지표를 붙인다. 점수는 만들지 않는다.
    for area in layer2.areas:
        if area.area_code == R.MARKET and fetch.ok:
            area.metrics = [
                {"metric_id": mid, "label": label, **market_metrics[mid].as_dict()}
                for mid, label in market.METRIC_LABEL.items()
            ]
            area.status = "partial"   # 지표는 있으나 점수는 미승인

    # ── 탭별 상세 (화면·보고서 공용) ──────────────────────────────────
    subject_dict = subject.as_dict()
    area_by_code = {a.area_code: a.as_dict() for a in layer2.areas}
    details = {
        D.TAB_MARKET: D.market_detail(subject_dict, filters, fetch,
                                      market_metrics, gate_note=GATE_NOTE),
        D.TAB_TRADE_HISTORY: D.trade_history_detail(
            subject_dict, filters, history,
            validation_summary=layer3.validation_summary),
        D.TAB_EXPORT_CONTROL: D.export_control_detail(
            subject_dict, filters, layer1.as_dict(), readiness),
    }
    for tab_id, area_code in ((D.TAB_TARIFF_ORIGIN, R.PRICE),
                              (D.TAB_COUNTERPARTY, R.STABILITY),
                              (D.TAB_PROFIT_FX, R.PRICE),
                              (D.TAB_SUPPLY_LOGISTICS, R.LOGISTICS)):
        details[tab_id] = D.unverified_detail(
            tab_id, subject_dict, filters, area_by_code.get(area_code))

    engine = {
        "template_version": settings.get("versions.template_version"),
        "rule_set_version": settings.get("versions.rule_set_version") or None,
        "calc_engine_version": settings.get("versions.calc_engine_version") or None,
        "scoring_config_version":
            settings.get("versions.scoring_config_version") or None,
        "config_version": settings.get("config_version"),
    }
    fingerprint = run_store.input_fingerprint(
        upload_sha256=upload_sha256, subject_id=subject.subject_id,
        filters=filters, engine=engine)

    external_sources = [fetch.as_dict()]

    demo = settings.get("features.demo_mode") in (True, "true", "True")
    run = {
        "run_id": run_store.new_run_id(),
        # 시연 데이터 환경 식별 (명세서 §7, §10). 실제 기업 자료 환경과 구분한다.
        "environment": {
            "demo_mode": demo,
            "label": "시연 데이터 환경" if demo else "실제 자료 환경",
            "storage_scope": "instance/ (시연용 세션 보관, 기업 계정 저장 아님)",
        },
        "run_seq": run_store.next_seq(upload_dir, subject.subject_id),
        "input_fingerprint": fingerprint,
        "upload_id": upload_id,
        "upload_sha256": upload_sha256,
        "company_id": subject.company_id,
        "subject": subject_dict,
        "analysis_mode": subject.analysis_mode,
        "analysis_mode_label": subject.analysis_mode_label,
        "filters": filters,
        "engine": engine,
        "scope": gate.scope(),
        "evidence_inventory": {
            "verified_apis": gate.verified_apis(),
            "files": gate.file_inventory(),
        },
        "external_sources": external_sources,
        "result": {
            "mandatory_review": layer1.as_dict(),
            "business_fitness": layer2.as_dict(),
            "evidence_status": layer3.as_dict(),
            "overall": overall,
        },
        "main_summary": R.build_main_summary(layer1, layer2),
        "tab_details": details,
        "tab_order": list(D.TAB_ORDER),
        "missing_inputs": layer3.missing_inputs,
        "follow_up_actions": _follow_ups(details),
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "executed_by": executed_by or {"actor_type": "user", "user_id": None,
                                       "org_id": None, "role": None},
        "display_timezone": settings.get("locale.display_timezone"),
        "supersedes_run_id": None,
        "superseded_by_run_id": None,
        "new_run_reason": filters.get("_reason") or "user_requested",
    }
    return run


def _follow_ups(details: dict) -> list[dict]:
    out = []
    for tab_id, d in details.items():
        for action in d["open_items"]["next_actions"]:
            out.append({"tab_id": tab_id, "action": action, "blocking": False})
    return out


def _resolve(settings: Settings, key: str, project_root: Path) -> Path:
    raw = Path(settings.get(key, ""))
    return raw if raw.is_absolute() else (project_root / raw).resolve()
