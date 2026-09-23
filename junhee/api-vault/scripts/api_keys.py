"""API 키 로더 — 프로젝트 무관 공통 모듈.

어느 프로젝트에서나 이 폴더(api-vault)를 통째로 복사해 쓴다.

사용 예:
    from api_keys import get_key, require_key, available

    key = get_key("ECOS_API_KEY")          # 없으면 None
    key = require_key("ECOS_API_KEY")      # 없으면 예외
    print(available())                      # 설정된 키 이름 목록

환경변수 탐색 순서:
    1) 이미 설정된 OS 환경변수
    2) api-vault/credentials/.env
    3) 현재 작업 디렉터리의 .env
"""

from __future__ import annotations

import os
from pathlib import Path

_VAULT = Path(__file__).resolve().parent.parent
_ENV_PATHS = [
    _VAULT / "credentials" / ".env",
    Path.cwd() / ".env",
]

_loaded = False


def _parse_env_file(path: Path) -> dict[str, str]:
    """의존성 없이 .env 파일을 파싱한다."""
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name and value:
            result[name] = value
    return result


def load(force: bool = False) -> None:
    """.env 파일을 읽어 os.environ 에 채운다. 기존 환경변수는 덮어쓰지 않는다."""
    global _loaded
    if _loaded and not force:
        return
    for path in _ENV_PATHS:
        for name, value in _parse_env_file(path).items():
            os.environ.setdefault(name, value)
    _loaded = True


def get_key(name: str, default: str | None = None) -> str | None:
    """키를 반환한다. 없으면 default."""
    load()
    value = os.environ.get(name)
    return value if value else default


def require_key(name: str) -> str:
    """키를 반환한다. 없으면 예외를 던진다."""
    value = get_key(name)
    if not value:
        raise RuntimeError(
            f"환경변수 {name} 가 비어 있습니다. "
            f"{_VAULT / 'credentials' / '.env'} 를 확인하세요."
        )
    return value


def _template_names() -> list[str]:
    """등록된 환경변수 이름 목록. 입력표를 우선 보고, 없으면 .env.example."""
    import re

    names: list[str] = []
    form = _VAULT / "API_KEYS_FORM.txt"
    if form.is_file():
        pattern = re.compile(r"^\s*\[변수\]\s*([A-Z0-9_]+)\s*$")
        for raw in form.read_text(encoding="utf-8").splitlines():
            m = pattern.match(raw)
            if m:
                names.append(m.group(1))
        if names:
            return names

    example = _VAULT / "credentials" / ".env.example"
    if example.is_file():
        for raw in example.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                name = line.partition("=")[0].strip()
                if name not in names:
                    names.append(name)
    return names


def available() -> list[str]:
    """등록된 항목 중 실제 값이 채워진 것."""
    load()
    return [n for n in _template_names() if os.environ.get(n)]


def missing() -> list[str]:
    """등록되어 있으나 아직 값이 없는 항목."""
    load()
    return [n for n in _template_names() if not os.environ.get(n)]
