/* /app 부트스트랩
 *
 * 이 앱은 /app 만 담당한다. 홈(/)은 web/home/ + home.js 가 따로 담당하며
 * 두 화면은 상태·스타일을 공유하지 않는다 (공통 토큰 tokens.css 만 공유, 명세서 §8).
 */

import { api } from "./api.js";
import { Desktop } from "./desktop.js";
import { errorScreen, loadingScreen } from "./screens.js";
import { KEYBOARD_HELP, WindowManager } from "./window-manager.js";

/* 저장 범위 구분 (명세서 §10)
 * 아래 localStorage 키는 **시연용·개인 UI 편의 저장**이다:
 *   - 애니메이션 줄이기 여부, 창 위치·크기
 * 기업 계정·기업 데이터·평가 결과를 브라우저에 저장하지 않는다.
 * 평가 실행(run)·업로드는 서버 instance/ 에만 있고, 장기 기업 계정 저장소는
 * 존재하지 않는다(미구현 — README '운영 전 필요 작업'). */
const STORAGE_SCOPE = "demo-ui-preferences";   // 기업 계정 저장이 아님
const PREF_KEY = "axport.prefs.v1";

function readPrefs() {
  try { return JSON.parse(localStorage.getItem(PREF_KEY) || "{}"); }
  catch { return {}; }
}
function writePrefs(p) {
  try { localStorage.setItem(PREF_KEY, JSON.stringify(p)); } catch { /* 무시 */ }
}

const live = document.getElementById("live");
function announce(msg) {
  if (!live) return;
  live.textContent = "";
  // 같은 문구가 연속될 때도 읽히도록 한 틱 뒤에 넣는다
  requestAnimationFrame(() => { live.textContent = msg; });
}

/* ── 애니메이션 줄이기 (명세서 §9) ──────────────────────────────── */
const motionBtn = document.getElementById("toggle-motion");
function applyMotion(reduced) {
  document.documentElement.dataset.reducedMotion = String(reduced);
  motionBtn.setAttribute("aria-pressed", String(reduced));
  motionBtn.textContent = reduced ? "애니메이션 줄이기: 켬" : "애니메이션 줄이기: 끔";
}
const prefs = readPrefs();
applyMotion(prefs.reducedMotion === true);
motionBtn.addEventListener("click", () => {
  const next = motionBtn.getAttribute("aria-pressed") !== "true";
  applyMotion(next);
  writePrefs({ ...readPrefs(), reducedMotion: next });
  announce(next ? "애니메이션을 줄입니다." : "애니메이션을 사용합니다.");
});

/* ── 창 관리자 ─────────────────────────────────────────────────── */
const wm = new WindowManager({
  layer: document.getElementById("window-layer"),
  taskbar: document.getElementById("taskbar"),
  announce,
});

document.getElementById("reset-layout").addEventListener("click", () => {
  wm.resetLayout();
});

/* 공용 PC 고려 — 저장된 사용자 설정을 초기화할 수 있게 한다 (명세서 §9) */
document.getElementById("reset-prefs").addEventListener("click", () => {
  try {
    localStorage.removeItem(PREF_KEY);
    localStorage.removeItem("axport.windows.geometry.v1");
  } catch { /* 무시 */ }
  applyMotion(false);
  wm.resetLayout();
  announce("저장된 화면 설정을 초기화했습니다.");
});

/* 키보드 도움 */
document.getElementById("keyboard-help").addEventListener("click", () => {
  wm.open({
    key: "keyboard-help",
    title: "키보드 조작",
    width: 520, height: 360,
    render: (body) => {
      const pane = document.createElement("div");
      pane.className = "tabpanel";
      const h = document.createElement("h3");
      h.className = "tabpanel__title";
      h.textContent = "키보드 조작";
      const ul = document.createElement("ul");
      ul.className = "screen__list";
      for (const line of KEYBOARD_HELP) {
        const li = document.createElement("li");
        li.textContent = line;
        ul.append(li);
      }
      pane.append(h, ul);
      body.append(pane);
    },
  });
});

/* ── 기동 ─────────────────────────────────────────────────────── */
const desktopEl = document.getElementById("desktop-icons");

async function boot() {
  desktopEl.replaceChildren(loadingScreen("앱 준비 상태"));
  try {
    const health = await api.health();
    document.getElementById("app-mode").textContent =
      health.checks.runtime.demo_mode ? "데모 모드" : health.checks.runtime.env;

    const desktop = new Desktop({
      mount: desktopEl, wm, announce, health,
    });
    await desktop.refresh();
    window.__axport = { wm, desktop, storageScope: STORAGE_SCOPE };   // 수동 확인용
    announce("대시보드 앱을 열었습니다.");
  } catch (err) {
    // 준비 실패 시 이유와 재시도 경로를 표시한다 (명세서 §8)
    desktopEl.replaceChildren(errorScreen({
      title: "앱을 준비하지 못했습니다",
      body: err.message,
      detail: err.info,
      onRetry: boot,
    }));
  }
}

boot();
