"""화면 제공 — 홈(/) 과 앱(/app) (명세서 §8, §13-5, §13-7).

홈과 앱은 별개 시안이며 화면 상태를 분리한다. 공통 토큰(tokens.css)만 공유한다.

이 계층은 파일을 내려주기만 한다. 판정·계산을 하지 않는다 (명세서 §11).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from axport.config.settings import PROJECT_ROOT

WEB_DIR = PROJECT_ROOT / "web"
STATIC_DIR = WEB_DIR

router = APIRouter(tags=["pages"])


@router.get("/", include_in_schema=False)
def home_page() -> FileResponse:
    """홈 화면 — 네이비 히어로·3D·스크롤 이후 흰 배경 (명세서 §1-2~5)."""
    index = WEB_DIR / "home" / "index.html"
    if not index.is_file():
        raise HTTPException(
            status_code=503,
            detail={"code": "web_not_built",
                    "message": f"홈 화면 파일이 없습니다: {index}"},
        )
    return FileResponse(index, media_type="text/html; charset=utf-8",
                        headers={"Cache-Control": "no-store"})


@router.get("/app", include_in_schema=False)
def app_shell() -> FileResponse:
    """대시보드 앱 셸."""
    index = WEB_DIR / "index.html"
    if not index.is_file():
        raise HTTPException(
            status_code=503,
            detail={"code": "web_not_built",
                    "message": f"화면 파일이 없습니다: {index}"},
        )
    # 개발 중에는 캐시하지 않는다
    return FileResponse(index, media_type="text/html; charset=utf-8",
                        headers={"Cache-Control": "no-store"})
