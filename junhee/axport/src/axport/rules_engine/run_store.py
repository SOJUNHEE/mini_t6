"""평가 실행 보관 (명세서 §6).

한 번 저장한 평가 실행은 고치지 않는다(`sealed`). 입력·규칙·외부 자료가
바뀌면 새 실행을 만든다. 과거 결과를 조용히 다시 계산하지 않는다.

화면과 보고서는 **같은 run_id** 를 읽는다. 보고서를 만들 때 다시 계산하지
않는다 (명세서 §11).

필터(분석 기간 등)가 바뀌면 입력이 바뀐 것이므로 새 run_id 가 된다.
이전 결과가 최신처럼 남지 않는다 (명세서 §9).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

RUNS_DIRNAME = "runs"
INDEX_FILENAME = "runs_index.json"


def new_run_id() -> str:
    return f"run_{uuid.uuid4().hex[:24]}"


def input_fingerprint(*, upload_sha256: str, subject_id: str, filters: dict,
                      engine: dict) -> str:
    """입력·필터·엔진 버전의 지문. 같은 지문이면 같은 입력이다."""
    blob = json.dumps({
        "upload_sha256": upload_sha256,
        "subject_id": subject_id,
        "filters": filters,
        "engine": engine,
    }, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def runs_dir(upload_dir: Path) -> Path:
    return upload_dir / RUNS_DIRNAME


def save(upload_dir: Path, run: dict) -> dict:
    """평가 실행을 저장하고 sealed 로 잠근다."""
    target = runs_dir(upload_dir)
    target.mkdir(parents=True, exist_ok=True)
    run = {**run, "sealed": True,
           "saved_at": datetime.now(timezone.utc).isoformat()}
    path = target / f"{run['run_id']}.json"
    if path.exists():
        raise RunStoreError(f"이미 저장된 평가 실행입니다: {run['run_id']}")
    path.write_text(json.dumps(run, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    _append_index(upload_dir, run)
    return run


class RunStoreError(RuntimeError):
    pass


def _append_index(upload_dir: Path, run: dict) -> None:
    path = upload_dir / INDEX_FILENAME
    try:
        index = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    except (OSError, json.JSONDecodeError):
        index = []
    index.append({
        "run_id": run["run_id"],
        "run_seq": run.get("run_seq"),
        "subject_id": run.get("subject", {}).get("subject_id"),
        "input_fingerprint": run.get("input_fingerprint"),
        "filters": run.get("filters"),
        "executed_at": run.get("executed_at"),
        "decision": run.get("result", {}).get("overall", {}).get("decision"),
        "supersedes_run_id": run.get("supersedes_run_id"),
    })
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2),
                    encoding="utf-8")


def load(upload_dir: Path, run_id: str) -> dict | None:
    if not run_id.startswith("run_") or not run_id[4:].isalnum():
        return None
    path = runs_dir(upload_dir) / f"{run_id}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def find_anywhere(uploads_root: Path, run_id: str) -> tuple[Path, dict] | None:
    """업로드를 몰라도 run_id 로 찾는다."""
    if not run_id.startswith("run_") or not run_id[4:].isalnum():
        return None
    for path in uploads_root.glob(f"*/*/*/{RUNS_DIRNAME}/{run_id}.json"):
        return path.parents[1], json.loads(path.read_text(encoding="utf-8"))
    return None


def index(upload_dir: Path) -> list[dict]:
    path = upload_dir / INDEX_FILENAME
    if not path.is_file():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def latest_for(upload_dir: Path, subject_id: str,
               fingerprint: str) -> dict | None:
    """같은 입력 지문의 가장 최근 실행. 같으면 재사용할 수 있다."""
    matches = [e for e in index(upload_dir)
               if e.get("subject_id") == subject_id
               and e.get("input_fingerprint") == fingerprint]
    if not matches:
        return None
    return matches[-1]


def next_seq(upload_dir: Path, subject_id: str) -> int:
    return 1 + len([e for e in index(upload_dir)
                    if e.get("subject_id") == subject_id])
