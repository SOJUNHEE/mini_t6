/* 홈 화면 부트스트랩 (/) — 앱(app.js)과 분리. 상태를 공유하지 않는다.
 *
 * 앱 진입 로딩 (명세서 §1-5, §8)
 *   실제 준비 상태(/health)를 확인한 뒤 /app 으로 이동한다.
 *   고정 대기시간을 넣지 않는다. 응답이 오면 즉시 이동한다.
 *   실패하면 이유와 다시 시도 경로를 보여 준다.
 *
 * 3D (명세서 §8)
 *   home-3d.js 를 동적으로 불러온다. 실패·미지원이면 정적 대체 화면이 남는다.
 *   애니메이션 줄이기 설정이면 3D 를 시도하지 않고 정적 화면을 쓴다.
 */

const live = document.getElementById("live");
function announce(msg) {
  if (!live) return;
  live.textContent = "";
  requestAnimationFrame(() => { live.textContent = msg; });
}

/* ── 3D 또는 정적 대체 ─────────────────────────────────────────── */
async function mount3d() {
  const stage = document.getElementById("hero-stage");
  const note = document.getElementById("hero-fallback-note");
  const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  if (reduced) {
    note.textContent = "애니메이션 줄이기 설정 — 정적 화면";
    return { mode: "static", reason: "reduced-motion" };
  }
  const t0 = performance.now();
  try {
    const mod = await import("./home-3d.js");
    const ok = mod.mount(stage);
    const ms = Math.round(performance.now() - t0);
    if (!ok) {
      note.textContent = "3D 미지원 브라우저 — 정적 화면";
      return { mode: "static", reason: "unsupported", ms };
    }
    return { mode: "3d", ms };
  } catch (err) {
    // 스크립트 로드 실패 → 정적 대체 화면 그대로 (명세서 §8)
    note.textContent = "3D 자산을 불러오지 못해 정적 화면으로 표시합니다";
    return { mode: "static", reason: err?.message || "load-failed" };
  }
}

/* ── 앱 진입 로딩 — 실제 준비 상태와 연결 ────────────────────────── */
const loader = document.getElementById("loader");
const loaderTitle = document.getElementById("loader-title");
const loaderBody = document.getElementById("loader-body");
const loaderChecks = document.getElementById("loader-checks");
const loaderActions = document.getElementById("loader-actions");

function checkRow(label, ok, detail) {
  const li = document.createElement("li");
  const mark = document.createElement("span");
  mark.className = "state-mark";
  mark.setAttribute("aria-hidden", "true");
  mark.textContent = ok === true ? "✓" : ok === false ? "!" : "…";
  const text = document.createElement("span");
  text.textContent = `${label}${detail ? ` — ${detail}` : ""}`;
  li.append(mark, text);
  return li;
}

function setLoader(state, title, body) {
  loader.dataset.state = state;
  loaderTitle.textContent = title;
  loaderBody.textContent = body;
  loaderActions.hidden = state !== "error";
}

async function enterApp() {
  loader.hidden = false;
  loaderChecks.replaceChildren();
  setLoader("checking", "앱 준비 상태 확인 중", "서버 준비 상태를 확인하고 있습니다.");
  announce("앱 준비 상태를 확인합니다.");

  let res;
  const started = performance.now();
  try {
    res = await fetch("/health", { cache: "no-store" });
  } catch (err) {
    setLoader("error", "서버에 연결하지 못했습니다",
      "네트워크 또는 서버가 응답하지 않습니다. 다시 시도하거나 홈으로 돌아가세요.");
    loaderChecks.append(checkRow("서버 연결", false, err?.message || "network error"));
    announce("서버에 연결하지 못했습니다.");
    return;
  }
  const ms = Math.round(performance.now() - started);

  let health = null;
  try { health = await res.json(); } catch { health = null; }

  if (!res.ok || !health) {
    setLoader("error", "준비 상태를 읽지 못했습니다",
      `HTTP ${res.status}. 서버가 헬스체크에 응답하지 않았습니다.`);
    loaderChecks.append(checkRow("헬스체크", false, `HTTP ${res.status}`));
    return;
  }

  const c = health.checks || {};
  loaderChecks.append(checkRow("서버 응답", true, `${ms} ms`));
  loaderChecks.append(checkRow("설정 로드", c.config?.loaded === true,
    c.config?.loaded ? `미정 ${c.config.undecided_count}건` : c.config?.reason));
  loaderChecks.append(checkRow("저장 경로", c.storage
    ? Object.values(c.storage).every(Boolean) : null));
  loaderChecks.append(checkRow("api-vault 참조", c.api_vault?.reachable === true,
    c.api_vault?.reachable ? `키 ${c.api_vault.keys_configured_count}건 (건수만)`
                           : c.api_vault?.reason));
  loaderChecks.append(checkRow("업로드 기능",
    c.features?.upload === true ? true : null,
    c.features?.upload === true ? "활성" : "비활성 (제한값 승인 대기)"));

  if (health.status === "error") {
    setLoader("error", "앱을 준비하지 못했습니다",
      c.config?.reason || "설정을 읽지 못했습니다.");
    announce("앱을 준비하지 못했습니다.");
    return;
  }

  // 준비됨 — 고정 대기 없이 바로 이동
  setLoader("ready", health.status === "degraded" ? "일부 기능 제한 상태로 진입"
                                                   : "준비 완료",
    health.status === "degraded"
      ? "일부 점검이 실패했지만 앱은 열 수 있습니다. 제한 사항은 앱 안에서 표시됩니다."
      : "대시보드 앱으로 이동합니다.");
  announce("대시보드 앱으로 이동합니다.");
  window.location.assign("/app");
}

for (const id of ["enter-app-top", "enter-app-hero", "enter-app-bottom"]) {
  document.getElementById(id)?.addEventListener("click", enterApp);
}
document.getElementById("loader-retry").addEventListener("click", enterApp);
document.getElementById("loader-cancel").addEventListener("click", () => {
  loader.hidden = true;
  announce("홈으로 돌아왔습니다.");
});
loader.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && loader.dataset.state === "error") loader.hidden = true;
});

/* ── 기동 ─────────────────────────────────────────────────────── */
mount3d().then((r) => {
  window.__axportHome = { hero3d: r };   // 수동 확인용 (앱 상태와 무관)
});
