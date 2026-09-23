/* 책갈피 탭 — 분석 창 오른쪽에 부착 (명세서 §8)
 *
 * 창의 형제 요소로 창 안에 들어가므로 창을 옮기면 함께 움직인다.
 *
 * 선택 탭은 색상 외에 **형태**(왼쪽 굵은 띠·들여쓰기·글꼴 굵기)와
 * **텍스트 마커(▸)**, 그리고 aria-selected 로도 구분한다
 * (design.md, 명세서 §9).
 *
 * 창 높이가 작으면 탭 영역이 스크롤된다 (app.css .bookmarks overflow-y).
 *
 * 탭 전환은 화면만 바꾼다. 기업·제품·목적국·평가 실행 맥락은
 * 창이 들고 있으며 탭이 건드리지 않는다.
 */

export const TABS = [
  { id: "overall", label: "종합판정" },
  { id: "trade_history", label: "수출실적" },
  { id: "market", label: "시장성" },
  { id: "tariff_origin", label: "관세·원산지" },
  { id: "export_control", label: "수출규제" },
  { id: "counterparty", label: "거래처" },
  { id: "profit_fx", label: "수익성·환율" },
  { id: "supply_logistics", label: "공급·물류" },
];

export class BookmarkTabs {
  /**
   * @param {object} o
   * @param {HTMLElement} o.mount   창 안의 탭 컨테이너
   * @param {HTMLElement} o.panel   탭 내용이 그려질 영역
   * @param {(tabId:string, panel:HTMLElement)=>void} o.renderPanel
   * @param {(msg:string)=>void} o.announce
   */
  constructor({ mount, panel, renderPanel, announce, initial = "overall" }) {
    this.mount = mount;
    this.panel = panel;
    this.renderPanel = renderPanel;
    this.announce = announce || (() => {});
    this.current = initial;
    this.buttons = new Map();
    this.build();
    this.select(initial, { silent: true });
  }

  build() {
    this.mount.className = "bookmarks";
    this.mount.setAttribute("role", "tablist");
    this.mount.setAttribute("aria-orientation", "vertical");
    this.mount.setAttribute("aria-label", "판단 근거별 화면");

    for (const tab of TABS) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "bookmark";
      btn.id = `tab-${this.uid()}-${tab.id}`;
      btn.setAttribute("role", "tab");
      btn.setAttribute("aria-selected", "false");
      btn.setAttribute("aria-controls", this.panel.id);
      btn.tabIndex = -1;
      btn.dataset.tab = tab.id;
      btn.innerHTML =
        `<span class="bookmark__mark" aria-hidden="true">▸</span>` +
        `<span class="bookmark__label"></span>` +
        `<span class="sr-only" data-role="selected"></span>`;
      btn.querySelector(".bookmark__label").textContent = tab.label;

      btn.addEventListener("click", () => this.select(tab.id));
      btn.addEventListener("keydown", (e) => this.onKeydown(e, tab.id));
      this.mount.appendChild(btn);
      this.buttons.set(tab.id, btn);
    }
  }

  uid() {
    this._uid = this._uid || Math.random().toString(36).slice(2, 8);
    return this._uid;
  }

  select(tabId, { silent = false } = {}) {
    if (!this.buttons.has(tabId)) return;
    this.current = tabId;

    for (const [id, btn] of this.buttons) {
      const selected = id === tabId;
      btn.setAttribute("aria-selected", String(selected));
      btn.tabIndex = selected ? 0 : -1;
      // 스크린리더에도 선택 상태를 문구로 전달
      btn.querySelector('[data-role="selected"]').textContent =
        selected ? "선택됨" : "";
    }

    const label = TABS.find((t) => t.id === tabId).label;
    this.panel.setAttribute("aria-labelledby", this.buttons.get(tabId).id);
    this.panel.replaceChildren();
    this.renderPanel(tabId, this.panel);

    // 탭 영역이 스크롤될 때 선택 탭이 보이도록
    this.buttons.get(tabId).scrollIntoView({ block: "nearest" });
    if (!silent) this.announce(`${label} 화면으로 전환했습니다.`);
  }

  focus() {
    this.buttons.get(this.current).focus();
  }

  onKeydown(e, tabId) {
    const ids = TABS.map((t) => t.id);
    const i = ids.indexOf(tabId);
    let next = null;

    switch (e.key) {
      case "ArrowDown": case "ArrowRight":
        next = ids[(i + 1) % ids.length]; break;
      case "ArrowUp": case "ArrowLeft":
        next = ids[(i - 1 + ids.length) % ids.length]; break;
      case "Home": next = ids[0]; break;
      case "End": next = ids[ids.length - 1]; break;
      default: return;
    }
    e.preventDefault();
    this.select(next);
    this.buttons.get(next).focus();
  }
}
