"""/app 화면 셸과 정적 자산 검증.

브라우저 동작(드래그·리사이즈)은 여기서 검증하지 않는다. 자동화 브라우저를
도입하지 않았으므로, 그 부분은 수동 확인 대상이며 README 에 그렇게 적는다.

여기서 검증하는 것
    /app 이 응답하고 /static 이 제공되는지
    홈(/)을 만들지 않았는지
    design.md UI 통일성 규칙이 토큰에 고정됐는지
    판정·계산 로직이 화면 JS 에 없는지 (명세서 §11)
    접근성 속성이 들어 있는지 (명세서 §9)
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from axport.main import create_app

WEB = Path(__file__).resolve().parents[1] / "web"
client = TestClient(create_app())


# ── 제공 ──────────────────────────────────────────────────────────────
def test_app_shell_served():
    res = client.get("/app")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "AXPORT 분석 작업공간" in res.text


def test_home_is_separate_page():
    """홈(/)은 앱(/app)과 별개 파일이며 앱 자산을 불러오지 않는다 (명세서 §8)."""
    res = client.get("/")
    assert res.status_code == 200
    assert "AXPORT" in res.text
    assert "/static/css/home.css" in res.text
    assert "/static/js/home.js" in res.text
    assert "app.css" not in res.text and "js/app.js" not in res.text


def test_static_assets_served():
    for path in ("/static/css/tokens.css", "/static/css/app.css",
                 "/static/js/app.js", "/static/js/window-manager.js",
                 "/static/js/bookmark-tabs.js", "/static/js/screens.js",
                 "/static/js/desktop.js", "/static/js/analysis-window.js",
                 "/static/js/api.js"):
        assert client.get(path).status_code == 200, path


def test_uploads_list_endpoint_exists():
    """바탕화면의 '최근 분석'이 쓰는 목록 엔드포인트."""
    res = client.get("/uploads")
    # 업로드 기능이 비활성이면 503 + 사유를 준다. 404 여서는 안 된다.
    assert res.status_code in (200, 503)
    if res.status_code == 503:
        assert res.json()["detail"]["code"] in ("feature_disabled",
                                                "limits_undecided")


# ── 바탕화면 진입점 (명세서 §8) ───────────────────────────────────────
def test_desktop_has_four_entry_points():
    js = (WEB / "js" / "desktop.js").read_text(encoding="utf-8")
    ids = set(re.findall(r'id:\s*"(\w+)"', js))
    assert {"upload", "recent", "company", "reports"} <= ids


def test_empty_desktop_state_exists():
    js = (WEB / "js" / "desktop.js").read_text(encoding="utf-8")
    assert "emptyDesktop" in js
    assert "아직 분석한 자료가 없습니다" in js


# ── 창 관리자 (명세서 §8) ─────────────────────────────────────────────
def test_window_manager_has_required_operations():
    js = (WEB / "js" / "window-manager.js").read_text(encoding="utf-8")
    for name in ("bindTitlebar", "bindResize", "minimize", "restore",
                 "toggleMaximize", "close", "resetLayout", "clamp",
                 "reflowAll", "setGeometry"):
        assert name in js, name


def test_window_min_size_defined():
    css = (WEB / "css" / "tokens.css").read_text(encoding="utf-8")
    m = re.search(r"--win-min-w:\s*(\d+)px", css)
    h = re.search(r"--win-min-h:\s*(\d+)px", css)
    assert m and h
    assert int(m.group(1)) >= 320
    assert int(h.group(1)) >= 240


def test_controls_kept_on_screen():
    """조작부가 화면 밖에 갇히지 않도록 보정한다."""
    js = (WEB / "js" / "window-manager.js").read_text(encoding="utf-8")
    assert "KEEP_VISIBLE_X" in js
    assert "clamp(" in js
    # 화면 크기 변경 시 보정
    assert 'window.addEventListener("resize"' in js
    assert "reflowAll" in js


def test_geometry_persisted_and_storage_failure_tolerated():
    js = (WEB / "js" / "window-manager.js").read_text(encoding="utf-8")
    assert "localStorage.setItem" in js and "localStorage.getItem" in js
    # 저장 실패가 화면을 막지 않아야 한다
    assert js.count("catch") >= 2


def test_duplicate_window_policy_is_single_and_documented():
    js = (WEB / "js" / "window-manager.js").read_text(encoding="utf-8")
    assert "중복 실행 정책" in js
    assert "기존 창을 활성화" in js
    # open() 이 기존 창을 찾으면 새로 만들지 않는다
    body = js.split("open({")[1]
    assert "const existing = this.windows.get(key);" in body
    assert "this.focus(key);" in body


# ── 책갈피 탭 (명세서 §8) ─────────────────────────────────────────────
def test_eight_bookmark_tabs_in_order():
    js = (WEB / "js" / "bookmark-tabs.js").read_text(encoding="utf-8")
    labels = re.findall(r'label:\s*"([^"]+)"', js)
    assert labels == ["종합판정", "수출실적", "시장성", "관세·원산지",
                      "수출규제", "거래처", "수익성·환율", "공급·물류"]


def test_selected_tab_distinguished_beyond_color():
    """선택 탭을 색 외에 형태·텍스트로도 구분한다."""
    css = (WEB / "css" / "app.css").read_text(encoding="utf-8")
    sel = css.split('.bookmark[aria-selected="true"]')[1].split("}")[0]
    # 형태: 왼쪽 띠 굵기·들여쓰기·글꼴 굵기
    assert "border-left-width" in sel
    assert "margin-left" in sel
    assert "font-weight" in sel
    # 텍스트 마커
    assert '.bookmark[aria-selected="true"] .bookmark__mark' in css
    js = (WEB / "js" / "bookmark-tabs.js").read_text(encoding="utf-8")
    assert '"선택됨"' in js      # 스크린리더용 문구


def test_tabs_scroll_when_window_is_short():
    css = (WEB / "css" / "app.css").read_text(encoding="utf-8")
    block = css.split(".bookmarks {")[1].split("}")[0]
    assert "overflow-y: auto" in block


def test_tabs_keyboard_navigation():
    js = (WEB / "js" / "bookmark-tabs.js").read_text(encoding="utf-8")
    for key in ("ArrowDown", "ArrowUp", "Home", "End"):
        assert key in js
    assert 'role", "tablist"' in js
    assert "aria-selected" in js


def test_context_preserved_across_tabs():
    """탭 전환 시 기업·제품·목적국·평가 실행이 유지된다."""
    js = (WEB / "js" / "analysis-window.js").read_text(encoding="utf-8")
    assert "record.context" in js
    for field in ("company_id", "product_id",
                  "destination_country_code", "subject_id"):
        assert field in js
    # 탭 렌더러가 맥락을 다시 만들지 않는다
    tabs_js = (WEB / "js" / "bookmark-tabs.js").read_text(encoding="utf-8")
    assert "company_id" not in tabs_js
    assert "subject_id" not in tabs_js


# ── 메인 종합판정 (design.md) ─────────────────────────────────────────
def test_main_shows_only_five_items_from_server():
    """5개 항목은 서버 main_summary 를 그대로 순회한다. 화면이 만들지 않는다."""
    js = (WEB / "js" / "analysis-window.js").read_text(encoding="utf-8")
    assert "for (const item of run.main_summary)" in js
    # 항목 이름을 화면에서 하드코딩해 늘리지 않았는지
    assert "card__headline" in js and "card__note" in js


def test_context_bar_has_required_fields():
    js = (WEB / "js" / "analysis-window.js").read_text(encoding="utf-8")
    for label in ('"기업"', '"제품"', '"HS"', '"대상국"', '"기준일"'):
        assert label in js, label


def test_main_note_limited_to_short_line():
    css = (WEB / "css" / "app.css").read_text(encoding="utf-8")
    block = css.split(".card__note {")[1].split("}")[0]
    assert "-webkit-line-clamp: 2" in block


def test_missing_values_not_filled():
    js = (WEB / "js" / "analysis-window.js").read_text(encoding="utf-8")
    assert '"미입력"' in js          # 빈 값을 0 이 아니라 '미입력'으로
    assert "|| 0" not in js          # 결측을 0 으로 치환하지 않는다
    assert "?? 0" not in js


# ── 계층 경계 (명세서 §11) ────────────────────────────────────────────
FORBIDDEN_IN_VIEW = [
    # 점수 계산·가중치·임계값의 흔적
    r"\bweight\b", r"\bthreshold\b", r"\bscore\s*=", r"composite\s*=",
    r"Math\.(min|max|round|pow)\s*\([^)]*score",
]


def test_no_judgement_or_scoring_logic_in_frontend():
    for path in (WEB / "js").glob("*.js"):
        text = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN_IN_VIEW:
            assert not re.search(pattern, text, re.IGNORECASE), \
                f"{path.name}: 화면에 판정·계산 흔적 ({pattern})"


def test_frontend_reads_server_state_only():
    js = (WEB / "js" / "analysis-window.js").read_text(encoding="utf-8")
    # 서버가 준 state / display_label / reason_code 를 그대로 쓴다
    assert "d.results.state" in js
    assert "m.state" in js
    assert "item.state" in js
    assert "decision_label" in js
    # 탭 상세 5구성을 서버 tab_details 에서 읽는다
    assert "run.tab_details" in js


# ── 접근성 (명세서 §9) ────────────────────────────────────────────────
def test_reduced_motion_supported_both_ways():
    css = (WEB / "css" / "tokens.css").read_text(encoding="utf-8")
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert 'data-reduced-motion="true"' in css
    js = (WEB / "js" / "app.js").read_text(encoding="utf-8")
    assert "reducedMotion" in js


def test_focus_visible_defined():
    css = (WEB / "css" / "tokens.css").read_text(encoding="utf-8")
    assert ":focus-visible" in css
    assert "--focus-ring" in css


def test_status_not_color_only():
    """상태 배지에 형태(마크)와 문구가 함께 있다."""
    js = (WEB / "js" / "screens.js").read_text(encoding="utf-8")
    assert "STATE_MARK" in js and "STATE_TEXT" in js
    for state in ("actual", "not_entered", "not_evaluated",
                  "not_applicable", "fetch_failed"):
        assert state in js, state


def test_active_window_marked_with_text():
    js = (WEB / "js" / "window-manager.js").read_text(encoding="utf-8")
    assert '"활성 창"' in js
    css = (WEB / "css" / "app.css").read_text(encoding="utf-8")
    assert ".titlebar__activemark" in css


def test_live_region_present():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert 'aria-live="polite"' in html
    assert 'id="live"' in html


def test_layout_reset_and_prefs_reset_buttons():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert 'id="reset-layout"' in html
    assert "창 배치 초기화" in html
    # 공용 PC 고려 — 저장된 설정 초기화
    assert 'id="reset-prefs"' in html


# ── design.md UI 통일성 ───────────────────────────────────────────────
def test_button_height_at_least_40px():
    css = (WEB / "css" / "tokens.css").read_text(encoding="utf-8")
    for var in ("--control-h", "--control-h-sm"):
        m = re.search(rf"{var}:\s*(\d+)px", css)
        assert m, var
        assert int(m.group(1)) >= 40, f"{var} = {m.group(1)}px"


def test_korean_and_latin_font_with_fallbacks():
    css = (WEB / "css" / "tokens.css").read_text(encoding="utf-8")
    block = css.split("--font-sans:")[1].split(";")[0]
    # 한글 폰트와 대체 폰트가 함께 지정돼야 한다
    assert "Malgun Gothic" in block or "맑은 고딕" in block
    assert "Apple SD Gothic Neo" in block
    assert "sans-serif" in block
    assert block.count(",") >= 5


def test_no_external_font_or_script_fetch():
    """외부 CDN 을 끌어오지 않는다 (오프라인·의존성 결정 미룸)."""
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert "http://" not in html
    assert "https://" not in html


def test_long_text_does_not_overflow():
    css = (WEB / "css" / "tokens.css").read_text(encoding="utf-8")
    assert "word-break: keep-all" in css
    assert "overflow-wrap: anywhere" in css
    app_css = (WEB / "css" / "app.css").read_text(encoding="utf-8")
    # 버튼 문구가 잘리지 않게
    assert "white-space: normal" in css or "white-space: normal" in app_css


def test_state_screens_are_distinct():
    """로딩·빈 상태·오류·자료 부족·평가 보류가 서로 다른 화면."""
    js = (WEB / "js" / "screens.js").read_text(encoding="utf-8")
    for fn in ("loadingScreen", "emptyScreen", "errorScreen",
               "insufficientScreen", "withheldScreen", "notImplementedScreen"):
        assert f"export function {fn}" in js, fn
    css = (WEB / "css" / "app.css").read_text(encoding="utf-8")
    for kind in ("loading", "empty", "error", "insufficient", "withheld"):
        assert f".screen--{kind}" in css, kind
