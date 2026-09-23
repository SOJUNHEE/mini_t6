"""중앙 설정 로더 (명세서 §11).

설정의 단일 출처는 config/settings.toml 이다.
값을 UI·서버·보고서에 중복 하드코딩하지 않는다.

우선순위
    1) 환경변수 (AXPORT_ 접두사)
    2) config/settings.toml
    비밀값은 어느 쪽에서도 읽지 않는다. API 키는 api-vault 에서만 읽는다.

빈 문자열("")은 '미정'을 뜻한다. 미정 값을 임의의 기본값으로
대체하지 않는다. 그 값을 필요로 하는 기능은 비활성으로 둔다.
"""

from __future__ import annotations

import os
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any

# src/axport/config/settings.py -> 프로젝트 루트
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "settings.toml"

UNDECIDED = ""


class ConfigError(RuntimeError):
    """설정을 읽을 수 없을 때. 기본값으로 조용히 넘어가지 않는다."""


class Settings:
    """읽기 전용 설정 접근자."""

    def __init__(self, data: dict[str, Any], source: Path) -> None:
        self._data = data
        self.source = source

    def get(self, path: str, default: Any = None) -> Any:
        """'runtime.port' 형태의 경로로 값을 읽는다."""
        node: Any = self._data
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def require(self, path: str) -> Any:
        """미정('')이면 예외를 던진다. 임의 기본값으로 대체하지 않는다."""
        value = self.get(path, UNDECIDED)
        if value == UNDECIDED or value is None:
            raise ConfigError(
                f"설정 '{path}' 가 미정입니다. {self.source} 를 확인하세요. "
                "임의의 기본값으로 대체하지 않습니다."
            )
        return value

    def is_decided(self, path: str) -> bool:
        value = self.get(path, UNDECIDED)
        return value not in (UNDECIDED, None, [], {})

    def undecided_paths(self) -> list[str]:
        """미정 상태인 설정 경로 목록. 헬스체크·기동 로그에 쓴다."""
        found: list[str] = []

        def walk(node: Any, prefix: str) -> None:
            if isinstance(node, dict):
                for k, v in node.items():
                    walk(v, f"{prefix}.{k}" if prefix else k)
            elif node == UNDECIDED:
                found.append(prefix)

        walk(self._data, "")
        return sorted(found)

    def resolve_path(self, path: str) -> Path:
        """storage 계열 상대경로를 프로젝트 루트 기준 절대경로로 바꾼다."""
        raw = self.require(path)
        p = Path(raw)
        return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()

    def as_dict(self) -> dict[str, Any]:
        return self._data


def _apply_env_overrides(data: dict[str, Any]) -> dict[str, Any]:
    """AXPORT_RUNTIME__PORT 형태의 환경변수로 덮어쓴다."""
    for key, value in os.environ.items():
        if not key.startswith("AXPORT_") or "__" not in key:
            continue
        parts = key[len("AXPORT_"):].lower().split("__")
        node = data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
            if not isinstance(node, dict):
                break
        else:
            node[parts[-1]] = value
    return data


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    path = Path(os.environ.get("AXPORT_CONFIG_FILE", DEFAULT_CONFIG))
    if not path.is_file():
        raise ConfigError(f"설정 파일을 찾을 수 없습니다: {path}")
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    return Settings(_apply_env_overrides(data), path)
