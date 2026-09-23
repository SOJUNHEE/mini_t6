/* 상태 화면 — 로딩 / 빈 상태 / 오류 / 자료 부족 / 평가 보류
 *
 * 다섯을 **서로 다른 화면**으로 만든다 (명세서 §9 — 로딩·오류·빈 상태를
 * 구분한다). 같은 화면에 문구만 바꿔 넣지 않는다.
 *
 * 색만으로 구분하지 않는다. 각 화면에 형태(마크)와 문구가 함께 있다.
 *
 * 값을 만들어 채우지 않는다. 서버가 준 상태와 이유만 표시한다.
 */

import { TABS } from "./bookmark-tabs.js";

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function screen({ kind, mark, title, body, bullets = [], actions = [] }) {
  const root = el("div", `screen screen--${kind}`);
  root.setAttribute("role", kind === "error" ? "alert" : "status");

  const markBox = el("div", "screen__mark");
  markBox.setAttribute("aria-hidden", "true");
  markBox.textContent = mark;
  root.append(markBox);

  root.append(el("h3", "screen__title", title));
  if (body) root.append(el("p", "screen__body", body));

  if (bullets.length) {
    const ul = el("ul", "screen__list");
    for (const b of bullets) ul.append(el("li", null, b));
    root.append(ul);
  }

  if (actions.length) {
    const box = el("div", "screen__actions");
    for (const a of actions) {
      const btn = el("button", "btn", a.label);
      btn.type = "button";
      if (a.primary) btn.classList.add("btn--primary");
      btn.addEventListener("click", a.onClick);
      box.append(btn);
    }
    root.append(box);
  }
  return root;
}

/* ① 로딩 — 진행 중. 이전 결과를 최신처럼 보여주지 않는다 (명세서 §9) */
export function loadingScreen(what) {
  const node = screen({
    kind: "loading",
    mark: "…",
    title: "불러오는 중",
    body: `${what} 을 불러오고 있습니다.`,
  });
  const sp = el("div", "spinner");
  sp.setAttribute("aria-hidden", "true");
  node.querySelector(".screen__title").after(sp);
  return node;
}

/* ② 빈 상태 — 데이터가 아직 없음. 오류가 아니다 */
export function emptyScreen({ title, body, actions = [] }) {
  return screen({ kind: "empty", mark: "○", title, body, actions });
}

/* ③ 오류 — 실패했고 재시도 경로를 준다 (명세서 §8) */
export function errorScreen({ title = "요청을 처리하지 못했습니다", body,
                              detail, onRetry }) {
  const bullets = [];
  if (detail?.code) bullets.push(`오류 코드: ${detail.code}`);
  if (detail?.stage) bullets.push(`단계: ${detail.stage}`);
  if (detail?.detail) {
    for (const [k, v] of Object.entries(detail.detail)) {
      bullets.push(`${k}: ${Array.isArray(v) ? v.join(", ") : v}`);
    }
  }
  const actions = onRetry
    ? [{ label: "다시 시도", primary: true, onClick: onRetry }]
    : [];
  return screen({ kind: "error", mark: "!", title, body, bullets, actions });
}

/* ④ 자료 부족 — 입력·외부 자료가 없어 계산할 수 없다 */
export function insufficientScreen({ title = "자료 부족", body,
                                     requiredInputs = [], requiredSources = [],
                                     actions = [] }) {
  const bullets = [];
  for (const r of requiredInputs) bullets.push(`필요한 입력 — ${r}`);
  for (const s of requiredSources) bullets.push(`필요한 자료 — ${s}`);
  return screen({
    kind: "insufficient",
    mark: "△",
    title,
    body: body || "값을 임의로 채우지 않습니다. 아래 항목이 확보되면 평가합니다.",
    bullets,
    actions,
  });
}

/* ⑤ 평가 보류 — 규칙·설정이 미확보·미승인이라 계산을 시작하지 않았다 */
export function withheldScreen({ title = "평가 보류", body, reasons = [],
                                 actions = [] }) {
  return screen({
    kind: "withheld",
    mark: "‖",
    title,
    body: body || "판정 규칙 또는 설정이 확정되지 않아 평가를 시작하지 않았습니다.",
    bullets: reasons,
    actions,
  });
}

/* ⑥ 미구현 — 아직 만들지 않은 화면. 있는 것처럼 꾸미지 않는다 */
export function notImplementedScreen(tabId) {
  const label = TABS.find((t) => t.id === tabId)?.label || tabId;
  return screen({
    kind: "notimpl",
    mark: "·",
    title: `${label} 상세 화면 미구현`,
    body: "이 탭의 수치·차트·상세 표는 아직 만들지 않았습니다. "
        + "지표 계산 계층이 비어 있어 표시할 실제 값이 없습니다.",
    bullets: [
      "지표 계산(metrics) 계층 미구현",
      "값이 없는 자리를 예시 수치로 채우지 않습니다 (명세서 §7)",
    ],
  });
}

/* 상태 배지 — 색 + 형태 + 문구 */
const STATE_MARK = {
  actual: "✓",
  not_entered: "△",
  not_evaluated: "‖",
  not_applicable: "—",
  fetch_failed: "!",
};
const STATE_TEXT = {
  actual: "확인됨",
  not_entered: "자료 부족",
  not_evaluated: "평가 보류",
  not_applicable: "해당 없음",
  fetch_failed: "조회 실패",
};

export function stateBadge(state, textOverride) {
  const span = el("span", `state state--${state}`);
  const mark = el("span", "state-mark", STATE_MARK[state] ?? "?");
  mark.setAttribute("aria-hidden", "true");
  span.append(mark, el("span", "state-text",
    textOverride || STATE_TEXT[state] || state));
  return span;
}

/* 데이터 구분 배지 — 실제 자료 / 사용자 입력 / 샘플 / 가정값 (명세서 §7) */
const DATA_CLASS_MARK = {
  real: "●", user_input: "◐", sample: "◌", assumption: "◇",
};
const DATA_CLASS_TEXT = {
  real: "실제 자료", user_input: "사용자 입력",
  sample: "시연 데이터", assumption: "가정값",
};
export function dataClassBadge(dataClass, label) {
  const span = el("span", `dataclass dataclass--${dataClass || "unknown"}`);
  const mark = el("span", "state-mark", DATA_CLASS_MARK[dataClass] ?? "?");
  mark.setAttribute("aria-hidden", "true");
  span.append(mark, el("span", null,
    label || DATA_CLASS_TEXT[dataClass] || "구분 미상"));
  return span;
}

/* 외부 조회 상태 배지 — ok / no_data / no_permission / connection_failed / stale */
const FETCH_TEXT = {
  ok: "조회 성공", no_data: "자료 없음", no_permission: "권한 없음",
  connection_failed: "연결 실패", stale_cache_used: "오래된 저장 자료 사용",
  file_present: "파일 보유",
};
const FETCH_STATE = {
  ok: "actual", no_data: "not_entered", no_permission: "fetch_failed",
  connection_failed: "fetch_failed", stale_cache_used: "not_evaluated",
  file_present: "not_applicable",
};
export function fetchBadge(fetchResult) {
  return stateBadge(FETCH_STATE[fetchResult] || "not_evaluated",
    FETCH_TEXT[fetchResult] || fetchResult);
}

export { el };
