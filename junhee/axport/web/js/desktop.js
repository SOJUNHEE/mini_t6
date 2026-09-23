/* 바탕화면 — 업로드·최근 분석·기업 데이터·보고서 진입점 (명세서 §8)
 *
 * 빈 바탕화면 상태도 여기서 그린다. 아이콘은 있고 최근 분석이 없을 때와,
 * 서버 준비가 안 됐을 때를 구분한다.
 */

import { api, ApiError } from "./api.js";
import { renderAnalysisWindow } from "./analysis-window.js";
import {
  el, emptyScreen, errorScreen, insufficientScreen, loadingScreen,
} from "./screens.js";

/* 시연 데이터 환경 안내 (명세서 §10, §13-8).
 * 서버 health.checks.runtime.demo_mode 가 true 일 때만 표시한다.
 * 실제 기업 자료를 받지 않는다. */
function demoBanner(health, where) {
  if (health?.checks?.runtime?.demo_mode !== true) return null;
  const box = el("div", "notice notice--demo");
  box.setAttribute("role", "note");
  box.append(el("span", "notice__mark", "◌"));
  const text = el("span");
  text.append(el("strong", null, "시연 데이터 환경 — "));
  text.append(el("span", null,
    where === "upload"
      ? "실제 기업 자료를 업로드하지 마세요. 가상 샘플(data/samples)만 사용합니다. "
        + "업로드 파일은 시연용으로만 보관되며 기업 계정 저장이 아닙니다."
      : "실제 기업 자료를 넣지 마세요. 이 화면의 데이터는 시연용 샘플·사용자 입력이며 "
        + "실제 자료·가정값과 배지로 구분됩니다."));
  box.append(text);
  return box;
}

const ICONS = [
  { id: "upload", glyph: "↑", label: "엑셀 업로드",
    hint: "기업 데이터 업로드" },
  { id: "recent", glyph: "◫", label: "최근 분석",
    hint: "최근 업로드와 분석 결과" },
  { id: "company", glyph: "▤", label: "기업 데이터",
    hint: "업로드한 데이터셋과 검증 결과" },
  { id: "reports", glyph: "▥", label: "보고서",
    hint: "생성된 보고서" },
];

export class Desktop {
  constructor({ mount, wm, announce, health }) {
    this.mount = mount;
    this.wm = wm;
    this.announce = announce;
    this.health = health;
    this.uploads = [];
    this.render();
  }

  render() {
    this.mount.replaceChildren();
    const list = el("ul", "icons");
    list.setAttribute("aria-label", "바탕화면 아이콘");

    for (const def of ICONS) {
      const li = el("li");
      const btn = el("button", "icon");
      btn.type = "button";
      btn.dataset.icon = def.id;

      const glyph = el("span", "icon__glyph", def.glyph);
      glyph.setAttribute("aria-hidden", "true");
      btn.append(glyph);
      btn.append(el("span", "icon__label", def.label));

      const count = el("span", "icon__count");
      btn.append(count);
      this.decorate(def.id, btn, count);

      btn.addEventListener("click", () => this.activate(def.id));
      btn.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          this.activate(def.id);
        }
      });
      li.append(btn);
      list.append(li);
    }
    const banner = demoBanner(this.health, "desktop");
    if (banner) this.mount.append(banner);
    this.mount.append(list);

    // 빈 바탕화면 — 아이콘 외에 열린 창도, 업로드도 없을 때
    if (this.wm.windows.size === 0) {
      this.mount.append(this.emptyDesktop());
    }
  }

  decorate(id, btn, count) {
    const uploadEnabled = this.health?.checks?.features?.upload === true;
    if (id === "upload" && !uploadEnabled) {
      btn.setAttribute("aria-disabled", "true");
      count.textContent = "비활성";
      btn.title = "업로드 기능이 비활성 상태입니다";
    }
    if (id === "recent" || id === "company") {
      count.textContent = this.uploads.length
        ? `${this.uploads.length}건` : "없음";
    }
    if (id === "reports") {
      count.textContent = this.health?.checks?.features?.reports
        ? "" : "미구현";
      if (!this.health?.checks?.features?.reports) {
        btn.setAttribute("aria-disabled", "true");
      }
    }
  }

  emptyDesktop() {
    const wrap = el("div");
    wrap.style.padding = "0 var(--sp-5) var(--sp-5)";
    const uploadEnabled = this.health?.checks?.features?.upload === true;

    if (!uploadEnabled) {
      wrap.append(insufficientScreen({
        title: "업로드를 받을 수 없는 상태입니다",
        body: "업로드 제한값이 승인되지 않아 기능이 비활성입니다. "
            + "임의의 기본값으로 대체하지 않습니다.",
        requiredSources: [
          "config/settings.toml 의 upload.max_file_bytes 등 제한값 승인 (명세서 §2)",
          "features.upload = true",
        ],
      }));
      return wrap;
    }
    if (this.uploads.length === 0) {
      wrap.append(emptyScreen({
        title: "아직 분석한 자료가 없습니다",
        body: "엑셀을 업로드하면 검증 결과와 분석 창이 열립니다. "
            + "표준 양식은 data/samples 에 있습니다.",
        actions: [{ label: "엑셀 업로드", primary: true,
                    onClick: () => this.activate("upload") }],
      }));
      return wrap;
    }
    wrap.append(emptyScreen({
      title: "열린 창이 없습니다",
      body: "최근 분석에서 평가 대상을 선택하면 분석 창이 열립니다.",
      actions: [{ label: "최근 분석 열기", primary: true,
                  onClick: () => this.activate("recent") }],
    }));
    return wrap;
  }

  async refresh() {
    try {
      const res = await api.listUploads();
      this.uploads = res.uploads || [];
    } catch {
      this.uploads = [];
    }
    this.render();
  }

  activate(id) {
    if (id === "upload") return this.openUpload();
    if (id === "recent" || id === "company") return this.openRecent(id);
    if (id === "reports") return this.openReports();
  }

  /* ── 업로드 창 ────────────────────────────────────────────────── */
  openUpload() {
    this.wm.open({
      key: "upload",
      title: "엑셀 업로드",
      width: 760, height: 460,
      render: (body) => {
        const pane = el("div", "tabpanel");
        body.append(pane);
        this.renderUploadForm(pane);
      },
    });
  }

  renderUploadForm(pane) {
    pane.replaceChildren();
    const head = el("div", "tabpanel__head");
    head.append(el("h3", "tabpanel__title", "엑셀 업로드"));
    pane.append(head);

    const banner = demoBanner(this.health, "upload");
    if (banner) pane.append(banner);
    pane.append(el("p", "screen__body",
      "표준 양식(.xlsx)만 받습니다. 파일 형식·크기·셀 수는 서버에서 검증합니다."));

    const input = el("input");
    input.type = "file";
    input.accept = ".xlsx";
    input.id = "upload-file";
    input.style.minHeight = "var(--control-h)";
    const label = el("label", null, "업로드할 파일");
    label.setAttribute("for", input.id);
    label.style.display = "block";
    label.style.marginBottom = "var(--sp-2)";

    const submit = el("button", "btn btn--primary", "업로드하고 검증");
    submit.type = "button";
    submit.disabled = true;
    input.addEventListener("change", () => {
      submit.disabled = !input.files?.length;
    });
    submit.addEventListener("click", () =>
      this.runUpload(pane, input.files[0]));

    const form = el("div");
    form.style.display = "grid";
    form.style.gap = "var(--sp-3)";
    form.style.maxWidth = "52ch";
    form.append(label, input, submit);
    pane.append(form);
  }

  async runUpload(pane, file) {
    pane.replaceChildren(loadingScreen("업로드와 검증 결과"));
    try {
      const up = await api.upload(file);
      const uploadId = up.upload.upload_id;
      const validation = await api.validate(uploadId);
      this.renderValidation(pane, up, validation);
      await this.refresh();
    } catch (err) {
      pane.replaceChildren(errorScreen({
        body: err.message,
        detail: err instanceof ApiError ? err.info : undefined,
        onRetry: () => this.renderUploadForm(pane),
      }));
    }
  }

  renderValidation(pane, up, validation) {
    pane.replaceChildren();
    const head = el("div", "tabpanel__head");
    head.append(el("h3", "tabpanel__title", "검증 결과"));
    head.append(el("span", "tabpanel__source", up.upload.display_name));
    pane.append(head);

    const dl = el("dl", "deflist");
    for (const [k, v] of [
      ["오류", String(validation.counts.error)],
      ["경고", String(validation.counts.warning)],
      ["정보", String(validation.counts.info)],
      ["양식 버전", validation.template_version_in_file || "확인 불가"],
    ]) {
      const row = el("div");
      row.append(el("dt", null, k), el("dd", null, v));
      dl.append(row);
    }
    pane.append(dl);

    if (validation.blocking) {
      pane.append(errorScreen({
        title: "검증 오류가 있어 분석을 진행할 수 없습니다",
        body: "아래 오류를 고친 뒤 다시 업로드하세요.",
        detail: { code: "validation_has_errors" },
        onRetry: () => this.renderUploadForm(pane),
      }));
      const ul = el("ul", "screen__list");
      for (const f of validation.findings.filter((x) => x.severity === "error")) {
        ul.append(el("li", null,
          `${f.sheet} ${f.row}행 ${f.column || ""} — ${f.message}`));
      }
      pane.append(ul);
      return;
    }

    const next = el("button", "btn btn--primary", "평가 대상 선택으로");
    next.type = "button";
    next.addEventListener("click", () =>
      this.openSubjects(up.upload.upload_id));
    pane.append(next);
  }

  /* ── 최근 분석 / 기업 데이터 ──────────────────────────────────── */
  openRecent(which) {
    const title = which === "recent" ? "최근 분석" : "기업 데이터";
    this.wm.open({
      key: which,
      title,
      width: 720, height: 420,
      render: (body) => {
        const pane = el("div", "tabpanel");
        body.append(pane);
        pane.append(loadingScreen(title));
        this.fillRecent(pane, title);
      },
    });
  }

  async fillRecent(pane, title) {
    try {
      const res = await api.listUploads();
      pane.replaceChildren();
      const head = el("div", "tabpanel__head");
      head.append(el("h3", "tabpanel__title", title));
      pane.append(head);

      if (!res.uploads?.length) {
        pane.append(emptyScreen({
          title: "업로드한 자료가 없습니다",
          body: "엑셀을 업로드하면 여기에 표시됩니다.",
          actions: [{ label: "엑셀 업로드", primary: true,
                      onClick: () => this.activate("upload") }],
        }));
        return;
      }
      for (const u of res.uploads) {
        const row = el("div");
        row.style.display = "flex";
        row.style.flexWrap = "wrap";
        row.style.alignItems = "center";
        row.style.gap = "var(--sp-3)";
        row.style.padding = "var(--sp-2) 0";
        row.style.borderBottom = "1px solid var(--line-100)";
        row.append(el("span", null, u.display_name));
        row.append(el("span", "tabpanel__source", u.uploaded_at));
        const open = el("button", "btn", "평가 대상 선택");
        open.type = "button";
        open.addEventListener("click", () => this.openSubjects(u.upload_id));
        row.append(open);
        pane.append(row);
      }
    } catch (err) {
      pane.replaceChildren(errorScreen({
        body: err.message,
        detail: err instanceof ApiError ? err.info : undefined,
        onRetry: () => this.fillRecent(pane, title),
      }));
    }
  }

  openReports() {
    this.wm.open({
      key: "reports",
      title: "보고서",
      width: 640, height: 380,
      render: (body) => {
        const pane = el("div", "tabpanel");
        pane.append(insufficientScreen({
          title: "보고서 계층 미구현",
          body: "보고서는 화면과 같은 평가 실행을 참조해야 합니다. "
              + "지표 계산·판정이 동작하기 전에는 만들지 않습니다.",
          requiredSources: ["metrics 계층", "rules_engine 판정 규칙 확보"],
        }));
        body.append(pane);
      },
    });
  }

  /* ── 평가 대상 선택 → 분석 창 ─────────────────────────────────── */
  openSubjects(uploadId) {
    this.wm.open({
      key: `subjects:${uploadId}`,
      title: "평가 대상 선택",
      width: 860, height: 480,
      render: (body) => {
        const pane = el("div", "tabpanel");
        body.append(pane);
        pane.append(loadingScreen("평가 대상 후보"));
        this.fillSubjects(pane, uploadId);
      },
    });
  }

  async fillSubjects(pane, uploadId) {
    try {
      await api.mapping(uploadId);
      const res = await api.subjects(uploadId);
      pane.replaceChildren();
      const head = el("div", "tabpanel__head");
      head.append(el("h3", "tabpanel__title", "평가 대상 선택"));
      head.append(el("span", "tabpanel__source", res.evaluation_unit));
      pane.append(head);

      if (!res.count) {
        pane.append(emptyScreen({
          title: "평가 대상이 없습니다",
          body: "수출예정거래 시트에 행이 없습니다.",
        }));
        return;
      }
      for (const s of res.subjects) {
        const row = el("div");
        row.style.display = "flex";
        row.style.flexWrap = "wrap";
        row.style.alignItems = "center";
        row.style.gap = "var(--sp-3)";
        row.style.padding = "var(--sp-2) 0";
        row.style.borderBottom = "1px solid var(--line-100)";
        row.append(el("strong", null,
          `${s.model_name || s.product_id} → ${s.destination_country_code}`));
        row.append(el("span", "tabpanel__source", s.hs_code || "HS 미입력"));
        row.append(stateBadgeForMode(s));
        const open = el("button", "btn btn--primary", "분석 창 열기");
        open.type = "button";
        open.addEventListener("click", () =>
          this.openAnalysis(uploadId, s));
        row.append(open);
        pane.append(row);
      }
    } catch (err) {
      pane.replaceChildren(errorScreen({
        body: err.message,
        detail: err instanceof ApiError ? err.info : undefined,
        onRetry: () => this.fillSubjects(pane, uploadId),
      }));
    }
  }

  openAnalysis(uploadId, subject) {
    // 중복 실행 정책은 창 관리자가 처리한다 (같은 key → 기존 창 활성화)
    const key = `analysis:${uploadId}:${subject.subject_id}`;
    const title = `분석 — ${subject.model_name || subject.product_id} / `
                + `${subject.destination_country_code}`;
    const record = this.wm.open({
      key, title, width: 1000, height: 600,
      render: (body) => {
        const pane = el("div", "tabpanel");
        pane.append(loadingScreen("분석 결과"));
        body.append(pane);
      },
    });
    if (record.context) return;   // 이미 열려 있던 창
    this.fillAnalysis(record, uploadId, subject);
  }

  async fillAnalysis(record, uploadId, subject) {
    // 분석 기간을 임의로 정하지 않는다. 처음엔 필터 없이 평가 실행을 만들고,
    // 사용자가 기간을 지정하면 새 평가 실행이 만들어진다 (명세서 §9).
    const reanalyze = (filters) =>
      api.analyze(uploadId, subject.subject_id, filters);
    try {
      const run = await reanalyze({});
      renderAnalysisWindow(record.body, record, run, this.announce, reanalyze);
    } catch (err) {
      record.body.replaceChildren(errorScreen({
        body: err.message,
        detail: err instanceof ApiError ? err.info : undefined,
        onRetry: () => this.fillAnalysis(record, uploadId, subject),
      }));
    }
  }
}

function stateBadgeForMode(s) {
  const span = el("span", `state state--${
    s.analysis_mode === "market_exploration" ? "not_entered" : "actual"}`);
  const mark = el("span", "state-mark",
    s.analysis_mode === "market_exploration" ? "△" : "✓");
  mark.setAttribute("aria-hidden", "true");
  span.append(mark, el("span", null, s.analysis_mode_label));
  return span;
}
