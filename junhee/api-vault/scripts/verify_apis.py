"""보유 API 실제 호출 검증 — 명세서 §13-2.

실행:
    python scripts/verify_apis.py                # 등록된 API 전체
    python scripts/verify_apis.py nitemtrade     # 지정한 것만
    python scripts/verify_apis.py --list         # 등록 목록만 출력

하는 일:
    1) specs/ 의 활용가이드에 적힌 파라미터 그대로 각 API 를 1회 호출
    2) 응답 원문을 specs/samples/<api명>_response.xml 로 저장
    3) 성공/실패와 에러코드를 표로 출력

원칙:
    - 키는 api_keys.require_key 로만 읽는다.
    - 키 값을 화면·로그·저장 파일에 출력하지 않는다. (명세서 §10)
    - 문서에 없는 파라미터를 임의로 추가하지 않는다.
    - XML 전용 API 에 JSON 파라미터를 붙이지 않는다.
    - 실패를 성공으로 적지 않는다. 에러코드를 그대로 보고한다. (명세서 §7)

serviceKey 의 Encoding / Decoding:
    공공데이터포털은 같은 키를 Encoding(퍼센트 인코딩된 문자열)과
    Decoding(원문) 두 형태로 발급한다. API 마다 한쪽만 동작하는 경우가 있다.
    이 스크립트는 문서에 'URL Encode' 로 적힌 API 에 대해 보관된 키를
    그대로(as-is) 먼저 보내고, 에러 30(등록되지 않은 서비스키)이면
    퍼센트 인코딩한 뒤 재시도한다. 어느 쪽이 동작했는지 결과표에 적는다.
"""

from __future__ import annotations

import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import api_keys  # noqa: E402

VAULT = Path(__file__).resolve().parent.parent
SAMPLES = VAULT / "specs" / "samples"

TIMEOUT = 30  # 초
SLEEP_BETWEEN = 1.0  # 초. 30 tps 제한에 한참 못 미치지만 여유를 둔다.

# ----------------------------------------------------------------------
# 검증 대상 — specs/ 문서에서 확인한 값만 적는다. 추측해서 채우지 않는다.
# ----------------------------------------------------------------------
SPECS: dict[str, dict] = {
    "nitemtrade": {
        "label": "관세청_품목별 국가별 수출입실적(GW)",
        "spec_doc": "관세청_품목별 국가별 수출입실적(GW).docx",
        "env": "DATA_GO_KR_API_KEY",
        "base": "apis.data.go.kr/1220000/nitemtrade",
        "operation": "getNitemtradeList",
        "format": "xml",  # 문서: [O] XML [ ] JSON — JSON 파라미터 금지
        "service_key_urlencode": True,  # 문서 샘플데이터: '인증키 (URL Encode)'
        # 문서 'd) 요청/응답 메시지 예제' 의 값을 그대로 사용
        "params": {
            "strtYymm": "201601",
            "endYymm": "201601",
            "hsSgn": "1001999090",
            "cntyCd": "US",
        },
        "limits": "30 tps / 조회기간 1년 이내 / 최대 4000 byte",
    },
}


# ----------------------------------------------------------------------
# 호출
# ----------------------------------------------------------------------
def _build_url(scheme: str, base: str, operation: str,
               params: dict[str, str], service_key: str,
               encode_key: bool) -> str:
    """쿼리스트링을 직접 조립한다.

    serviceKey 는 urlencode 에 맡기지 않는다. 보관된 키가 이미 Encoding
    형태(퍼센트 인코딩됨)인 경우 다시 인코딩하면 '%' 가 '%25' 로 바뀌어
    에러 30 이 된다. 어느 형태로 보낼지는 호출부가 정한다.
    """
    key_part = urllib.parse.quote(service_key, safe="") if encode_key else service_key
    rest = urllib.parse.urlencode(params)
    query = f"serviceKey={key_part}" + (f"&{rest}" if rest else "")
    return f"{scheme}://{base}/{operation}?{query}"


def _fetch(url: str) -> tuple[int, bytes]:
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:  # 4xx·5xx 도 본문을 봐야 한다
        return exc.code, exc.read()


def _redact(text: str, secret: str) -> str:
    """혹시라도 본문·URL 에 키가 섞여 있으면 가린다."""
    out = text
    for form in {secret, urllib.parse.quote(secret, safe=""),
                 urllib.parse.unquote(secret)}:
        if form:
            out = out.replace(form, "<REDACTED>")
    return out


# ----------------------------------------------------------------------
# 응답 판정
# ----------------------------------------------------------------------
def _interpret(body: bytes) -> dict:
    """응답에서 결과코드를 뽑는다. 판단 불가면 그렇게 적는다."""
    text = body.decode("utf-8", errors="replace").strip()
    result = {"code": "", "msg": "", "items": None, "shape": ""}

    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        result["shape"] = "XML 파싱 실패"
        result["msg"] = f"{exc}"
        return result

    tag = root.tag.split("}")[-1]

    # 포털 공통 오류 봉투
    if tag == "OpenAPI_ServiceResponse":
        result["shape"] = "포털 오류"
        code = root.findtext(".//returnReasonCode") or ""
        result["code"] = code.strip()
        result["msg"] = (root.findtext(".//returnAuthMsg")
                         or root.findtext(".//errMsg") or "").strip()
        return result

    # 정상 응답 봉투
    result["shape"] = tag
    result["code"] = (root.findtext(".//resultCode") or "").strip()
    result["msg"] = (root.findtext(".//resultMsg") or "").strip()
    items = root.findall(".//item")
    result["items"] = len(items)
    return result


def _is_success(info: dict) -> bool:
    return info["code"] in {"00", "0"}


# ----------------------------------------------------------------------
# API 1건 검증
# ----------------------------------------------------------------------
def verify(name: str, spec: dict) -> dict:
    print(f"\n{'=' * 68}")
    print(f"[{name}] {spec['label']}")
    print(f"{'=' * 68}")
    print(f"  명세 문서   {spec['spec_doc']}")
    print(f"  오퍼레이션  {spec['operation']}   포맷 {spec['format'].upper()}")
    print(f"  호출 제한   {spec['limits']}")
    print(f"  파라미터    {', '.join(f'{k}={v}' for k, v in spec['params'].items())}")

    outcome = {
        "name": name, "label": spec["label"], "ok": False,
        "code": "", "msg": "", "items": None,
        "key_form": "", "scheme": "", "http": "", "sample": "",
    }

    try:
        service_key = api_keys.require_key(spec["env"])
    except RuntimeError as exc:
        print(f"  [X] {exc}")
        outcome["code"] = "KEY_MISSING"
        outcome["msg"] = f"{spec['env']} 미설정"
        return outcome

    # (키 형태, 스킴) 순으로 시도. 에러 30 일 때만 반대쪽 키 형태로 재시도.
    attempts = [("as-is", False), ("URL-encoded", True)]
    if not spec["service_key_urlencode"]:
        attempts.reverse()

    body = b""
    info: dict = {}
    for key_form, encode_key in attempts:
        for scheme in ("https", "http"):
            url = _build_url(scheme, spec["base"], spec["operation"],
                             spec["params"], service_key, encode_key)
            shown = _redact(url, service_key)
            print(f"\n  → {scheme.upper()} / serviceKey {key_form}")
            print(f"    {shown}")
            try:
                status, body = _fetch(url)
            except Exception as exc:  # noqa: BLE001 — 원인을 그대로 보고
                print(f"    [X] 연결 실패: {type(exc).__name__}: "
                      f"{_redact(str(exc), service_key)}")
                outcome["code"] = "CONN_FAIL"
                outcome["msg"] = type(exc).__name__
                continue

            info = _interpret(body)
            outcome.update(http=str(status), scheme=scheme, key_form=key_form,
                           code=info["code"], msg=info["msg"],
                           items=info["items"])
            print(f"    HTTP {status} / {info['shape']} / "
                  f"resultCode={info['code'] or '-'} {info['msg']}")

            if _is_success(info):
                outcome["ok"] = True
                break
            # 30 = 등록되지 않은 서비스키 → 반대쪽 키 형태로 재시도할 가치가 있다
            if info["code"] == "30":
                break  # 스킴 반복을 끝내고 다음 키 형태로
        if outcome["ok"] or info.get("code") not in {"30", ""}:
            break

    if body:
        SAMPLES.mkdir(parents=True, exist_ok=True)
        path = SAMPLES / f"{name}_response.xml"
        text = _redact(body.decode("utf-8", errors="replace"), service_key)
        path.write_text(text, encoding="utf-8")
        outcome["sample"] = str(path.relative_to(VAULT))
        print(f"\n  응답 원문 저장: {outcome['sample']}  ({len(body)} byte)")

    return outcome


# ----------------------------------------------------------------------
def print_table(results: list[dict]) -> None:
    print(f"\n{'=' * 78}")
    print("검증 결과")
    print("=" * 78)
    head = f"{'API':<14} {'결과':<6} {'코드':<12} {'건수':>5}  {'키형태':<12} 비고"
    print(head)
    print("-" * 78)
    for r in results:
        mark = "성공" if r["ok"] else "실패"
        items = "-" if r["items"] is None else str(r["items"])
        note = r["msg"][:28]
        print(f"{r['name']:<14} {mark:<6} {r['code'] or '-':<12} {items:>5}  "
              f"{r['key_form'] or '-':<12} {note}")
    print("-" * 78)
    ok = sum(1 for r in results if r["ok"])
    print(f"성공 {ok}건 / 실패 {len(results) - ok}건")
    print("\n※ 성공은 '응답을 받았다'는 뜻이다. 응답 값의 정확성은 별도 검토 대상이다.")


def main(argv: list[str]) -> int:
    if "--list" in argv:
        for name, spec in SPECS.items():
            print(f"{name:<14} {spec['label']}")
        return 0

    targets = [a for a in argv if not a.startswith("-")]
    unknown = [t for t in targets if t not in SPECS]
    if unknown:
        print(f"[!] 등록되지 않은 API: {', '.join(unknown)}")
        print(f"    등록된 것: {', '.join(SPECS)}")
        return 1

    names = targets or list(SPECS)
    results = []
    for i, name in enumerate(names):
        if i:
            time.sleep(SLEEP_BETWEEN)
        results.append(verify(name, SPECS[name]))

    print_table(results)
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
