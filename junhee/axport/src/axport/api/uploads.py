"""업로드·분석 API (명세서 §11).

이 계층은 HTTP 입출력만 담당한다. 검증·매핑·판정·계산 로직은
upload_validation/ 과 rules_engine/ 에 있고 여기서는 호출만 한다.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, File, HTTPException, UploadFile

from axport.config.settings import get_settings
from axport.upload_validation import limits as L
from axport.upload_validation import pipeline as P
from axport.rules_engine import subject as S
from axport.upload_validation import storage

router = APIRouter(prefix="/uploads", tags=["uploads"])


def _ctx():
    try:
        return P.build_context(get_settings())
    except P.StageBlocked as exc:
        raise HTTPException(status_code=503, detail=exc.as_dict()) from exc
    except L.UploadRejected as exc:
        raise HTTPException(status_code=503, detail=exc.as_dict()) from exc


@router.get("", summary="업로드 목록 — 최근 분석·기업 데이터 진입점")
def list_uploads(limit: int = 20) -> dict:
    """보관된 업로드의 메타데이터만 돌려준다. 파일 내용은 읽지 않는다."""
    ctx = _ctx()
    root = ctx.uploads_root
    if not root.is_dir():
        return {"count": 0, "uploads": []}
    metas = []
    for meta_path in root.glob("*/*/*/meta.json"):
        data = storage.load_meta(meta_path.parent)
        if data:
            metas.append(data)
    metas.sort(key=lambda m: m.get("uploaded_at", ""), reverse=True)
    return {"count": len(metas), "uploads": metas[:limit]}


@router.post("", summary="① 업로드 — 제한 검증 후 원본 보존")
async def create_upload(file: UploadFile = File(...)) -> dict:
    ctx = _ctx()
    raw = await file.read()
    try:
        return P.ingest(ctx, raw, file.filename or "unnamed")
    except L.UploadRejected as exc:
        raise HTTPException(status_code=422, detail=exc.as_dict()) from exc


@router.post("/{upload_id}/validate", summary="② 검증 — 오류/경고/정보")
def run_validation(upload_id: str) -> dict:
    ctx = _ctx()
    try:
        return P.run_validation(ctx, upload_id)
    except P.StageBlocked as exc:
        raise HTTPException(status_code=409, detail=exc.as_dict()) from exc
    except L.UploadRejected as exc:
        raise HTTPException(status_code=422, detail=exc.as_dict()) from exc


@router.post("/{upload_id}/mapping", summary="③ 매핑 후보 생성 (확정하지 않음)")
def propose_mapping(upload_id: str) -> dict:
    ctx = _ctx()
    try:
        return P.run_mapping(ctx, upload_id)
    except P.StageBlocked as exc:
        raise HTTPException(status_code=409, detail=exc.as_dict()) from exc


@router.post("/{upload_id}/mapping/confirm", summary="③ 매핑 사용자 확인")
def confirm_mapping(upload_id: str, decisions: dict = Body(...)) -> dict:
    ctx = _ctx()
    try:
        return P.confirm_mapping(ctx, upload_id, decisions)
    except P.StageBlocked as exc:
        raise HTTPException(status_code=409, detail=exc.as_dict()) from exc


@router.get("/{upload_id}/subjects", summary="④ 평가 대상 후보 (평가 단위)")
def list_subjects(upload_id: str) -> dict:
    ctx = _ctx()
    try:
        return P.list_subjects(ctx, upload_id)
    except P.StageBlocked as exc:
        raise HTTPException(status_code=409, detail=exc.as_dict()) from exc


@router.post("/{upload_id}/analyze",
             summary="⑤ 분석 — 평가 실행을 만들어 저장한다")
def analyze(upload_id: str, body: dict = Body(...)) -> dict:
    """filters 를 바꾸면 입력이 바뀐 것이므로 새 run_id 가 나온다.

    body 예:
      {"subject_id": "...", "filters": {"analysis_period":
       {"start": "2026-01", "end": "2026-08"}}}
    """
    ctx = _ctx()
    subject_id = body.get("subject_id")
    if not subject_id:
        raise HTTPException(status_code=422,
                            detail={"code": "subject_id_required",
                                    "message": "subject_id 가 필요합니다."})
    filters = body.get("filters") or {}
    try:
        return P.analyze(ctx, upload_id, subject_id, filters=filters)
    except P.StageBlocked as exc:
        raise HTTPException(status_code=409, detail=exc.as_dict()) from exc
    except S.SubjectError as exc:
        raise HTTPException(status_code=404,
                            detail={"code": "subject_not_found",
                                    "message": str(exc)}) from exc
