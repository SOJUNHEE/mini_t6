"""홈 화면(/) — 명세서 §1-2~5, §8, §13-7.

브라우저 렌더링(3D 회전·스크롤·로딩 오버레이 동작)은 자동화하지 않았다.
여기서는 제공 여부와 구조·규칙만 검사한다.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from axport.main import create_app

WEB = Path(__file__).resolve().parents[1] / "web"
client = TestClient(create_app())
HTML = (WEB / "home" / "index.html").read_text(encoding="utf-8")
CSS = (WEB / "css" / "home.css").read_text(encoding="utf-8")
JS = (WEB / "js" / "home.js").read_text(encoding="utf-8")
JS3D = (WEB / "js" / "home-3d.js").read_text(encoding="utf-8")


def test_home_and_assets_served():
    assert client.get("/").status_code == 200
    for p in ("/static/css/home.css", "/static/js/home.js", "/static/js/home-3d.js"):
        assert client.get(p).status_code == 200, p


def test_app_untouched_by_home():
    """홈은 앱 파일을 수정하지 않고, 앱은 홈 파일을 불러오지 않는다."""
    app_html = (WEB / "index.html").read_text(encoding="utf-8")
    assert "home.css" not in app_html and "home.js" not in app_html
    for f in ("app.js", "desktop.js", "window-manager.js", "bookmark-tabs.js"):
        assert "home" not in (WEB / "js" / f).read_text(encoding="utf-8").lower() \
            or "home" not in re.findall(r'from\s+"\./([\w-]+)\.js"', (WEB / "js" / f).read_text(encoding="utf-8"))


def test_navy_hero_and_3d_stage():
    assert 'class="hero"' in HTML
    assert "var(--navy-900)" in CSS.split(".hero {")[1].split("}")[0]
    assert 'id="hero-stage"' in HTML
    assert "transform-style: preserve-3d" in CSS


def test_static_fallback_exists_and_3d_is_separate_module():
    """3D 로드 실패 시 정적 대체 화면으로 진입 가능 (명세서 §8)."""
    assert 'id="hero-fallback"' in HTML
    assert 'import("./home-3d.js")' in JS         # 동적 import → 실패 격리
    assert "catch" in JS.split("async function mount3d")[1].split("}")[0] or "catch (err)" in JS
    assert "supports3d" in JS3D
    assert "정적 화면" in JS


def test_scroll_section_white_and_formal():
    assert 'id="intro"' in HTML and 'id="flow"' in HTML and 'id="principles"' in HTML
    assert "background: var(--surface-0)" in CSS.split(".content {")[1].split("}")[0]


def test_enter_button_top_right():
    assert 'id="enter-app-top"' in HTML
    top = CSS.split(".hometop__enter")[1].split("}")[0]
    assert "margin-left: auto" in top     # 우측 정렬


def test_loading_tied_to_real_readiness_no_fixed_delay():
    assert 'fetch("/health"' in JS
    assert "setTimeout" not in JS         # 고정 대기시간 없음
    assert 'window.location.assign("/app")' in JS
    assert 'id="loader-retry"' in HTML    # 재시도 경로
    assert "다시 시도" in HTML
    assert "loaderChecks.append(checkRow(" in JS   # 실패 이유 표시


def test_home_uses_shared_tokens_only():
    assert "/static/css/tokens.css" in HTML
    assert "app.css" not in HTML
    # 홈 전용 색을 새로 정의하지 않고 토큰을 쓴다
    assert "--navy-" in CSS and "#0d1b33" not in CSS


def test_button_height_rule_kept_on_home():
    """design.md — 버튼 40px 이상. 홈 큰 버튼은 48px."""
    assert "min-height: 48px" in CSS.split(".btn--lg")[1].split("}")[0]


def test_no_external_assets():
    assert "https://" not in HTML.replace('href="/docs"', "")
    assert "http://" not in HTML


def test_reduced_motion_respected():
    assert "prefers-reduced-motion" in CSS
    assert "prefers-reduced-motion" in JS


def test_demo_environment_notice_on_home():
    assert "시연 데이터 환경" in HTML
    assert "실제 기업 자료를 넣지 마세요" in HTML
