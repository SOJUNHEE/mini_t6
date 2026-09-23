"""평가 실행·보고서·AI 설명 API (명세서 §11).

HTTP 입출력만 담당한다. 계산·판정은 rules_engine/·metrics/ 가 하고,
보고서는 저장된 평가 실행을 그대로 옮긴다. 여기서 재계산하지 않는다.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import FileResponse

from axport.ai_explain import service as ai
from axport.config.settings import get_settings
from axport.reports import builder
from axport.upload_validation import limits as L
from axport.upload_validation import pipeline as P

router = APIRouter(tags=["evaluations"])


def _ctx():
    try:
        return P.build_context(get_settings())
    except (P.StageBlocked, L.UploadRejected) as exc:
        raise HTTPException(status_code=503, detail=exc.as_dict()) from exc


def _load_run(ctx, run_id: str):
    try:
        return P.get_run(ctx, run_id)
    except P.StageBlocked as exc:
        raise HTTPException(status_code=404, detail=exc.as_dict()) from exc


@router.get("/evaluations/{run_id}", summary="평가 실행 조회 (화면·보고서 공용)")
def get_evaluation(run_id: str) -> dict:
    _, run = _load_run(_ctx(), run_id)
    return run


@router.get("/evaluations/{run_id}/tabs/{tab_id}",
            summary="탭 상세 — 5구성 (평가 대상·결과·표·근거·미확인)")
def get_tab(run_id: str, tab_id: str) -> dict:
    _, run = _load_run(_ctx(), run_id)
    detail = run.get("tab_details", {}).get(tab_id)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "tab_not_found",
                    "message": f"탭 상세가 없습니다: {tab_id}",
                    "detail": {"available": list(run.get("tab_details", {}))}},
        )
    return {"run_id": run_id, **detail}


@router.get("/uploads/{upload_id}/runs", summary="이 업로드의 평가 실행 목록")
def list_runs(upload_id: str) -> dict:
    ctx = _ctx()
    try:
        return P.list_runs(ctx, upload_id)
    except P.StageBlocked as exc:
        raise HTTPException(status_code=404, detail=exc.as_dict()) from exc


# ── 보고서 ────────────────────────────────────────────────────────────
@router.post("/reports", summary="보고서 생성 — 저장된 평가 실행을 그대로 옮긴다")
def create_report(run_id: str = Body(..., embed=True)) -> dict:
    ctx = _ctx()
    _, run = _load_run(ctx, run_id)
    report = builder.build(run)
    saved = builder.save(ctx.settings.resolve_path("storage.reports_dir"),
                         run, report)
    return {**saved, "report": report}


@router.get("/reports/{report_id}", summary="보고서 조회")
def get_report(report_id: str) -> dict:
    ctx = _ctx()
    report = builder.load(
        ctx.settings.resolve_path("storage.reports_dir"), report_id)
    if report is None:
        raise HTTPException(status_code=404,
                            detail={"code": "report_not_found",
                                    "message": f"보고서가 없습니다: {report_id}"})
    return report


@router.get("/reports/{report_id}/download.csv",
            summary="보고서 CSV — 수식 주입 방어 적용")
def download_report_csv(report_id: str) -> FileResponse:
    ctx = _ctx()
    path = builder.csv_path(
        ctx.settings.resolve_path("storage.reports_dir"), report_id)
    if path is None:
        raise HTTPException(status_code=404,
                            detail={"code": "report_not_found",
                                    "message": f"보고서 CSV 가 없습니다: {report_id}"})
    return FileResponse(
        path, media_type="text/csv; charset=utf-8",
        filename=f"{report_id}.csv",
        headers={"Cache-Control": "no-store"},
    )


# ── AI 설명 ───────────────────────────────────────────────────────────
@router.post("/ai/explain", summary="AI 설명 — 결과 설명만. 수치를 만들지 않는다")
def explain(run_id: str = Body(..., embed=True),
            dry_run: bool = Query(True,
                                  description="true 면 전송 대상만 미리 본다")) -> dict:
    ctx = _ctx()
    _, run = _load_run(ctx, run_id)
    return ai.explain(run, ctx.settings, dry_run=dry_run)


@router.get("/ai/policy", summary="AI 전송 정책·상한 확인")
def ai_policy() -> dict:
    settings = get_settings()
    policy = ai.load_policy(settings)
    return {
        "policy": policy.as_dict(),
        "always_denied_fields": list(ai.ALWAYS_DENY),
        "note": "허용목록에 없는 항목은 전송하지 않는다. "
                "제외목록은 허용목록보다 우선한다 (명세서 §10).",
    }
