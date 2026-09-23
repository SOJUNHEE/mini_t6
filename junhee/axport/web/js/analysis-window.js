/* 분석 창 내용 — 상단 맥락 + 분석 기간 + 책갈피 탭 + 탭 화면
 *
 * 메인(종합판정)은 design.md: 5개 항목만, 핵심 결과 1개 + 설명 1줄.
 * 나머지 탭은 서버가 조립한 상세 5구성(명세서 §8)을 그대로 그린다:
 *   ① 평가 대상과 기준일  ② 영역별 결과·핵심 수치  ③ 차트·상세 표
 *   ④ 판단 이유·계산식·근거 출처  ⑤ 미확인 사항·필요한 추가 자료·후속 조치
 *
 * 이 파일은 서버 응답(평가 실행 run)을 **읽어서 그린다.** 계산·판정을 하지
 * 않는다. 값이 없는 자리를 채우지 않는다 (명세서 §11, §5).
 *
 * 분석 기간을 바꾸면 서버가 **새 평가 실행**을 만든다. 화면은 먼저 로딩
 * 화면으로 비운 뒤 새 run 만 그린다. 이전 결과가 최신처럼 남지 않는다
 * (명세서 §9). 탭 전환은 run 을 바꾸지 않는다.
 *
 * 차트는 표와 같은 배열(chart.series === table.rows)을 그린다.
 * 화면에서 다시 계산하지 않는다 (명세서 §9 — 표 형태로도 확인).
 */

import { api, ApiError } from "./api.js";
import { BookmarkTabs, TABS } from "./bookmark-tabs.js";
import {
  dataClassBadge, el, errorScreen, fetchBadge, insufficientScreen,
  loadingScreen, stateBadge, withheldScreen,
} from "./screens.js";

const MAIN_ITEM_TO_TAB = {
  regulation: "export_control",
  market: "market",
  price: "tariff_origin",
  logistics: "supply_logistics",
  stability: "counterparty",
};

const SESSION_NOTE =
  "시연용 세션. 창의 맥락은 브라우저 메모리에만 있으며 기업 계정 저장이 아니다.";

/* ── 유틸 ─────────────────────────────────────────────────────────── */
function metricUnit(m) {
  const parts = [];
  if (m.currency) parts.push(m.currency);
  if (m.unit) parts.push(m.unit);
  if (m.amount_multiplier && m.amount_multiplier !== 1) {
    parts.push(`×${m.amount_multiplier}`);
  }
  return parts.join(" ");
}

function periodText(p) {
  if (!p || (!p.start && !p.end)) return "기간 미지정";
  return `${p.start || "?"} ~ ${p.end || "?"}`;
}

function dl(pairs) {
  const list = el("dl", "deflist");
  for (const [k, v] of pairs) {
    const row = el("div");
    row.append(el("dt", null, k));
    const dd = el("dd");
    if (v instanceof Node) dd.append(v); else dd.textContent = v ?? "미입력";
    row.append(dd);
    list.append(row);
  }
  return list;
}

function section(title, hint) {
  const wrap = el("section", "detail__section");
  const h = el("h4", "detail__title", title);
  wrap.append(h);
  if (hint) wrap.append(el("p", "detail__hint", hint));
  return wrap;
}

/* ── 상단 맥락 줄 — 기업·제품·HS·대상국·기준일 (design.md) ────────── */
function ctxItem(key, value, mono = false) {
  const wrap = el("div", "ctxbar__item");
  wrap.append(el("span", "ctxbar__key", key));
  const val = el("span", `ctxbar__val${mono ? " ctxbar__val--mono" : ""}`);
  val.textContent = value || "미입력";     // 추측해 채우지 않는다
  wrap.append(val);
  return wrap;
}

function contextBar(run) {
  const s = run.subject;
  const bar = el("header", "ctxbar");
  bar.setAttribute("aria-label", "평가 대상");
  bar.append(
    ctxItem("기업", s.company_id, true),
    ctxItem("제품", s.model_name ? `${s.model_name} (${s.product_id})` : s.product_id),
    ctxItem("HS", s.hs_code ? `${s.hs_code}${s.hs_version ? ` · ${s.hs_version}` : ""}` : "", true),
    ctxItem("대상국", s.destination_country_raw
      ? `${s.destination_country_raw} (${s.destination_country_code})`
      : s.destination_country_code, true),
    ctxItem("기준일", s.evaluation_base_date, true),
    ctxItem("평가 실행", `${run.run_id} (#${run.run_seq})`, true),
  );
  const mode = el("div", "ctxbar__item");
  mode.append(el("span", "ctxbar__key", "분석"));
  mode.append(stateBadge(
    run.analysis_mode === "market_exploration" ? "not_entered" : "actual",
    run.analysis_mode_label,
  ));
  bar.append(mode);
  return bar;
}

/* ── 분석 기간 필터 — 공통 조건. 바꾸면 새 평가 실행 ──────────────── */
function periodBar(run, onChange) {
  const bar = el("form", "periodbar");
  bar.setAttribute("aria-label", "분석 기간 (공통 조건)");
  const current = run.filters?.analysis_period || {};

  const mk = (id, label, value) => {
    const wrap = el("label", "periodbar__field");
    wrap.setAttribute("for", id);
    wrap.append(el("span", null, label));
    const input = el("input");
    input.type = "month"; input.id = id; input.value = value || "";
    input.required = true;
    wrap.append(input);
    return [wrap, input];
  };
  const [w1, start] = mk(`p-start-${run.run_id}`, "시작", current.start);
  const [w2, end] = mk(`p-end-${run.run_id}`, "종료", current.end);
  const btn = el("button", "btn btn--primary", "이 기간으로 다시 평가");
  btn.type = "submit";
  const note = el("span", "tabpanel__source",
    "기간을 바꾸면 새 평가 실행(run)이 만들어집니다. 이전 결과는 보관되고 "
    + "화면에는 새 실행만 표시됩니다.");
  bar.append(w1, w2, btn, note);
  bar.addEventListener("submit", (e) => {
    e.preventDefault();
    if (!start.value || !end.value) return;
    onChange({ analysis_period: { start: start.value, end: end.value } });
  });
  return bar;
}

/* ── 메인 종합판정 ─────────────────────────────────────────────── */
function overallPanel(run, panel, tabs) {
  const o = run.result.overall;

  if (run.subject.disclaimer) {
    const notice = el("div", "notice");
    notice.append(el("span", "notice__mark", "△"));
    notice.append(el("span", null, run.subject.disclaimer));
    panel.append(notice);
  }

  const verdict = el("div", "verdict");
  verdict.append(el("span", "verdict__label", "종합"));
  verdict.append(el("strong", "verdict__value", o.decision_label));
  verdict.append(el("span", "verdict__note", o.disclaimer));
  panel.append(verdict);

  const grid = el("div", "summary");
  grid.setAttribute("role", "list");
  for (const item of run.main_summary) {           // 서버가 준 5개만
    const card = el("article", "card");
    card.setAttribute("role", "listitem");
    const head = el("div", "card__head");
    head.append(el("h4", "card__title", item.label));
    head.append(stateBadge(item.state));
    head.append(el("span", "card__layer",
      item.layer === "mandatory_review" ? "1층" : "2층"));
    card.append(head);
    card.append(el("div", "card__headline", item.headline));
    card.append(el("p", "card__note", item.note || ""));
    const tabId = MAIN_ITEM_TO_TAB[item.item];
    if (tabId) {
      const more = el("button", "card__more", "근거 보기");
      more.type = "button";
      more.addEventListener("click", () => tabs.select(tabId));
      card.append(more);
    }
    grid.append(card);
  }
  panel.append(grid);

  const scope = run.scope || {};
  panel.append(el("p", "tabpanel__source",
    `지표 계산 범위: 검증완료 API ${scope.verified_api_count ?? "?"}개 · `
    + `계산에 쓸 수 있는 파일 자료 ${scope.file_usable_for_metrics ?? "?"}/`
    + `${scope.file_total ?? "?"}개. 상세는 오른쪽 책갈피 탭.`));
}

/* ── 차트 (인라인 SVG) — 표와 같은 배열을 그린다 ───────────────── */
function chartSvg(chart) {
  const series = chart.series || [];
  const keys = chart.y_keys || [];
  const W = 640, H = 220, padL = 56, padB = 34, padT = 14, padR = 12;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("class", "chart");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label",
    `${chart.title} 차트. 같은 값을 아래 표에서 확인할 수 있습니다.`);

  // 숫자 문자열을 그리기 위해서만 Number 로 바꾼다. 값을 저장하지 않는다.
  const nums = series.flatMap((r) => keys.map((k) => Number(r[k])))
    .filter((n) => Number.isFinite(n));
  if (!series.length || !nums.length) {
    const t = document.createElementNS(svg.namespaceURI, "text");
    t.setAttribute("x", W / 2); t.setAttribute("y", H / 2);
    t.setAttribute("text-anchor", "middle");
    t.setAttribute("class", "chart__empty");
    t.textContent = "표시할 값이 없습니다";
    svg.append(t);
    return svg;
  }
  const max = Math.max(...nums, 0), min = Math.min(...nums, 0);
  const span = (max - min) || 1;
  const plotW = W - padL - padR, plotH = H - padT - padB;
  const x = (i) => padL + (series.length === 1 ? plotW / 2
    : (i / (series.length - 1)) * plotW);
  const y = (v) => padT + plotH - ((v - min) / span) * plotH;

  const axis = document.createElementNS(svg.namespaceURI, "path");
  axis.setAttribute("d", `M${padL},${padT}V${padT + plotH}H${W - padR}`);
  axis.setAttribute("class", "chart__axis");
  svg.append(axis);

  const zero = document.createElementNS(svg.namespaceURI, "line");
  zero.setAttribute("x1", padL); zero.setAttribute("x2", W - padR);
  zero.setAttribute("y1", y(0)); zero.setAttribute("y2", y(0));
  zero.setAttribute("class", "chart__zero");
  svg.append(zero);

  const classes = ["chart__s1", "chart__s2", "chart__s3"];
  keys.forEach((k, ki) => {
    if (chart.type === "bar") {
      const bw = Math.max(4, plotW / (series.length * (keys.length + 1)));
      series.forEach((r, i) => {
        const v = Number(r[k]);
        if (!Number.isFinite(v)) return;
        const rect = document.createElementNS(svg.namespaceURI, "rect");
        rect.setAttribute("x", x(i) - (bw * keys.length) / 2 + ki * bw);
        rect.setAttribute("y", Math.min(y(v), y(0)));
        rect.setAttribute("width", bw);
        rect.setAttribute("height", Math.abs(y(v) - y(0)));
        rect.setAttribute("class", classes[ki % classes.length]);
        svg.append(rect);
      });
    } else {
      const d = series.map((r, i) => {
        const v = Number(r[k]);
        return Number.isFinite(v) ? `${i ? "L" : "M"}${x(i)},${y(v)}` : "";
      }).join("");
      const path = document.createElementNS(svg.namespaceURI, "path");
      path.setAttribute("d", d);
      path.setAttribute("class", `chart__line ${classes[ki % classes.length]}`);
      svg.append(path);
      series.forEach((r, i) => {
        const v = Number(r[k]);
        if (!Number.isFinite(v)) return;
        const c = document.createElementNS(svg.namespaceURI, "circle");
        c.setAttribute("cx", x(i)); c.setAttribute("cy", y(v));
        c.setAttribute("r", 3);
        c.setAttribute("class", classes[ki % classes.length]);
        svg.append(c);
      });
    }
  });

  series.forEach((r, i) => {
    if (series.length > 12 && i % Math.ceil(series.length / 12)) return;
    const t = document.createElementNS(svg.namespaceURI, "text");
    t.setAttribute("x", x(i)); t.setAttribute("y", H - 10);
    t.setAttribute("text-anchor", "middle");
    t.setAttribute("class", "chart__tick");
    t.textContent = String(r[chart.x_key] ?? "");
    svg.append(t);
  });
  [min, max].forEach((v) => {
    const t = document.createElementNS(svg.namespaceURI, "text");
    t.setAttribute("x", padL - 6); t.setAttribute("y", y(v) + 4);
    t.setAttribute("text-anchor", "end");
    t.setAttribute("class", "chart__tick");
    t.textContent = v.toLocaleString("ko-KR");
    svg.append(t);
  });
  return svg;
}

function dataTable(table) {
  const wrap = el("div", "tablewrap");
  const t = el("table", "datatable");
  const cap = el("caption", null, table.title || table.table_id);
  t.append(cap);
  const thead = el("thead"); const tr = el("tr");
  for (const c of table.columns) {
    const th = el("th", null, c.label
      + (c.currency ? ` (${c.currency})` : "")
      + (c.unit ? ` (${c.unit})` : ""));
    th.scope = "col";
    tr.append(th);
  }
  thead.append(tr); t.append(thead);
  const tbody = el("tbody");
  if (!table.rows?.length) {
    const r = el("tr"); const td = el("td", "datatable__empty", "행 없음");
    td.colSpan = table.columns.length; r.append(td); tbody.append(r);
  }
  for (const row of table.rows || []) {
    const r = el("tr");
    for (const c of table.columns) {
      const v = row[c.key];
      const td = el("td", null,
        v === null || v === undefined || v === "" ? "미입력"
          : typeof v === "boolean" ? (v ? "예" : "아니오") : String(v));
      if (v === null || v === undefined || v === "") td.classList.add("is-missing");
      r.append(td);
    }
    tbody.append(r);
  }
  t.append(tbody); wrap.append(t);
  return wrap;
}

/* ── 상세 5구성 ────────────────────────────────────────────────── */
function detailPanel(run, tabId, panel) {
  const d = run.tab_details?.[tabId];
  if (!d) {
    panel.append(withheldScreen({ body: "이 탭의 서버 결과가 없습니다." }));
    return;
  }

  // ① 평가 대상과 기준일
  const s1 = section("① 평가 대상과 기준일");
  const sub = d.subject;
  s1.append(dl([
    ["제품", sub.model_name ? `${sub.model_name} (${sub.product_id})` : sub.product_id],
    ["HS", sub.hs_code ? `${sub.hs_code} · ${sub.hs_version || "버전 미입력"}` : null],
    ["대상국", sub.destination_country_code],
    ["평가 기준일", sub.evaluation_base_date],
    ["분석 기간", periodText(sub.analysis_period)],
    ["분석 모드", sub.analysis_mode_label],
  ]));
  panel.append(s1);

  // ② 영역별 결과·핵심 수치
  const s2 = section("② 영역별 결과·핵심 수치",
    "모든 지표에 통화·단위·기간이 붙습니다. 값이 없으면 상태로 표시합니다.");
  const head = el("div", "detail__state");
  head.append(stateBadge(d.results.state,
    d.results.display_label || undefined));
  if (d.results.reason_code) head.append(el("code", null, d.results.reason_code));
  s2.append(head);
  if (d.results.metrics?.length) {
    const grid = el("div", "metrics");
    for (const m of d.results.metrics) {
      const card = el("div", "metric");
      card.append(el("div", "metric__label", m.label));
      if (m.state === "actual") {
        const v = el("div", "metric__value");
        v.append(el("strong", null, m.display?.text ?? String(m.value)));
        v.append(el("span", "metric__unit", metricUnit(m)));
        card.append(v);
      } else {
        card.append(stateBadge(m.state, m.display_label));
      }
      const meta = el("div", "metric__meta");
      meta.append(el("span", null, periodText(m.period)));
      if (m.data_class) meta.append(dataClassBadge(m.data_class, m.data_class_label));
      if (m.display?.rounding_policy) {
        meta.append(el("span", "tabpanel__source",
          `반올림 정책 ${m.display.rounding_policy}${m.display.rounded ? "" : " · 원값"}`));
      }
      card.append(meta);
      if (m.required_inputs?.length) {
        const ul = el("ul", "screen__list");
        for (const r of m.required_inputs) ul.append(el("li", null, r));
        card.append(ul);
      }
      grid.append(card);
    }
    s2.append(grid);
  } else {
    s2.append(d.results.state === "not_evaluated"
      ? withheldScreen({ body: d.reasoning?.text,
                         reasons: d.open_items?.required_sources || [] })
      : insufficientScreen({ body: d.reasoning?.text,
                             requiredInputs: d.open_items?.required_inputs || [] }));
  }
  panel.append(s2);

  // ③ 차트·상세 표
  const s3 = section("③ 차트·상세 표",
    "차트와 표는 같은 값을 씁니다. 차트를 표로도 확인할 수 있습니다.");
  if (d.chart) {
    const toggle = el("div", "detail__toggle");
    const bChart = el("button", "btn", "차트로 보기");
    const bTable = el("button", "btn", "표로 보기");
    bChart.type = bTable.type = "button";
    const chartBox = el("div", "chartbox");
    chartBox.append(el("h5", "chartbox__title",
      `${d.chart.title}${d.chart.currency ? ` (${d.chart.currency})` : ""} · ${periodText(d.chart.period)}`));
    chartBox.append(chartSvg(d.chart));
    const linked = (d.tables || []).find((t) => t.table_id === d.chart.table_ref);
    const tableBox = linked ? dataTable(linked) : el("p", null, "연결된 표 없음");
    const setMode = (mode) => {
      bChart.setAttribute("aria-pressed", String(mode === "chart"));
      bTable.setAttribute("aria-pressed", String(mode === "table"));
      chartBox.hidden = mode !== "chart";
      tableBox.hidden = mode !== "table";
    };
    bChart.addEventListener("click", () => setMode("chart"));
    bTable.addEventListener("click", () => setMode("table"));
    toggle.append(bChart, bTable);
    s3.append(toggle, chartBox, tableBox);
    setMode("chart");
    for (const t of d.tables || []) {
      if (t.table_id !== d.chart.table_ref) s3.append(dataTable(t));
    }
  } else if (d.tables?.length) {
    for (const t of d.tables) s3.append(dataTable(t));
  } else {
    s3.append(el("p", "detail__none", "표시할 차트·표가 없습니다 (값이 계산되지 않았습니다)."));
  }
  panel.append(s3);

  // ④ 판단 이유·계산식·근거 출처
  const s4 = section("④ 판단 이유·계산식·근거 출처");
  if (d.reasoning?.text) s4.append(el("p", "detail__text", d.reasoning.text));
  if (d.reasoning?.formulas?.length) {
    const ul = el("ul", "formulas");
    for (const f of d.reasoning.formulas) {
      const li = el("li");
      li.append(el("code", null, f.metric_id), el("span", null, " = "),
                el("code", null, f.formula));
      ul.append(li);
    }
    s4.append(ul);
  }
  for (const src of d.reasoning?.sources || []) {
    const box = el("div", "source");
    const line = el("div", "source__head");
    line.append(el("strong", null, src.api_name || src.path || src.source_id || "출처"));
    if (src.fetch_result) line.append(fetchBadge(src.fetch_result));
    if (src.data_class) line.append(dataClassBadge(src.data_class, src.data_class_label));
    if (src.verified) line.append(el("span", "tabpanel__source", `검증: ${src.verified}`));
    box.append(line);
    const pairs = [];
    if (src.endpoint) pairs.push(["엔드포인트", src.endpoint]);
    if (src.query) pairs.push(["조회 조건", JSON.stringify(src.query)]);
    if (src.period) pairs.push(["기간", periodText(src.period)]);
    if (src.currency) pairs.push(["통화", src.currency]);
    if (src.hs_granularity_used) pairs.push(["HS 조회 단위", src.hs_granularity_used]);
    if (src.fetched_at) pairs.push(["조회 시각(UTC)", src.fetched_at]);
    if (src.cache) {
      pairs.push(["저장 자료 사용", src.cache.hit ? `예 (경과 ${src.cache.age_days ?? "?"}일)` : "아니오"]);
      pairs.push(["최대 허용 경과", src.cache.max_age_policy === "미정" ? "정책 미정 — 초과 판정 안 함"
        : (src.cache.max_age_exceeded ? "초과" : "이내")]);
    }
    if (src.error_code) pairs.push(["오류", `${src.error_code} ${src.error_message || ""}`]);
    if (pairs.length) box.append(dl(pairs));
    s4.append(box);
  }
  const eng = run.engine || {};
  s4.append(dl([
    ["규칙 버전", eng.rule_set_version ?? "미정"],
    ["계산 엔진 버전", eng.calc_engine_version ?? "미정"],
    ["점수 설정 버전", eng.scoring_config_version ?? "미정"],
    ["양식 버전", eng.template_version ?? "미정"],
    ["실행 시각(UTC)", run.executed_at],
  ]));
  panel.append(s4);

  // ⑤ 미확인 사항·필요한 추가 자료·후속 조치
  const s5 = section("⑤ 미확인 사항·필요한 추가 자료·후속 조치");
  const oi = d.open_items || {};
  const groups = [
    ["미확인 사항", oi.unconfirmed], ["필요한 입력", oi.required_inputs],
    ["필요한 자료", oi.required_sources], ["후속 조치", oi.next_actions],
  ];
  for (const [label, items] of groups) {
    const box = el("div", "openitem");
    box.append(el("h5", "openitem__title", label));
    if (items?.length) {
      const ul = el("ul", "screen__list");
      for (const i of items) ul.append(el("li", null, i));
      box.append(ul);
    } else {
      box.append(el("p", "detail__none", "없음"));
    }
    s5.append(box);
  }
  panel.append(s5);
}

/* ── 보고서·AI 작업줄 ──────────────────────────────────────────── */
function actionBar(run, announce) {
  const bar = el("div", "actionbar");
  const status = el("span", "tabpanel__source", "");

  const rep = el("button", "btn", "보고서 만들기 (같은 평가 실행)");
  rep.type = "button";
  rep.addEventListener("click", async () => {
    rep.disabled = true; status.textContent = "보고서 생성 중…";
    try {
      const out = await api.createReport(run.run_id);
      status.replaceChildren();
      status.append(el("span", null, `보고서 ${out.report_id} · run ${out.run_id} · `));
      const a = el("a", null, "CSV 내려받기 (수식 주입 방어 적용)");
      a.href = `/reports/${out.report_id}/download.csv`;
      a.setAttribute("download", `${out.report_id}.csv`);
      status.append(a);
      announce("보고서를 만들었습니다.");
    } catch (err) {
      status.textContent = `보고서 실패: ${err.message}`;
    } finally { rep.disabled = false; }
  });

  const ai = el("button", "btn", "AI 설명 미리보기 (전송 대상 확인)");
  ai.type = "button";
  const aiBox = el("div", "aibox"); aiBox.hidden = true;
  ai.addEventListener("click", async () => {
    ai.disabled = true; aiBox.hidden = false;
    aiBox.replaceChildren(loadingScreen("AI 전송 정책"));
    try {
      const out = await api.aiExplain(run.run_id, true);
      aiBox.replaceChildren();
      aiBox.append(el("h5", "openitem__title", "AI 설명 — 상태"));
      aiBox.append(stateBadge(out.state, out.display_label));
      aiBox.append(el("p", "detail__text", `${out.reason_code}: ${out.note || ""}`));
      const p = out.policy || {};
      aiBox.append(dl([
        ["활성화", p.enabled ? "예" : "아니오"],
        ["공급자 / 모델", `${p.provider ?? "미정"} / ${p.model ?? "미정"}`],
        ["요청 상한 / 비용 상한", `${p.max_requests_per_run ?? "미정"} / ${p.monthly_cost_cap ?? "미정"}`],
        ["미정 항목", (p.undecided || []).join(", ") || "없음"],
        ["전송 대상 수", out.payload_preview?.fact_count == null ? "확인 불가" : String(out.payload_preview.fact_count)],
        ["제외된 항목 수", out.payload_preview?.skipped_denied_count == null ? "확인 불가" : String(out.payload_preview.skipped_denied_count)],
      ]));
      aiBox.append(el("p", "tabpanel__source",
        "AI 는 이미 산출된 결과를 설명만 합니다. 수치·판정을 만들지 않습니다. "
        + "아래는 실제 전송될 최소 항목입니다."));
      const pre = el("pre", "aibox__pre",
        JSON.stringify(out.payload_preview?.facts || {}, null, 1));
      aiBox.append(pre);
      if (out.text) aiBox.append(el("p", "detail__text", out.text));
    } catch (err) {
      aiBox.replaceChildren(errorScreen({
        body: err.message, detail: err instanceof ApiError ? err.info : undefined }));
    } finally { ai.disabled = false; }
  });

  bar.append(rep, ai, status);
  const wrap = el("div");
  wrap.append(bar, aiBox);
  return wrap;
}

/* ── 창 내용 조립 ──────────────────────────────────────────────── */
export function renderAnalysisWindow(body, record, run, announce, reanalyze) {
  body.replaceChildren();
  body.append(contextBar(run));
  if (run.environment?.demo_mode) {
    const n = el("div", "notice notice--demo");
    n.setAttribute("role", "note");
    n.append(el("span", "notice__mark", "◌"));
    n.append(el("span", null,
      `${run.environment.label}. 지표마다 붙은 배지로 실제 자료(●)·사용자 입력(◐)·`
      + "시연 데이터(◌)·가정값(◇)을 구분합니다."));
    body.append(n);
  }

  if (run.filters && Object.keys(run.filters).length === 0
      || !run.filters?.analysis_period) {
    const n = el("div", "notice");
    n.append(el("span", "notice__mark", "△"));
    n.append(el("span", null,
      "분석 기간이 지정되지 않아 외부 실적을 조회하지 않았습니다. "
      + "기간을 임의로 정하지 않습니다. 아래에서 기간을 지정하면 새 평가 실행이 만들어집니다."));
    body.append(n);
  }

  body.append(periodBar(run, async (filters) => {
    // 이전 결과를 최신처럼 남기지 않는다: 먼저 비우고 새 run 만 그린다
    body.replaceChildren(loadingScreen("새 평가 실행"));
    record.context = null;
    try {
      const next = await reanalyze(filters);
      renderAnalysisWindow(body, record, next, announce, reanalyze);
      announce(`새 평가 실행 ${next.run_id} 을 표시합니다.`);
    } catch (err) {
      body.replaceChildren(errorScreen({
        body: err.message, detail: err instanceof ApiError ? err.info : undefined,
        onRetry: () => renderAnalysisWindow(body, record, run, announce, reanalyze),
      }));
    }
  }));

  const split = el("div", "split");
  const panel = el("div", "tabpanel");
  panel.id = `panel-${record.key}`;
  panel.setAttribute("role", "tabpanel");
  panel.tabIndex = 0;
  const tabsMount = el("div");
  split.append(panel, tabsMount);
  body.append(split);
  body.append(actionBar(run, announce));

  const tabs = new BookmarkTabs({
    mount: tabsMount, panel, announce,
    renderPanel: (tabId, target) => {
      const label = TABS.find((t) => t.id === tabId).label;
      const head = el("div", "tabpanel__head");
      head.append(el("h3", "tabpanel__title", label));
      head.append(el("span", "tabpanel__source",
        tabId === "overall" ? "result.overall + main_summary"
          : `tab_details.${tabId}`));
      target.append(head);
      if (tabId === "overall") overallPanel(run, target, tabs);
      else detailPanel(run, tabId, target);
    },
  });

  // 창이 들고 있는 평가 맥락. 탭 전환이 이 값을 바꾸지 않는다.
  // 시연용 세션 상태(브라우저 메모리)이며 기업 계정 저장이 아니다 (명세서 §10).
  record.context = {
    session_note: SESSION_NOTE,
    run_id: run.run_id,
    upload_id: run.upload_id,
    company_id: run.subject.company_id,
    product_id: run.subject.product_id,
    destination_country_code: run.subject.destination_country_code,
    subject_id: run.subject.subject_id,
    evaluation_base_date: run.subject.evaluation_base_date,
    filters: run.filters,
  };
  record.tabs = tabs;
  return tabs;
}
