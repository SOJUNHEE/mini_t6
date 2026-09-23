/* 창 관리자 — 공통 컴포넌트 (명세서 §8)
 *
 * 이동·크기 조절·최소화·최대화·닫기를 여기서만 구현한다. 각 화면은
 * 창 내용만 만들고 창 동작을 다시 만들지 않는다.
 *
 * Mac 외형을 복제하지 않는다 (명세서 §1-8).
 *
 * 중복 실행 정책 — 하나로 고정
 *   같은 key 의 창을 다시 열면 **새 창을 만들지 않고 기존 창을 활성화**한다.
 *   같은 평가 실행을 두 창에서 따로 보면 수치가 갈라져 보일 수 있고,
 *   화면과 보고서가 같은 평가 실행을 참조해야 하기 때문이다 (명세서 §6).
 *   최소화된 창이면 복원한 뒤 활성화한다.
 *
 * 판정·계산은 하지 않는다. 좌표와 크기만 다룬다 (명세서 §11).
 */

/* 시연용·개인 UI 편의 저장 (창 위치·크기). 기업 계정 저장이 아니다 (명세서 §10). */
const STORE_KEY = "axport.windows.geometry.v1";

/* 조작부(제목줄)가 화면 밖으로 나가지 않도록 남겨 둘 여백 */
const KEEP_VISIBLE_X = 96;   // 제목줄이 최소 이만큼은 보인다
const KEEP_VISIBLE_Y = 0;    // 제목줄 상단은 항상 보인다
const STEP = 16;             // 키보드 이동·크기 조절 단위
const STEP_LARGE = 64;

function readStore() {
  try {
    return JSON.parse(localStorage.getItem(STORE_KEY) || "{}");
  } catch {
    return {};   // 공용 PC·차단 환경에서도 화면은 떠야 한다
  }
}

function writeStore(data) {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(data));
  } catch {
    /* 저장 실패는 기능을 막지 않는다 */
  }
}

function minSize(el) {
  const cs = getComputedStyle(el);
  return {
    w: parseInt(cs.minWidth, 10) || 320,
    h: parseInt(cs.minHeight, 10) || 240,
  };
}

export class WindowManager {
  constructor({ layer, taskbar, announce }) {
    this.layer = layer;
    this.taskbar = taskbar;
    this.announce = announce || (() => {});
    this.windows = new Map();   // key -> record
    this.zTop = 10;
    this.active = null;

    window.addEventListener("resize", () => this.reflowAll());
  }

  /* ── 열기 ─────────────────────────────────────────────────────── */
  open({ key, title, render, width = 900, height = 560 }) {
    const existing = this.windows.get(key);
    if (existing) {
      // 중복 실행 정책: 기존 창 활성화
      if (existing.minimized) this.restore(key);
      this.focus(key);
      this.announce(`이미 열려 있는 창 '${existing.title}' 을 활성화했습니다.`);
      return existing;
    }

    const el = document.createElement("section");
    el.className = "window";
    el.dataset.key = key;
    el.dataset.active = "false";
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-label", title);
    el.tabIndex = -1;

    el.innerHTML = `
      <div class="window__frame">
        <header class="titlebar" data-role="titlebar">
          <span class="titlebar__activemark" aria-hidden="true">●</span>
          <h2 class="titlebar__title" data-role="title"></h2>
          <span class="sr-only" data-role="activetext"></span>
          <div class="winbtns">
            <button type="button" class="winbtn" data-act="minimize"
              aria-label="창 최소화" title="창 최소화 (Alt+Shift+↓)">–</button>
            <button type="button" class="winbtn" data-act="maximize"
              aria-label="창 최대화" aria-pressed="false"
              title="창 최대화 전환 (Alt+Shift+↑)">□</button>
            <button type="button" class="winbtn" data-act="close"
              aria-label="창 닫기" title="창 닫기 (Alt+Shift+W)">✕</button>
          </div>
        </header>
        <div class="window__body" data-role="body" tabindex="0"></div>
      </div>
      <div class="resize resize--e" data-resize="e" aria-hidden="true"></div>
      <div class="resize resize--s" data-resize="s" aria-hidden="true"></div>
      <div class="resize resize--se" data-resize="se" aria-hidden="true"></div>
    `;
    el.querySelector('[data-role="title"]').textContent = title;

    const record = {
      key, title, el,
      body: el.querySelector('[data-role="body"]'),
      minimized: false,
      maximized: false,
      preMaximize: null,
    };
    this.windows.set(key, record);
    this.layer.appendChild(el);

    const saved = readStore()[key];
    const offset = (this.windows.size - 1) * 28;
    this.setGeometry(record, saved || {
      x: 40 + offset,
      y: 24 + offset,
      w: width,
      h: height,
    });

    this.bindTitlebar(record);
    this.bindButtons(record);
    this.bindResize(record);
    el.addEventListener("pointerdown", () => this.focus(key), true);
    el.addEventListener("keydown", (e) => this.onKeydown(e, record));

    if (render) render(record.body, record);
    this.renderTaskbar();
    this.focus(key);
    el.focus({ preventScroll: true });
    this.announce(`창 '${title}' 을 열었습니다.`);
    return record;
  }

  /* ── 기하 ─────────────────────────────────────────────────────── */
  bounds() {
    return { w: this.layer.clientWidth, h: this.layer.clientHeight };
  }

  /* 조작부가 화면 밖에 갇히지 않도록 좌표를 보정한다 */
  clamp(record, g) {
    const b = this.bounds();
    const min = minSize(record.el);
    const w = Math.max(min.w, Math.min(g.w, Math.max(min.w, b.w)));
    const h = Math.max(min.h, Math.min(g.h, Math.max(min.h, b.h)));
    const maxX = Math.max(0, b.w - KEEP_VISIBLE_X);
    const maxY = Math.max(0, b.h - 44);   // 제목줄 한 줄은 남는다
    const x = Math.min(Math.max(g.x, KEEP_VISIBLE_Y), maxX);
    const y = Math.min(Math.max(g.y, 0), maxY);
    return { x, y, w, h };
  }

  setGeometry(record, g, { persist = true } = {}) {
    const c = this.clamp(record, g);
    record.el.style.left = `${c.x}px`;
    record.el.style.top = `${c.y}px`;
    record.el.style.width = `${c.w}px`;
    record.el.style.height = `${c.h}px`;
    record.geometry = c;
    if (persist && !record.maximized) {
      const all = readStore();
      all[record.key] = c;
      writeStore(all);
    }
    return c;
  }

  /* 화면 크기가 달라지면 모든 창을 보정한다 */
  reflowAll() {
    for (const record of this.windows.values()) {
      if (record.maximized) { this.applyMaximized(record); continue; }
      if (record.geometry) this.setGeometry(record, record.geometry, { persist: false });
    }
  }

  /* ── 이동 ─────────────────────────────────────────────────────── */
  bindTitlebar(record) {
    const bar = record.el.querySelector('[data-role="titlebar"]');
    bar.addEventListener("pointerdown", (e) => {
      if (e.target.closest(".winbtn")) return;
      if (record.maximized) return;
      const g = record.geometry;
      const startX = e.clientX, startY = e.clientY;
      bar.classList.add("is-dragging");
      bar.setPointerCapture(e.pointerId);

      const move = (ev) => {
        this.setGeometry(record, {
          ...g,
          x: g.x + (ev.clientX - startX),
          y: g.y + (ev.clientY - startY),
        }, { persist: false });
      };
      const up = () => {
        bar.classList.remove("is-dragging");
        bar.removeEventListener("pointermove", move);
        bar.removeEventListener("pointerup", up);
        this.setGeometry(record, record.geometry);
      };
      bar.addEventListener("pointermove", move);
      bar.addEventListener("pointerup", up);
    });

    bar.addEventListener("dblclick", (e) => {
      if (e.target.closest(".winbtn")) return;
      this.toggleMaximize(record.key);
    });
  }

  /* ── 크기 조절 ────────────────────────────────────────────────── */
  bindResize(record) {
    record.el.querySelectorAll("[data-resize]").forEach((handle) => {
      handle.addEventListener("pointerdown", (e) => {
        if (record.maximized) return;
        e.stopPropagation();
        const dir = handle.dataset.resize;
        const g = record.geometry;
        const startX = e.clientX, startY = e.clientY;
        handle.setPointerCapture(e.pointerId);

        const move = (ev) => {
          const next = { ...g };
          if (dir.includes("e")) next.w = g.w + (ev.clientX - startX);
          if (dir.includes("s")) next.h = g.h + (ev.clientY - startY);
          this.setGeometry(record, next, { persist: false });
        };
        const up = () => {
          handle.removeEventListener("pointermove", move);
          handle.removeEventListener("pointerup", up);
          this.setGeometry(record, record.geometry);
        };
        handle.addEventListener("pointermove", move);
        handle.addEventListener("pointerup", up);
      });
    });
  }

  /* ── 버튼 ─────────────────────────────────────────────────────── */
  bindButtons(record) {
    record.el.querySelectorAll("[data-act]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const act = btn.dataset.act;
        if (act === "minimize") this.minimize(record.key);
        if (act === "maximize") this.toggleMaximize(record.key);
        if (act === "close") this.close(record.key);
      });
    });
  }

  /* ── 상태 전환 ────────────────────────────────────────────────── */
  focus(key) {
    const record = this.windows.get(key);
    if (!record) return;
    this.zTop += 1;
    record.el.style.zIndex = String(this.zTop);
    for (const [k, r] of this.windows) {
      const isActive = k === key;
      r.el.dataset.active = String(isActive);
      // 활성 상태를 색 외에 텍스트로도 알린다 (명세서 §9)
      r.el.querySelector('[data-role="activetext"]').textContent =
        isActive ? "활성 창" : "";
    }
    this.active = key;
    this.renderTaskbar();
  }

  minimize(key) {
    const record = this.windows.get(key);
    if (!record) return;
    record.minimized = true;
    record.el.dataset.minimized = "true";
    this.announce(`창 '${record.title}' 을 최소화했습니다. 아래 창 목록에서 다시 열 수 있습니다.`);
    const next = [...this.windows.values()].find((r) => !r.minimized);
    if (next) this.focus(next.key); else this.active = null;
    this.renderTaskbar();
  }

  restore(key) {
    const record = this.windows.get(key);
    if (!record) return;
    record.minimized = false;
    record.el.dataset.minimized = "false";
    this.focus(key);
    record.el.focus({ preventScroll: true });
  }

  applyMaximized(record) {
    const b = this.bounds();
    record.el.style.left = "0px";
    record.el.style.top = "0px";
    record.el.style.width = `${b.w}px`;
    record.el.style.height = `${b.h}px`;
  }

  toggleMaximize(key) {
    const record = this.windows.get(key);
    if (!record) return;
    const btn = record.el.querySelector('[data-act="maximize"]');
    if (record.maximized) {
      record.maximized = false;
      record.el.dataset.maximized = "false";
      btn.setAttribute("aria-pressed", "false");
      this.setGeometry(record, record.preMaximize || record.geometry);
      this.announce(`창 '${record.title}' 크기를 되돌렸습니다.`);
    } else {
      record.preMaximize = record.geometry;
      record.maximized = true;
      record.el.dataset.maximized = "true";
      btn.setAttribute("aria-pressed", "true");
      this.applyMaximized(record);
      this.announce(`창 '${record.title}' 을 최대화했습니다.`);
    }
    this.focus(key);
  }

  close(key) {
    const record = this.windows.get(key);
    if (!record) return;
    record.el.remove();
    this.windows.delete(key);
    this.announce(`창 '${record.title}' 을 닫았습니다.`);
    const next = [...this.windows.values()].find((r) => !r.minimized);
    if (next) this.focus(next.key); else this.active = null;
    this.renderTaskbar();
  }

  /* ── 창 배치 초기화 (명세서 §8) ───────────────────────────────── */
  resetLayout() {
    writeStore({});
    let i = 0;
    for (const record of this.windows.values()) {
      record.maximized = false;
      record.el.dataset.maximized = "false";
      record.el.querySelector('[data-act="maximize"]')
        .setAttribute("aria-pressed", "false");
      record.minimized = false;
      record.el.dataset.minimized = "false";
      this.setGeometry(record, { x: 40 + i * 28, y: 24 + i * 28, w: 900, h: 560 });
      i += 1;
    }
    this.renderTaskbar();
    this.announce("창 배치를 초기화했습니다.");
  }

  /* ── 작업 표시줄 — 최소화한 창을 되찾는 경로 ──────────────────── */
  renderTaskbar() {
    if (!this.taskbar) return;
    this.taskbar.replaceChildren();
    for (const record of this.windows.values()) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "taskbar__btn";
      btn.textContent = record.minimized ? `${record.title} (최소화)` : record.title;
      btn.setAttribute("aria-current", String(this.active === record.key));
      btn.addEventListener("click", () => {
        if (record.minimized) this.restore(record.key);
        else this.focus(record.key);
        record.el.focus({ preventScroll: true });
      });
      this.taskbar.appendChild(btn);
    }
  }

  /* ── 키보드 조작 (명세서 §9) ──────────────────────────────────── */
  onKeydown(e, record) {
    if (!e.altKey || !e.shiftKey) return;
    const g = record.geometry;
    const step = e.ctrlKey ? STEP_LARGE : STEP;
    let handled = true;

    switch (e.key) {
      case "ArrowLeft":
        this.setGeometry(record, { ...g, x: g.x - step }); break;
      case "ArrowRight":
        this.setGeometry(record, { ...g, x: g.x + step }); break;
      case "ArrowUp":
        if (e.key === "ArrowUp" && g.y === 0) this.toggleMaximize(record.key);
        else this.setGeometry(record, { ...g, y: g.y - step });
        break;
      case "ArrowDown":
        this.setGeometry(record, { ...g, y: g.y + step }); break;
      case "+": case "=":
        this.setGeometry(record, { ...g, w: g.w + step, h: g.h + step }); break;
      case "-": case "_":
        this.setGeometry(record, { ...g, w: g.w - step, h: g.h - step }); break;
      case "W": case "w":
        this.close(record.key); break;
      case "M": case "m":
        this.minimize(record.key); break;
      default:
        handled = false;
    }
    if (handled) {
      e.preventDefault();
      if (record.geometry) {
        this.announce(
          `창 위치 ${record.geometry.x}, ${record.geometry.y} · ` +
          `크기 ${record.geometry.w}×${record.geometry.h}`
        );
      }
    }
  }
}

export const KEYBOARD_HELP = [
  "Alt+Shift+방향키 — 창 이동 (Ctrl 함께 누르면 크게)",
  "Alt+Shift+ +/- — 창 크기 조절",
  "Alt+Shift+↑ (창이 맨 위) — 최대화 전환",
  "Alt+Shift+M — 최소화",
  "Alt+Shift+W — 닫기",
  "책갈피 탭 — 방향키로 이동, Home/End 로 처음·끝",
];
