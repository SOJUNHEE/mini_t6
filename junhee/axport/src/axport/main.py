"""AXPORT ASGI 진입점.

현재 범위: 서버 기동과 헬스체크만. 화면·업로드·분석은 아직 없다.

계층 경계 (명세서 §11)
    api/                이 파일과 라우터. HTTP 입출력만 담당한다
    upload_validation/  업로드 검증
    metrics/            지표 계산
    rules_engine/       판정 규칙
    external_data/      외부 데이터 연결
    reports/            보고서
    ai_explain/         AI 설명
    web/                UI·창 관리 (프런트엔드, 별도 폴더)

판정·계산 로직을 api/ 나 web/ 에 넣지 않는다. 화면과 보고서는
동일한 서버 계산 결과를 사용한다.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from axport import __version__
from axport.api import evaluations, health, pages, uploads
from axport.config.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="AXPORT API",
        version=__version__,
        description=(
            "수출적합도 분석 API. 화면은 /app 에서 제공한다. "
            "설정 단일 출처: config/settings.toml"
        ),
    )
    app.include_router(health.router)
    app.include_router(uploads.router)
    app.include_router(evaluations.router)
    app.include_router(pages.router)

    if pages.STATIC_DIR.is_dir():
        app.mount("/static",
                  StaticFiles(directory=pages.STATIC_DIR),
                  name="static")

    # 기동 시 미정 설정 건수를 남긴다. 값을 추측해 채우지 않는다.
    undecided = settings.undecided_paths()
    if undecided:
        import logging

        logging.getLogger("axport").warning(
            "미정 설정 %d건 (명세서 §2 승인 대기): %s",
            len(undecided), ", ".join(undecided),
        )
    return app


app = create_app()
