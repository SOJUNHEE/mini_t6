"""§13-6 검증 — 검증된 범위의 실제 분석·보고서·AI 설명.

네트워크·키 없이 돈다 (stub_customs). 실제 외부 호출은 -m external.
"""

from __future__ import annotations

import csv
import io
import json

import pytest

from tests.conftest import (CANNED_ROWS, EMPTY_XML, ERROR_XML, PERIOD,
                            canned_xml)


@pytest.fixture()
def analyzed(ctx, clean_workbook, stub_customs):
    from axport.upload_validation import pipeline as P

    res = P.ingest(ctx, clean_workbook.read_bytes(), "clean.xlsx")
    uid = res["upload"]["upload_id"]
    P.run_validation(ctx, uid)
    P.run_mapping(ctx, uid)
    subjects = P.list_subjects(ctx, uid)
    sid = next(s["subject_id"] for s in subjects["subjects"]
               if s["product_id"] == "P-001")
    run = P.analyze(ctx, uid, sid, filters={"analysis_period": PERIOD})
    return ctx, uid, sid, run


def _metrics(run, tab):
    return run["tab_details"][tab]["results"]["metrics"]


# ── 범위 제한: 검증완료 소스만 (명세서 §13-6) ──────────────────────────
def test_only_verified_sources_feed_metrics(analyzed):
    _, _, _, run = analyzed
    assert run["scope"]["verified_api_count"] == 2
    assert run["scope"]["file_usable_for_metrics"] == 0   # MANIFEST 검증완료 0건
    for src in run["external_sources"]:
        if src["fetch_result"] in ("ok", "stale_cache_used"):
            assert src["verified"] == "검증완료"
    for tab, d in run["tab_details"].items():
        for m in d["results"]["metrics"]:
            if m["state"] == "actual":
                assert m["data_class"] in ("real", "user_input"), (tab, m)
                assert not str(m.get("source_id", "")).startswith("file:")


def test_unverified_tabs_show_no_values(analyzed):
    _, _, _, run = analyzed
    for tab in ("tariff_origin", "counterparty", "profit_fx",
                "supply_logistics"):
        d = run["tab_details"][tab]
        assert d["results"]["state"] == "not_evaluated"
        assert d["results"]["reason_code"] == "source_not_verified"
        assert d["results"]["metrics"] == []
        assert d["chart"] is None
        assert d["open_items"]["required_sources"]


# ── 5구성 (명세서 §8) ─────────────────────────────────────────────────
def test_every_tab_has_five_sections(analyzed):
    _, _, _, run = analyzed
    for tab in run["tab_order"]:
        if tab == "overall":
            continue
        d = run["tab_details"][tab]
        for key in ("subject", "results", "chart", "tables",
                    "reasoning", "open_items"):
            assert key in d, (tab, key)
        assert d["subject"]["evaluation_base_date"]
        assert d["subject"]["analysis_period"] == PERIOD
        for key in ("unconfirmed", "required_inputs",
                    "required_sources", "next_actions"):
            assert key in d["open_items"], (tab, key)


# ── 통화·단위·기간 + 계산/반올림 분리 (명세서 §4) ─────────────────────
def test_every_actual_metric_has_unit_or_currency_and_period(analyzed):
    _, _, _, run = analyzed
    for tab, d in run["tab_details"].items():
        for m in d["results"]["metrics"]:
            if m["state"] != "actual":
                continue
            assert m.get("currency") or m.get("unit"), (tab, m["metric_id"])
            assert m.get("period"), (tab, m["metric_id"])
            assert m.get("formula"), (tab, m["metric_id"])
            assert m.get("data_class"), (tab, m["metric_id"])


def test_calculation_and_display_are_separate(analyzed):
    _, _, _, run = analyzed
    m = next(x for x in _metrics(run, "market")
             if x["metric_id"] == "kr_export_amount")
    assert m["value"] == "300"                 # 계산값: 100 + 200, 문자열
    assert m["display"]["text"] == "300"
    assert m["display"]["rounding_policy"] == "미정"
    assert m["display"]["rounded"] is False
    avg = next(x for x in _metrics(run, "market")
               if x["metric_id"] == "kr_export_avg_monthly")
    assert avg["value"] == "150"
    assert avg["currency"] == "USD"


def test_chart_and_table_share_the_same_rows(analyzed):
    """차트는 표 형태로도 확인할 수 있다 (명세서 §9)."""
    _, _, _, run = analyzed
    d = run["tab_details"]["market"]
    chart = d["chart"]
    table = next(t for t in d["tables"] if t["table_id"] == chart["table_ref"])
    assert chart["series"] == table["rows"]
    assert [r["period"] for r in table["rows"]] == ["2026.01", "2026.02"]
    assert table["rows"][0]["export_amount"] == "100"
    cur_cols = [c for c in table["columns"] if c.get("currency")]
    assert cur_cols and all(c["currency"] == "USD" for c in cur_cols)


def test_total_row_is_excluded(analyzed):
    _, _, _, run = analyzed
    src = run["external_sources"][0]
    assert src["row_count"] == 2                 # 총계 제외
    assert any(r["is_total"] for r in src["rows"])


def test_hs_broadening_is_disclosed(analyzed):
    """10자리로 자료가 없어 6자리로 조회한 사실을 숨기지 않는다."""
    _, _, _, run = analyzed
    d = run["tab_details"]["market"]
    src = run["external_sources"][0]
    assert src["requested_hs"] == "8542320000"
    assert src["hs_broadened"] is True
    assert any("넓은 범위" in u for u in d["open_items"]["unconfirmed"])


# ── 외부 자료 상태 구분 (명세서 §7) ───────────────────────────────────
def test_no_data_is_reported_not_zero(ctx, clean_workbook, stub_customs):
    from axport.upload_validation import pipeline as P

    stub_customs["body"] = EMPTY_XML
    res = P.ingest(ctx, clean_workbook.read_bytes(), "c.xlsx")
    uid = res["upload"]["upload_id"]
    P.run_validation(ctx, uid); P.run_mapping(ctx, uid)
    sid = next(s["subject_id"] for s in P.list_subjects(ctx, uid)["subjects"]
               if s["product_id"] == "P-001")
    run = P.analyze(ctx, uid, sid, filters={"analysis_period": PERIOD})
    src = run["external_sources"][0]
    assert src["fetch_result"] == "no_data"
    for m in _metrics(run, "market"):
        assert m["state"] == "not_entered"
        assert "value" not in m
        assert m["display_label"] == "자료 부족"


def test_permission_error_is_fetch_failed(ctx, clean_workbook, stub_customs):
    from axport.upload_validation import pipeline as P

    stub_customs["body"] = ERROR_XML
    res = P.ingest(ctx, clean_workbook.read_bytes(), "c.xlsx")
    uid = res["upload"]["upload_id"]
    P.run_validation(ctx, uid); P.run_mapping(ctx, uid)
    sid = next(s["subject_id"] for s in P.list_subjects(ctx, uid)["subjects"]
               if s["product_id"] == "P-001")
    run = P.analyze(ctx, uid, sid, filters={"analysis_period": PERIOD})
    src = run["external_sources"][0]
    assert src["fetch_result"] == "no_permission"
    assert src["error_code"] == "30"
    for m in _metrics(run, "market"):
        assert m["state"] == "fetch_failed"
        assert m["display_label"] == "조회 실패"
    assert run["tab_details"]["market"]["chart"]["series"] == []


def test_connection_failure_is_fetch_failed(ctx, clean_workbook, monkeypatch):
    from axport.external_data.providers import customs_trade as ct
    from axport.rules_engine import evaluate as E
    from axport.upload_validation import pipeline as P

    def boom(url, timeout):
        raise OSError("simulated network down")

    monkeypatch.setattr(ct, "_http_get", boom)
    monkeypatch.setattr(E, "_service_key", lambda *a, **k: "TEST")
    res = P.ingest(ctx, clean_workbook.read_bytes(), "c.xlsx")
    uid = res["upload"]["upload_id"]
    P.run_validation(ctx, uid); P.run_mapping(ctx, uid)
    sid = next(s["subject_id"] for s in P.list_subjects(ctx, uid)["subjects"]
               if s["product_id"] == "P-001")
    run = P.analyze(ctx, uid, sid, filters={"analysis_period": PERIOD})
    assert run["external_sources"][0]["fetch_result"] == "connection_failed"
    assert run["external_sources"][0]["data_class"] == "real"
    # 샘플로 대체하지 않았다
    assert all(m["state"] == "fetch_failed" for m in _metrics(run, "market"))


def test_stale_cache_is_flagged(ctx, clean_workbook, stub_customs, monkeypatch):
    """max_age 정책이 있고 초과했으면 stale_cache_used 로 표시한다."""
    import os

    from axport.config.settings import get_settings
    from axport.upload_validation import pipeline as P

    os.environ["AXPORT_EXTERNAL_DATA__MAX_AGE_DAYS_DEFAULT"] = "1"
    get_settings.cache_clear()
    ctx = P.build_context(get_settings())

    res = P.ingest(ctx, clean_workbook.read_bytes(), "c.xlsx")
    uid = res["upload"]["upload_id"]
    P.run_validation(ctx, uid); P.run_mapping(ctx, uid)
    sid = next(s["subject_id"] for s in P.list_subjects(ctx, uid)["subjects"]
               if s["product_id"] == "P-001")
    run1 = P.analyze(ctx, uid, sid, filters={"analysis_period": PERIOD})
    assert run1["external_sources"][0]["cache"]["hit"] is False

    # 캐시 파일의 fetched_at 을 10일 전으로 되돌린다
    cache_root = ctx.settings.resolve_path("storage.cache_dir")
    for f in cache_root.rglob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        d["fetched_at"] = "2020-01-01T00:00:00+00:00"
        f.write_text(json.dumps(d), encoding="utf-8")

    run2 = P.analyze(ctx, uid, sid, filters={"analysis_period": PERIOD,
                                             "_reason": "retry"})
    src = run2["external_sources"][0]
    assert src["fetch_result"] == "stale_cache_used"
    assert src["cache"]["max_age_exceeded"] is True
    assert any("경과" in u for u in
               run2["tab_details"]["market"]["open_items"]["unconfirmed"])
    os.environ.pop("AXPORT_EXTERNAL_DATA__MAX_AGE_DAYS_DEFAULT", None)
    get_settings.cache_clear()


def test_max_age_policy_undecided_is_stated(analyzed):
    _, _, _, run = analyzed
    src = run["external_sources"][0]
    assert src["cache"]["max_age_policy"] == "미정"
    assert src["cache"]["max_age_exceeded"] is None


# ── 사용자 입력 실적 ───────────────────────────────────────────────────
def test_upload_history_is_user_input_and_zero_kept(analyzed):
    _, _, _, run = analyzed
    d = run["tab_details"]["trade_history"]
    for m in d["results"]["metrics"]:
        if m["state"] == "actual":
            assert m["data_class"] == "user_input"
            assert m["data_class_label"] == "사용자 입력"
    cancelled = next(m for m in d["results"]["metrics"]
                     if m["metric_id"] == "upload_cancelled_count")
    assert cancelled["state"] == "actual" and cancelled["value"] == 0


# ── 평가 실행 보관 (명세서 §6) ────────────────────────────────────────
def test_run_is_sealed_and_retrievable(analyzed):
    from axport.upload_validation import pipeline as P

    ctx, uid, _, run = analyzed
    assert run["sealed"] is True
    _, stored = P.get_run(ctx, run["run_id"])
    assert stored["run_id"] == run["run_id"]
    assert stored["tab_details"]["market"]["results"]["metrics"] == \
        run["tab_details"]["market"]["results"]["metrics"]


def test_filter_change_creates_new_run_and_keeps_old(analyzed, stub_customs):
    """필터 변경 후 이전 결과가 최신처럼 남지 않는다 (명세서 §9)."""
    from axport.upload_validation import pipeline as P

    ctx, uid, sid, run1 = analyzed
    stub_customs["body"] = canned_xml([CANNED_ROWS[0], {
        **CANNED_ROWS[1], "period": "2025.06", "exp": "999"}])
    run2 = P.analyze(ctx, uid, sid, filters={
        "analysis_period": {"start": "2025-01", "end": "2025-12"}})
    assert run2["run_id"] != run1["run_id"]
    assert run2["input_fingerprint"] != run1["input_fingerprint"]
    assert run2["run_seq"] == run1["run_seq"] + 1
    v1 = _metrics(run1, "market")[0]["value"]
    v2 = _metrics(run2, "market")[0]["value"]
    assert v1 == "300" and v2 == "999"
    _, again = P.get_run(ctx, run1["run_id"])
    assert _metrics(again, "market")[0]["value"] == "300"   # 옛 실행 불변
    runs = P.list_runs(ctx, uid)["runs"]
    assert [r["run_id"] for r in runs] == [run1["run_id"], run2["run_id"]]


# ── 보고서 (명세서 §11, §5) ───────────────────────────────────────────
def test_report_matches_screen_and_does_not_recompute(analyzed, monkeypatch):
    from axport.external_data.providers import customs_trade as ct
    from axport.reports import builder
    from axport.upload_validation import pipeline as P

    ctx, _, _, run = analyzed
    _, screen = P.get_run(ctx, run["run_id"])

    # 보고서 생성 중 외부 호출이 일어나면 실패시킨다 → 재계산 없음 증명
    def forbidden(*a, **k):
        raise AssertionError("보고서 생성 중 외부 API 를 호출했다")
    monkeypatch.setattr(ct, "fetch", forbidden)

    report = builder.build(screen)
    assert report["run_id"] == screen["run_id"]

    screen_metrics = {
        (tab, m["metric_id"]): m
        for tab in screen["tab_order"]
        if tab in screen["tab_details"]
        for m in screen["tab_details"][tab]["results"]["metrics"]}
    report_metrics = {(m["tab_id"], m["metric_id"]): m
                      for m in report["metrics"]}
    assert set(screen_metrics) == set(report_metrics)
    for key, sm in screen_metrics.items():
        rm = report_metrics[key]
        assert str(sm.get("value", "")) == str(rm["value"])
        assert (sm.get("display") or {}).get("text", "") == rm["표시값"]
        assert (sm.get("currency") or "") == (rm["currency"] or "")
        assert (sm.get("unit") or "") == (rm["unit"] or "")
        assert sm["state"] == rm["state"]

    # CSV 도 같은 값
    rows = list(csv.reader(io.StringIO(builder.to_csv(screen))))
    hi = next(i for i, r in enumerate(rows) if r and r[0] == "tab_id")
    hdr = rows[hi]
    csv_metrics = {}
    for r in rows[hi + 1:]:
        if not r or not r[0] or r[0].startswith("["):
            break
        rec = dict(zip(hdr, r))
        csv_metrics[(rec["tab_id"], rec["metric_id"])] = rec
    for key, sm in screen_metrics.items():
        assert str(sm.get("value", "")) == csv_metrics[key]["value"]


def test_csv_formula_injection_guard(analyzed):
    from axport.reports import builder

    ctx, _, _, run = analyzed
    poisoned = json.loads(json.dumps(run))
    poisoned["tab_details"]["market"]["open_items"]["unconfirmed"].append(
        "=HYPERLINK(\"http://evil\")")
    poisoned["tab_details"]["market"]["open_items"]["next_actions"].append(
        "+cmd|' /C calc'!A0")
    text = builder.to_csv(poisoned)
    for row in csv.reader(io.StringIO(text)):
        for cell in row:
            assert not cell.startswith(("=", "+", "@")) or cell.lstrip("-").replace(".", "").isdigit(), cell
    assert "'=HYPERLINK" in text
    assert "'+cmd" in text


def test_report_endpoints(analyzed):
    from fastapi.testclient import TestClient

    from axport.main import create_app

    _, _, _, run = analyzed
    c = TestClient(create_app())
    created = c.post("/reports", json={"run_id": run["run_id"]})
    assert created.status_code == 200
    rid = created.json()["report_id"]
    assert c.get(f"/reports/{rid}").json()["run_id"] == run["run_id"]
    dl = c.get(f"/reports/{rid}/download.csv")
    assert dl.status_code == 200
    assert "text/csv" in dl.headers["content-type"]
    assert run["run_id"] in dl.text


def test_tab_endpoint(analyzed):
    from fastapi.testclient import TestClient

    from axport.main import create_app

    _, _, _, run = analyzed
    c = TestClient(create_app())
    res = c.get(f"/evaluations/{run['run_id']}/tabs/market")
    assert res.status_code == 200
    assert res.json()["tab_id"] == "market"
    assert c.get(f"/evaluations/{run['run_id']}/tabs/nope").status_code == 404


# ── AI 설명 (명세서 §7, §10, §11) ─────────────────────────────────────
def test_ai_not_called_when_config_undecided(analyzed):
    from axport.ai_explain import service as ai

    ctx, _, _, run = analyzed
    out = ai.explain(run, ctx.settings, dry_run=False)
    assert out["state"] == "not_evaluated"
    assert out["reason_code"] in ("ai_disabled", "ai_config_undecided")
    assert out["text"] is None


def test_ai_payload_is_minimal_and_redacted(analyzed):
    from axport.ai_explain import service as ai

    ctx, _, _, run = analyzed
    out = ai.explain(run, ctx.settings, dry_run=True)
    facts = out["payload_preview"]["facts"]
    assert facts, "허용목록 항목이 하나도 안 뽑혔다"
    blob = json.dumps(facts, ensure_ascii=False)
    for forbidden in ("company_id", "C-0001", "법인명", "주소", "등록번호",
                      "Northvale", "serviceKey", "sha256", "upload_id",
                      "최종사용자명"):
        assert forbidden not in blob, forbidden
    assert any(k.endswith(".display.text") for k in facts)
    assert any(k.endswith(".data_class_label") for k in facts)
    assert out["payload_preview"]["skipped_denied_count"] > 0


def test_ai_numeric_guard_rejects_invented_numbers(analyzed):
    from axport.ai_explain import service as ai

    ctx, _, _, run = analyzed
    payload = ai.build_payload(run, ai.load_policy(ctx.settings))
    ok = ai.check_response("2026-01~2026-03 수출금액은 300 USD 이며 평가 보류다.",
                           payload)
    assert ok["accepted"] is True
    bad = ai.check_response("수출금액은 300 USD 이고 성공 확률은 87% 다.", payload)
    assert bad["accepted"] is False
    assert "87" in bad["invented_numbers"]


def test_ai_limits_come_from_settings_not_code(analyzed):
    from axport.ai_explain import service as ai

    ctx, _, _, _ = analyzed
    policy = ai.load_policy(ctx.settings)
    assert "ai.max_requests_per_run" in policy.undecided
    assert "ai.monthly_cost_cap" in policy.undecided
    assert policy.callable is False


# ── 실제 외부 호출 (분리) ────────────────────────────────────────────
@pytest.mark.external
def test_live_customs_api(ctx):
    """실제 키·네트워크. 기본 실행에서 제외된다:  pytest -m external"""
    from axport.external_data.providers import customs_trade as ct
    from axport.rules_engine import evaluate as E

    key = E._service_key(ctx.settings, ct.ENV_VAR)
    res = ct.fetch(service_key=key, country_code="US", start_yymm="202601",
                   end_yymm="202603", hs_code="854232", verified="검증완료")
    assert res.fetch_result == "ok"
    assert res.row_count if hasattr(res, "row_count") else len(res.detail_rows) > 0
