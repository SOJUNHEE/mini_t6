"""파이프라인 오케스트레이션 — 업로드 → 검증 → 매핑·단위 확인 → 분석.

각 단계는 독립 모듈이다 (명세서 §11). 이 파일은 순서와 진행 조건만 정한다.
단계 산출물은 원본과 분리해 업로드 폴더에 저장한다.

진행 조건
    검증에 error 가 있으면 매핑 단계로 가지 않는다.
    매핑 확인이 끝나지 않으면 분석 단계로 가지 않는다. (§5 — 사용자 확인)
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from axport.config.settings import Settings
from axport.rules_engine import evaluate as E
from axport.rules_engine import run_store
from axport.rules_engine import subject as S
from axport.upload_validation import limits as L
from axport.upload_validation import mapping as M
from axport.upload_validation import reader, storage, validate

STAGE_INGEST = "ingest"
STAGE_VALIDATE = "validate"
STAGE_MAPPING = "mapping"
STAGE_ANALYZE = "analyze"

ARTIFACT_VALIDATION = "validation.json"
ARTIFACT_MAPPING = "mapping.json"
ARTIFACT_SUBJECTS = "subjects.json"


class StageBlocked(Exception):
    def __init__(self, stage: str, code: str, message: str, detail: dict | None = None):
        super().__init__(message)
        self.stage = stage
        self.code = code
        self.message = message
        self.detail = detail or {}

    def as_dict(self) -> dict:
        return {"stage": self.stage, "code": self.code,
                "message": self.message, "detail": self.detail}


@dataclass
class Context:
    settings: Settings
    project_root: Path
    limits: L.Limits

    @property
    def uploads_root(self) -> Path:
        return self.settings.resolve_path("storage.uploads_dir")

    @property
    def registry_path(self) -> Path:
        p = Path(self.settings.get("external_data.registry_path", ""))
        return p if p.is_absolute() else (self.project_root / p).resolve()

    @property
    def manifest_path(self) -> Path:
        p = Path(self.settings.get("external_data.manifest_path", ""))
        return p if p.is_absolute() else (self.project_root / p).resolve()


def build_context(settings: Settings) -> Context:
    from axport.config.settings import PROJECT_ROOT

    if not settings.get("features.upload") in (True, "true", "True"):
        raise StageBlocked(
            STAGE_INGEST, "feature_disabled",
            "업로드 기능이 비활성화되어 있습니다. "
            "config/settings.toml 의 features.upload 를 확인하세요.",
        )
    return Context(settings=settings, project_root=PROJECT_ROOT,
                   limits=L.load_limits(settings))


# ── ① 업로드 ──────────────────────────────────────────────────────────
def ingest(ctx: Context, raw: bytes, declared_name: str) -> dict:
    """제한 검증 → 서버 경로 생성 → 원본 보존."""
    started = time.monotonic()
    uploads_root = ctx.uploads_root
    uploads_root.mkdir(parents=True, exist_ok=True)

    # 크기 검사를 먼저 한다. 파일을 쓰기 전에 거른다.
    if len(raw) > ctx.limits.max_file_bytes:
        raise L.UploadRejected(
            "file_too_large", "파일 크기 제한을 초과했습니다.",
            {"size_bytes": len(raw),
             "max_file_bytes": ctx.limits.max_file_bytes},
        )

    stored = storage.store(raw, declared_name, uploads_root, ctx.project_root)
    source = ctx.project_root / stored.source_path
    try:
        inspection = L.inspect_file(source, declared_name, ctx.limits)
    except L.UploadRejected:
        # 거부된 파일은 남기지 않는다
        for p in sorted(source.parent.rglob("*"), reverse=True):
            p.unlink() if p.is_file() else p.rmdir()
        source.parent.rmdir()
        raise

    return {
        "stage": STAGE_INGEST,
        "upload": stored.as_dict(),
        "inspection": inspection.as_dict(),
        "limits": ctx.limits.as_dict(),
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "note": "저장 경로는 서버가 생성했습니다. 원본 파일명은 표시 정보입니다.",
    }


# ── ② 검증 ────────────────────────────────────────────────────────────
def run_validation(ctx: Context, upload_id: str) -> dict:
    upload_dir = _require_dir(ctx, upload_id)
    started = time.monotonic()
    data = reader.read(upload_dir / storage.SOURCE_FILENAME, ctx.limits)
    report = validate.validate(data)
    elapsed = time.monotonic() - started

    if elapsed > ctx.limits.processing_timeout_seconds:
        raise L.UploadRejected(
            "processing_timeout", "처리시간 제한을 초과했습니다.",
            {"elapsed_seconds": round(elapsed, 2),
             "limit": ctx.limits.processing_timeout_seconds},
        )

    payload = {
        "stage": STAGE_VALIDATE,
        "upload_id": upload_id,
        "template_version_in_file": data.info_sheet_values.get("template_version"),
        "sheets_found": sorted(data.sheets),
        "missing_sheets": data.missing_sheets,
        "extra_sheets": data.extra_sheets,
        "elapsed_ms": int(elapsed * 1000),
        **report.as_dict(),
    }
    storage.write_artifact(upload_dir, ARTIFACT_VALIDATION, payload)
    return payload


# ── ③ 매핑·단위 확인 ──────────────────────────────────────────────────
def run_mapping(ctx: Context, upload_id: str) -> dict:
    upload_dir = _require_dir(ctx, upload_id)
    prior = storage.read_artifact(upload_dir, ARTIFACT_VALIDATION)
    if prior is None:
        raise StageBlocked(STAGE_MAPPING, "validation_not_run",
                           "검증 단계를 먼저 실행해야 합니다.")
    if prior["blocking"]:
        raise StageBlocked(
            STAGE_MAPPING, "validation_has_errors",
            "검증 오류가 남아 있어 매핑 단계로 진행하지 않습니다.",
            {"error_count": prior["counts"]["error"]},
        )

    data = reader.read(upload_dir / storage.SOURCE_FILENAME, ctx.limits)
    report = M.propose(data)
    payload = {"stage": STAGE_MAPPING, "upload_id": upload_id, **report.as_dict()}
    storage.write_artifact(upload_dir, ARTIFACT_MAPPING, payload)
    return payload


def confirm_mapping(ctx: Context, upload_id: str,
                    decisions: dict[str, str | None]) -> dict:
    """사용자 확인 결과를 반영한다. 서버가 임의로 확정하지 않는다."""
    upload_dir = _require_dir(ctx, upload_id)
    prior = storage.read_artifact(upload_dir, ARTIFACT_MAPPING)
    if prior is None:
        raise StageBlocked(STAGE_MAPPING, "mapping_not_proposed",
                           "매핑 후보를 먼저 생성해야 합니다.")
    report = M.apply_confirmation(M.from_dict(prior), decisions)
    payload = {"stage": STAGE_MAPPING, "upload_id": upload_id, **report.as_dict()}
    storage.write_artifact(upload_dir, ARTIFACT_MAPPING, payload)
    return payload


# ── ④ 평가 대상 후보 ──────────────────────────────────────────────────
def list_subjects(ctx: Context, upload_id: str) -> dict:
    upload_dir = _require_dir(ctx, upload_id)
    _require_mapping_confirmed(upload_dir)
    data = reader.read(upload_dir / storage.SOURCE_FILENAME, ctx.limits)
    subjects = S.list_candidates(data)
    payload = {
        "stage": STAGE_ANALYZE,
        "upload_id": upload_id,
        "count": len(subjects),
        "evaluation_unit": "기업 + 제품·모델 + 목적국 + 거래 조건 + 평가 기준일",
        "subjects": [s.as_dict() for s in subjects],
    }
    storage.write_artifact(upload_dir, ARTIFACT_SUBJECTS, payload)
    return payload


# ── ⑤ 분석 → 평가 실행 저장 ───────────────────────────────────────────
def analyze(ctx: Context, upload_id: str, subject_id: str,
            filters: dict | None = None,
            executed_by: dict | None = None) -> dict:
    """평가 실행을 만들어 **저장한** 뒤 돌려준다.

    필터가 바뀌면 입력이 바뀐 것이므로 새 run_id 가 된다. 이전 결과를
    최신처럼 쓰지 않는다 (명세서 §9).
    """
    upload_dir = _require_dir(ctx, upload_id)
    _require_mapping_confirmed(upload_dir)
    if storage.read_artifact(upload_dir, ARTIFACT_VALIDATION) is None:
        raise StageBlocked(STAGE_ANALYZE, "validation_not_run",
                           "검증 단계를 먼저 실행해야 합니다.")

    meta = storage.load_meta(upload_dir) or {}
    data = reader.read(upload_dir / storage.SOURCE_FILENAME, ctx.limits)
    subject = S.select(data, subject_id)
    report = validate.validate(data)

    run = E.evaluate(
        data=data, subject=subject, validation=report,
        settings=ctx.settings, project_root=ctx.project_root,
        upload_id=upload_id, upload_sha256=meta.get("sha256", ""),
        filters=filters or {}, upload_dir=upload_dir,
        executed_by=executed_by,
    )
    return run_store.save(upload_dir, run)


def get_run(ctx: Context, run_id: str) -> tuple[Path, dict]:
    found = run_store.find_anywhere(ctx.uploads_root, run_id)
    if found is None:
        raise StageBlocked(STAGE_ANALYZE, "run_not_found",
                           f"평가 실행을 찾을 수 없습니다: {run_id}")
    return found


def list_runs(ctx: Context, upload_id: str) -> dict:
    upload_dir = _require_dir(ctx, upload_id)
    return {"upload_id": upload_id, "runs": run_store.index(upload_dir)}


# ── 공통 ──────────────────────────────────────────────────────────────
def _require_dir(ctx: Context, upload_id: str) -> Path:
    upload_dir = storage.find(upload_id, ctx.uploads_root)
    if upload_dir is None:
        raise StageBlocked(STAGE_VALIDATE, "upload_not_found",
                           f"업로드를 찾을 수 없습니다: {upload_id}")
    return upload_dir


def _require_mapping_confirmed(upload_dir: Path) -> None:
    payload = storage.read_artifact(upload_dir, ARTIFACT_MAPPING)
    if payload is None:
        raise StageBlocked(STAGE_ANALYZE, "mapping_not_run",
                           "매핑 단계를 먼저 실행해야 합니다.")
    if not payload.get("ready_for_analysis"):
        raise StageBlocked(
            STAGE_ANALYZE, "mapping_needs_confirmation",
            "컬럼 매핑에 사용자 확인이 필요한 항목이 남아 있습니다. "
            "서버가 임의로 확정하지 않습니다. (명세서 §5)",
            {"needs_confirmation_count": payload.get("needs_confirmation_count"),
             "unmapped_count": payload.get("unmapped_count")},
        )
