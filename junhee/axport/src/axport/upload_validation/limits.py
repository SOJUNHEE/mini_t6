"""① 제한 검증 — 파일 형식·크기·압축해제 크기·셀 수·처리시간 (명세서 §5).

전부 **서버에서** 검증한다. 클라이언트가 보낸 값은 신뢰하지 않는다.

제한값은 config/settings.toml 에 있고 현재 **미정("")** 이다 (명세서 §2).
미정인 동안 업로드를 거부한다. 임의의 기본값으로 대체하지 않는다.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from axport.config.settings import Settings

# 매크로를 담을 수 있는 확장자·내부 파트
MACRO_EXTENSIONS = {".xlsm", ".xlsb", ".xltm"}
MACRO_PARTS = ("vbaproject.bin", "vbaproject", "macrosheet")

LIMIT_KEYS = (
    "upload.max_file_bytes",
    "upload.max_decompressed_bytes",
    "upload.max_rows_per_sheet",
    "upload.max_sheets",
    "upload.max_cells",
    "upload.processing_timeout_seconds",
)


class UploadRejected(Exception):
    """업로드 거부. code 는 사유 코드다."""

    def __init__(self, code: str, message: str, detail: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or {}

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "detail": self.detail}


@dataclass
class Limits:
    max_file_bytes: int
    max_decompressed_bytes: int
    max_rows_per_sheet: int
    max_sheets: int
    max_cells: int
    processing_timeout_seconds: int
    allowed_extensions: tuple[str, ...]
    source: str = ""

    def as_dict(self) -> dict:
        return {
            "max_file_bytes": self.max_file_bytes,
            "max_decompressed_bytes": self.max_decompressed_bytes,
            "max_rows_per_sheet": self.max_rows_per_sheet,
            "max_sheets": self.max_sheets,
            "max_cells": self.max_cells,
            "processing_timeout_seconds": self.processing_timeout_seconds,
            "allowed_extensions": list(self.allowed_extensions),
            "source": self.source,
        }


def load_limits(settings: Settings) -> Limits:
    """설정에서 제한값을 읽는다. 미정이면 UploadRejected 를 던진다."""
    missing = [k for k in LIMIT_KEYS if not settings.is_decided(k)]
    if missing:
        raise UploadRejected(
            "limits_undecided",
            "업로드 제한값이 미정입니다. 승인 전까지 업로드를 받지 않습니다. "
            "(명세서 §2 「파일 크기·행 수·시트 수·처리시간 제한」)",
            {"undecided": missing, "config": str(settings.source)},
        )

    def as_int(key: str) -> int:
        raw = settings.get(key)
        try:
            return int(str(raw).strip())
        except (TypeError, ValueError) as exc:
            raise UploadRejected(
                "limit_not_a_number",
                f"설정 '{key}' 가 정수가 아닙니다.",
                {"value": str(raw)},
            ) from exc

    exts = settings.get("upload.allowed_extensions") or []
    if not exts:
        raise UploadRejected(
            "limits_undecided",
            "허용 확장자가 비어 있습니다.",
            {"undecided": ["upload.allowed_extensions"]},
        )

    return Limits(
        max_file_bytes=as_int("upload.max_file_bytes"),
        max_decompressed_bytes=as_int("upload.max_decompressed_bytes"),
        max_rows_per_sheet=as_int("upload.max_rows_per_sheet"),
        max_sheets=as_int("upload.max_sheets"),
        max_cells=as_int("upload.max_cells"),
        processing_timeout_seconds=as_int("upload.processing_timeout_seconds"),
        allowed_extensions=tuple(str(e).lower() for e in exts),
        source=str(settings.source),
    )


@dataclass
class FileInspection:
    """파일을 열기 전에 확인한 사실."""

    declared_name: str          # 클라이언트가 보낸 이름 — 표시 정보로만 쓴다
    extension: str
    size_bytes: int
    decompressed_bytes: int
    entry_count: int
    macro_parts: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "declared_name": self.declared_name,
            "extension": self.extension,
            "size_bytes": self.size_bytes,
            "decompressed_bytes": self.decompressed_bytes,
            "entry_count": self.entry_count,
            "macro_parts": self.macro_parts,
        }


def inspect_file(path: Path, declared_name: str, limits: Limits) -> FileInspection:
    """열기 전 검사. 통과하지 못하면 UploadRejected.

    declared_name 은 확장자 판단과 화면 표시에만 쓴다.
    저장 경로로 쓰지 않는다 (명세서 §5).
    """
    size = path.stat().st_size
    if size == 0:
        raise UploadRejected("empty_file", "빈 파일입니다.")
    if size > limits.max_file_bytes:
        raise UploadRejected(
            "file_too_large",
            "파일 크기 제한을 초과했습니다.",
            {"size_bytes": size, "max_file_bytes": limits.max_file_bytes},
        )

    ext = Path(declared_name).suffix.lower()
    if ext in MACRO_EXTENSIONS:
        raise UploadRejected(
            "macro_format_not_allowed",
            "매크로를 포함할 수 있는 형식은 받지 않습니다. (명세서 §5)",
            {"extension": ext},
        )
    if ext not in limits.allowed_extensions:
        raise UploadRejected(
            "extension_not_allowed",
            "허용되지 않는 확장자입니다.",
            {"extension": ext, "allowed": list(limits.allowed_extensions)},
        )

    # xlsx 는 zip 이다. 실제 내용으로 형식을 확인한다 (확장자만 믿지 않는다).
    if not zipfile.is_zipfile(path):
        raise UploadRejected(
            "not_a_valid_xlsx",
            "xlsx 형식이 아닙니다. 확장자만 바뀐 파일일 수 있습니다.",
        )

    with zipfile.ZipFile(path) as zf:
        infos = zf.infolist()
        total = sum(i.file_size for i in infos)
        names = [i.filename for i in infos]

    if total > limits.max_decompressed_bytes:
        raise UploadRejected(
            "decompressed_too_large",
            "압축해제 크기 제한을 초과했습니다.",
            {"decompressed_bytes": total,
             "max_decompressed_bytes": limits.max_decompressed_bytes},
        )

    lowered = [n.lower() for n in names]
    found = [n for n, low in zip(names, lowered)
             if any(part in low for part in MACRO_PARTS)]
    if found:
        raise UploadRejected(
            "macro_content_found",
            "매크로가 포함된 파일입니다. 실행하지 않고 거부합니다. (명세서 §5)",
            {"parts": found},
        )

    if "xl/workbook.xml" not in lowered:
        raise UploadRejected(
            "not_a_valid_xlsx",
            "xlsx 내부 구조가 아닙니다.",
            {"entries": names[:10]},
        )

    return FileInspection(
        declared_name=declared_name,
        extension=ext,
        size_bytes=size,
        decompressed_bytes=total,
        entry_count=len(infos),
        macro_parts=[],
    )
