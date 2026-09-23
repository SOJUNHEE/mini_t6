"""AI 설명 — 계산 결과와 근거의 설명·요약만 담당한다 (명세서 §7, §10, §11).

절대 원칙
    AI 가 수치·판정·규정 조건을 만들어내지 않는다.
    설명 대상은 **이미 산출된 결과**뿐이다.
    응답에 입력 사실에 없는 숫자가 있으면 거부한다 (numeric guard).

전송 정책 (명세서 §10)
    전송 대상은 `ai.send_fields_allowlist` 에 **명시된 항목만**.
    `ai.send_fields_denylist` 는 허용목록보다 우선한다.
    기업명·거래처명·주소·등록번호·최종사용자·파일명 등 식별 정보는 기본 제외.
    API 키는 어떤 경우에도 페이로드에 들어가지 않는다.

제한 (명세서 §11)
    요청 수 상한 `ai.max_requests_per_run`, 비용 상한 `ai.monthly_cost_cap`.
    둘 중 하나라도 미정이면 호출하지 않는다. 임의 상한을 만들지 않는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from axport.config.settings import Settings

# 기본 제외 — 설정 denylist 와 합쳐서 적용한다
ALWAYS_DENY = (
    "company_id", "company_name", "법인명", "별칭", "주소", "등록번호",
    "최종사용자명", "최종용도", "거래처ID", "buyer_id", "display_name",
    "source_path", "sha256", "upload_id", "executed_by", "user_id",
    "serviceKey", "service_key", "api_key", "env_var", "query",
)

# 설명에 필요한 최소 항목. 설정 allowlist 가 비어 있으면 아무것도 보내지 않는다.
SUGGESTED_ALLOWLIST = (
    "subject.product_id", "subject.hs_code", "subject.hs_version",
    "subject.destination_country_code", "subject.evaluation_base_date",
    "analysis_mode_label",
    "result.overall.decision", "result.overall.decision_label",
    "result.overall.decision_reason_codes",
    "tab_details.*.label",
    "tab_details.*.results.metrics[].label",
    "tab_details.*.results.metrics[].state",
    "tab_details.*.results.metrics[].display.text",
    "tab_details.*.results.metrics[].unit",
    "tab_details.*.results.metrics[].currency",
    "tab_details.*.results.metrics[].period",
    "tab_details.*.results.metrics[].data_class_label",
    "tab_details.*.open_items.unconfirmed",
)

NUMBER_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


class AiDisabled(RuntimeError):
    """설정이 미정·비활성이라 호출하지 않는다."""

    def __init__(self, code: str, message: str, detail: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or {}

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message,
                "detail": self.detail}


@dataclass
class Policy:
    enabled: bool
    provider: str | None
    model: str | None
    max_requests_per_run: int | None
    monthly_cost_cap: str | None
    allowlist: tuple[str, ...]
    denylist: tuple[str, ...]
    undecided: list[str] = field(default_factory=list)

    @property
    def callable(self) -> bool:
        return self.enabled and not self.undecided

    def as_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "provider": self.provider,
            "model": self.model,
            "max_requests_per_run": self.max_requests_per_run,
            "monthly_cost_cap": self.monthly_cost_cap,
            "allowlist": list(self.allowlist),
            "denylist_effective": list(self.denylist),
            "undecided": self.undecided,
            "callable": self.callable,
        }


def load_policy(settings: Settings) -> Policy:
    undecided = [k for k in ("ai.provider", "ai.model",
                             "ai.max_requests_per_run", "ai.monthly_cost_cap")
                 if not settings.is_decided(k)]
    allowlist = tuple(settings.get("ai.send_fields_allowlist") or ())
    if not allowlist:
        undecided.append("ai.send_fields_allowlist")

    raw_cap = settings.get("ai.max_requests_per_run")
    try:
        max_req = int(str(raw_cap).strip()) if str(raw_cap).strip() else None
    except ValueError:
        max_req = None

    return Policy(
        enabled=settings.get("ai.enabled") in (True, "true", "True"),
        provider=settings.get("ai.provider") or None,
        model=settings.get("ai.model") or None,
        max_requests_per_run=max_req,
        monthly_cost_cap=settings.get("ai.monthly_cost_cap") or None,
        allowlist=allowlist,
        denylist=tuple(settings.get("ai.send_fields_denylist") or ())
                 + ALWAYS_DENY,
        undecided=undecided,
    )


# ── 전송 페이로드 ─────────────────────────────────────────────────────
def _denied(path: str, denylist: tuple[str, ...]) -> bool:
    last = path.split(".")[-1]
    return any(d == path or d == last or d in path for d in denylist)


def _allowed(path: str, allowlist: tuple[str, ...]) -> bool:
    for pattern in allowlist:
        regex = "^" + re.escape(pattern).replace(r"\*", "[^.]+") \
                                       .replace(r"\[\]", r"\[\d+\]") + "$"
        if re.match(regex, path):
            return True
    return False


def build_payload(run: dict, policy: Policy) -> dict:
    """허용목록에 있는 항목만 평평하게 모은다. 최소한만 전송한다."""
    facts: dict[str, object] = {}
    skipped_denied: list[str] = []

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else k)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
        else:
            if _denied(path, policy.denylist):
                skipped_denied.append(path)
                return
            if _allowed(path, policy.allowlist):
                facts[path] = node

    walk(run, "")
    return {
        "run_id": run.get("run_id"),
        "facts": facts,
        "fact_count": len(facts),
        "skipped_denied_count": len(skipped_denied),
        "instruction": (
            "아래 사실만 사용해 한국어로 설명하라. 숫자·판정·규정 조건을 "
            "새로 만들지 마라. 사실에 없는 값을 추정하지 마라. "
            "자료가 없는 항목은 '자료 부족' 또는 '평가 보류'로 그대로 서술하라."
        ),
    }


# ── 응답 검사 ─────────────────────────────────────────────────────────
def _numbers(text: str) -> set[str]:
    """부호는 떼고 본다. '2026-01' 의 '-01' 이 음수로 오인되지 않게 한다.
    지어낸 숫자는 부호와 무관하게 숫자 자체로 드러난다."""
    return {m.group(0).replace(",", "").lstrip("-")
            for m in NUMBER_RE.finditer(text)}


def check_response(text: str, payload: dict) -> dict:
    """AI 응답에 입력에 없는 숫자가 있으면 거부한다."""
    allowed: set[str] = set()
    for value in payload["facts"].values():
        allowed |= _numbers(str(value))
    # 기간 표기(2026-01)에서 나온 조각도 허용한다
    for value in payload["facts"].values():
        for part in re.split(r"[-/.]", str(value)):
            if part.isdigit():
                allowed.add(part)

    found = _numbers(text)
    invented = sorted(n for n in found if n not in allowed)
    return {
        "accepted": not invented,
        "invented_numbers": invented,
        "checked_numbers": sorted(found),
        "reason": None if not invented else
                  "입력 사실에 없는 숫자가 응답에 포함되어 거부했습니다.",
    }


# ── 실행 ──────────────────────────────────────────────────────────────
def explain(run: dict, settings: Settings, *, dry_run: bool = False) -> dict:
    """설명을 만든다. 설정이 미정이면 호출하지 않고 이유를 돌려준다.

    dry_run=True 면 전송할 페이로드만 만들어 보여준다. 외부로 나가지 않는다.
    """
    policy = load_policy(settings)
    payload = build_payload(run, policy)

    base = {
        "run_id": run.get("run_id"),
        "policy": policy.as_dict(),
        "payload_preview": payload,
        "state": "not_evaluated",
        "reason_code": None,
        "display_label": "평가 보류",
        "text": None,
        "guard": None,
    }

    if dry_run:
        return {**base, "reason_code": "dry_run",
                "note": "전송하지 않았습니다. 전송 대상 미리보기입니다."}

    if not policy.enabled:
        return {**base, "reason_code": "ai_disabled",
                "note": "features/ai.enabled 가 false 입니다."}

    if policy.undecided:
        return {**base, "reason_code": "ai_config_undecided",
                "note": "AI 설정이 미정입니다. 임의 기본값을 쓰지 않습니다: "
                        + ", ".join(policy.undecided)}

    # 여기까지 오면 공급자 호출을 붙일 자리다. 아직 붙이지 않았다.
    return {**base, "reason_code": "provider_not_implemented",
            "note": "설정은 갖춰졌으나 공급자 연결이 아직 구현되지 않았습니다. "
                    "없는 기능을 동작하는 것처럼 반환하지 않습니다."}
