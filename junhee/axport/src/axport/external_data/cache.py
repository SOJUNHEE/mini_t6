"""외부 자료 캐시 — 오래된 자료 사용을 숨기지 않는다 (명세서 §7).

캐시에서 읽었는지, 몇 일 지났는지, 최대 허용 경과시간을 넘었는지를
호출부에 그대로 돌려준다. 오래된 자료를 최신처럼 쓰지 않는다.

`external_data.max_age_days_default` 가 미정이면 경과시간 초과를
**판정하지 않고** 그 사실을 보고한다. 임의 기준을 만들지 않는다.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class CacheEntry:
    hit: bool
    payload: dict | None
    fetched_at: str | None
    age_seconds: float | None
    age_days: float | None
    max_age_days: int | None          # None = 정책 미정
    max_age_exceeded: bool | None     # None = 판정 불가 (정책 미정)

    def as_dict(self) -> dict:
        return {
            "hit": self.hit,
            "fetched_at": self.fetched_at,
            "age_days": None if self.age_days is None else round(self.age_days, 3),
            "max_age_days": self.max_age_days,
            "max_age_exceeded": self.max_age_exceeded,
            "max_age_policy": "미정" if self.max_age_days is None else "설정됨",
        }


def query_key(source_id: str, params: dict) -> str:
    """조회 조건으로 캐시 키를 만든다. 키 값은 절대 포함하지 않는다."""
    safe = {k: v for k, v in sorted(params.items())
            if "key" not in k.lower() and "secret" not in k.lower()}
    blob = json.dumps([source_id, safe], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


class Cache:
    def __init__(self, root: Path, max_age_days: int | None,
                 enabled: bool = True) -> None:
        self.root = root
        self.max_age_days = max_age_days
        self.enabled = enabled

    def _path(self, source_id: str, key: str) -> Path:
        return self.root / source_id / f"{key}.json"

    def get(self, source_id: str, params: dict) -> CacheEntry:
        empty = CacheEntry(False, None, None, None, None,
                           self.max_age_days, None)
        if not self.enabled:
            return empty
        path = self._path(source_id, query_key(source_id, params))
        if not path.is_file():
            return empty
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return empty

        fetched_at = data.get("fetched_at")
        try:
            then = datetime.fromisoformat(fetched_at)
        except (TypeError, ValueError):
            return empty
        age = (datetime.now(timezone.utc) - then).total_seconds()
        age_days = age / 86400
        exceeded = (None if self.max_age_days is None
                    else age_days > self.max_age_days)
        return CacheEntry(True, data.get("payload"), fetched_at,
                          age, age_days, self.max_age_days, exceeded)

    def put(self, source_id: str, params: dict, payload: dict) -> None:
        if not self.enabled:
            return
        path = self._path(source_id, query_key(source_id, params))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source_id": source_id,
            # 조회 조건을 함께 남긴다. 인증키는 params 에 넣지 않는다.
            "query": {k: v for k, v in params.items() if "key" not in k.lower()},
            "payload": payload,
        }, ensure_ascii=False), encoding="utf-8")
