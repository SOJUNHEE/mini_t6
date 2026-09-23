"""보고서 생성 — 저장된 평가 실행을 그대로 옮긴다 (명세서 §6, §11).

원칙
    보고서를 만들 때 **다시 계산하지 않는다.** 저장된 run 의 값을 읽어 쓴다.
    화면과 보고서는 같은 run_id 를 참조하므로 수치가 일치한다.
    다운로드 표·CSV 에 수식 주입 방어를 적용한다 (명세서 §5).
    실제 자료·샘플·사용자 입력·가정값을 구분 표기한다 (명세서 §7).
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from axport.external_data.sources import DATA_CLASS_LABEL
from axport.reports.csv_safe import sanitize_row

REPORT_FORMATS = ("json", "csv")

METRIC_HEADER = [
    "tab_id", "탭", "metric_id", "지표", "state", "value", "표시값",
    "unit", "currency", "amount_multiplier", "period_start", "period_end",
    "data_class", "데이터구분", "reason_code", "상태문구", "formula",
    "source_id", "asof_date",
]

SOURCE_HEADER = [
    "source_id", "api_name", "verified", "fetch_result", "error_code",
    "error_message", "data_class", "데이터구분", "period_start", "period_end",
    "currency", "cache_hit", "cache_age_days", "max_age_policy",
    "requested_hs", "hs_granularity_used", "hs_broadened",
]


def new_report_id() -> str:
    return f"rep_{uuid.uuid4().hex[:20]}"


def _metric_rows(run: dict) -> list[list[object]]:
    """모든 지표를 한 표로. 통화·단위·기간을 함께 싣는다 (명세서 §4)."""
    rows: list[list[object]] = []
    for tab_id in run.get("tab_order", []):
        detail = run.get("tab_details", {}).get(tab_id)
        if not detail:
            continue
        for m in detail["results"].get("metrics", []):
            period = m.get("period") or {}
            rows.append([
                tab_id,
                detail["label"],
                m.get("metric_id"),
                m.get("label"),
                m.get("state"),
                m.get("value", ""),
                (m.get("display") or {}).get("text", ""),
                m.get("unit", ""),
                m.get("currency", ""),
                m.get("amount_multiplier", ""),
                period.get("start", ""),
                period.get("end", ""),
                m.get("data_class", ""),
                m.get("data_class_label", ""),
                m.get("reason_code", ""),
                m.get("display_label", ""),
                m.get("formula", ""),
                m.get("source_id", ""),
                m.get("asof_date", ""),
            ])
    return rows


def _source_rows(run: dict) -> list[list[object]]:
    rows: list[list[object]] = []
    for s in run.get("external_sources", []):
        cache = s.get("cache") or {}
        period = s.get("period") or {}
        rows.append([
            s.get("source_id"), s.get("api_name"), s.get("verified"),
            s.get("fetch_result"), s.get("error_code"), s.get("error_message"),
            s.get("data_class"),
            DATA_CLASS_LABEL.get(s.get("data_class"), ""),
            period.get("start", ""), period.get("end", ""),
            s.get("currency"),
            cache.get("hit"), cache.get("age_days"), cache.get("max_age_policy"),
            s.get("requested_hs"), s.get("hs_granularity_used"),
            s.get("hs_broadened"),
        ])
    for f in run.get("evidence_inventory", {}).get("files", []):
        rows.append([
            "file:" + (f.get("path") or ""), f.get("source"), f.get("verified"),
            "file_present", "", "", f.get("data_class"),
            DATA_CLASS_LABEL.get(f.get("data_class"), ""),
            f.get("asof", ""), "", "", "", "", "", "", "", "",
        ])
    return rows


def _detail_tables(run: dict) -> list[dict]:
    out = []
    for tab_id in run.get("tab_order", []):
        detail = run.get("tab_details", {}).get(tab_id)
        if not detail:
            continue
        for table in detail.get("tables", []):
            out.append({"tab_id": tab_id, **table})
    return out


def build(run: dict, *, formats: tuple[str, ...] = REPORT_FORMATS) -> dict:
    """저장된 run 에서 보고서 페이로드를 만든다. 재계산 없음."""
    tab_ids = [t for t in run.get("tab_order", [])
               if t in run.get("tab_details", {})]
    return {
        "report_id": new_report_id(),
        "run_id": run["run_id"],
        "run_seq": run.get("run_seq"),
        "upload_id": run.get("upload_id"),
        "input_fingerprint": run.get("input_fingerprint"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine": run.get("engine"),
        "environment": run.get("environment"),
        "scope": run.get("scope"),
        "subject": run.get("subject"),
        "filters": run.get("filters"),
        "analysis_mode": run.get("analysis_mode"),
        "analysis_mode_label": run.get("analysis_mode_label"),
        "overall": run.get("result", {}).get("overall"),
        "main_summary": run.get("main_summary"),
        "metrics": [dict(zip(METRIC_HEADER, r)) for r in _metric_rows(run)],
        "sources": [dict(zip(SOURCE_HEADER, r)) for r in _source_rows(run)],
        "tables": _detail_tables(run),
        "reasoning": {t: run["tab_details"][t]["reasoning"] for t in tab_ids},
        "open_items": {t: run["tab_details"][t]["open_items"] for t in tab_ids},
        "formats": list(formats),
        "note": ("이 보고서는 평가 실행 " + run["run_id"] +
                 " 의 저장된 결과를 그대로 옮긴 것이다. 재계산하지 않았다."),
    }


def _column_label(col: dict) -> str:
    label = col["label"]
    if col.get("currency"):
        label += f" ({col['currency']})"
    if col.get("unit"):
        label += f" ({col['unit']})"
    return label


def to_csv(run: dict) -> str:
    """지표·소스·상세 표를 한 CSV 로. 수식 주입 방어를 적용한다."""
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\r\n")
    subject = run.get("subject", {})
    overall = run.get("result", {}).get("overall", {})

    w.writerow(sanitize_row(["# AXPORT 분석 보고서"]))
    w.writerow(sanitize_row(["# run_id", run["run_id"]]))
    w.writerow(sanitize_row(["# 저장된 평가 실행을 그대로 옮긴 것이며 "
                             "재계산하지 않았습니다."]))
    w.writerow(sanitize_row(["# 생성시각(UTC)",
                             datetime.now(timezone.utc).isoformat()]))
    w.writerow(sanitize_row(["# 기업", subject.get("company_id"),
                             "제품", subject.get("product_id"),
                             "HS", subject.get("hs_code"),
                             "대상국", subject.get("destination_country_code"),
                             "기준일", subject.get("evaluation_base_date"),
                             "분석", run.get("analysis_mode_label")]))
    w.writerow(sanitize_row(["# 종합", overall.get("decision"),
                             overall.get("decision_label")]))
    env = run.get("environment") or {}
    w.writerow(sanitize_row(["# 환경", env.get("label"),
                             "storage", env.get("storage_scope")]))
    w.writerow([])

    w.writerow(sanitize_row(["[지표]"]))
    w.writerow(sanitize_row(METRIC_HEADER))
    for row in _metric_rows(run):
        w.writerow(sanitize_row(row))
    w.writerow([])

    w.writerow(sanitize_row(["[자료 출처]"]))
    w.writerow(sanitize_row(SOURCE_HEADER))
    for row in _source_rows(run):
        w.writerow(sanitize_row(row))
    w.writerow([])

    for table in _detail_tables(run):
        title = table.get("title", "")
        w.writerow(sanitize_row([f"[표] {table['tab_id']} / {title}"]))
        cols = table.get("columns", [])
        w.writerow(sanitize_row([_column_label(c) for c in cols]))
        for r in table.get("rows", []):
            w.writerow(sanitize_row([r.get(c["key"]) for c in cols]))
        w.writerow([])

    w.writerow(sanitize_row(["[미확인 사항·후속 조치]"]))
    w.writerow(sanitize_row(["tab_id", "종류", "내용"]))
    for tab_id in run.get("tab_order", []):
        detail = run.get("tab_details", {}).get(tab_id)
        if not detail:
            continue
        oi = detail["open_items"]
        for kind, items in (("미확인", oi["unconfirmed"]),
                            ("필요한 입력", oi["required_inputs"]),
                            ("필요한 자료", oi["required_sources"]),
                            ("후속 조치", oi["next_actions"])):
            for item in items:
                w.writerow(sanitize_row([tab_id, kind, item]))
    return buf.getvalue()


def save(reports_dir: Path, run: dict, report: dict) -> dict:
    """보고서를 파일로 남긴다. 경로는 서버가 만든다."""
    target = reports_dir / report["report_id"]
    target.mkdir(parents=True, exist_ok=True)
    (target / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    # BOM 을 붙여 Excel 에서 한글이 깨지지 않게 한다
    (target / "report.csv").write_text(to_csv(run), encoding="utf-8-sig")
    return {
        "report_id": report["report_id"],
        "run_id": run["run_id"],
        "files": {"json": "report.json", "csv": "report.csv"},
        "dir": target.name,
    }


def load(reports_dir: Path, report_id: str) -> dict | None:
    if not report_id.startswith("rep_") or not report_id[4:].isalnum():
        return None
    path = reports_dir / report_id / "report.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def csv_path(reports_dir: Path, report_id: str) -> Path | None:
    if not report_id.startswith("rep_") or not report_id[4:].isalnum():
        return None
    path = reports_dir / report_id / "report.csv"
    return path if path.is_file() else None
