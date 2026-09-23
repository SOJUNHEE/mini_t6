"""업로드 원본 보관 — 경로는 서버가 생성한다 (명세서 §5).

원칙
    파일명은 **표시 정보**로만 취급한다. 저장 경로에 쓰지 않는다.
    경로는 서버가 만든 upload_id 로만 구성한다.
    원본 파일을 보존하고, 정규화 데이터·사용자 보정 이력은 별도로 저장한다.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

SOURCE_FILENAME = "source.xlsx"      # 서버가 정한 고정 이름
META_FILENAME = "meta.json"


@dataclass
class StoredUpload:
    upload_id: str
    dir_path: str            # 프로젝트 루트 기준 상대경로
    source_path: str
    display_name: str        # 클라이언트가 보낸 원본 파일명. 표시 전용
    size_bytes: int
    sha256: str
    uploaded_at: str         # UTC

    def as_dict(self) -> dict:
        return asdict(self)


def new_upload_id() -> str:
    return uuid.uuid4().hex


def _display_path(path: Path, project_root: Path) -> str:
    """프로젝트 루트 기준 상대경로. 루트 밖이면(테스트 임시 폴더 등)
    절대경로를 쓴다. 개인 절대경로를 코드에 하드코딩하지는 않는다.
    """
    try:
        return str(path.relative_to(project_root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def store(raw: bytes, display_name: str, uploads_root: Path,
          project_root: Path) -> StoredUpload:
    """업로드 바이트를 서버가 만든 경로에 저장한다.

    display_name 은 meta.json 에만 기록한다. 경로 계산에 쓰지 않는다.
    """
    upload_id = new_upload_id()
    now = datetime.now(timezone.utc)
    # 날짜 계층은 서버 시각으로만 만든다. 클라이언트 값은 쓰지 않는다.
    target = uploads_root / now.strftime("%Y") / now.strftime("%m") / upload_id
    target.mkdir(parents=True, exist_ok=False)

    source = target / SOURCE_FILENAME
    source.write_bytes(raw)

    stored = StoredUpload(
        upload_id=upload_id,
        dir_path=_display_path(target, project_root),
        source_path=_display_path(source, project_root),
        display_name=display_name,
        size_bytes=len(raw),
        sha256=_sha256(source),
        uploaded_at=now.isoformat(),
    )
    (target / META_FILENAME).write_text(
        json.dumps(stored.as_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return stored


def find(upload_id: str, uploads_root: Path) -> Path | None:
    """upload_id 로 보관 폴더를 찾는다. 경로 조작 입력을 막는다."""
    if not upload_id or not upload_id.isalnum() or len(upload_id) != 32:
        return None
    matches = list(uploads_root.glob(f"*/*/{upload_id}"))
    return matches[0] if matches else None


def load_meta(upload_dir: Path) -> dict | None:
    meta = upload_dir / META_FILENAME
    if not meta.is_file():
        return None
    return json.loads(meta.read_text(encoding="utf-8"))


def write_artifact(upload_dir: Path, name: str, payload: dict) -> str:
    """단계별 산출물(검증 결과·매핑 등)을 원본과 분리해 저장한다."""
    path = upload_dir / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return path.name


def read_artifact(upload_dir: Path, name: str) -> dict | None:
    path = upload_dir / name
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
