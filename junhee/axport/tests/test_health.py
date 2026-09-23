"""헬스체크 검증. 비밀키 없이 재현 가능하다 (CONTRIBUTING §12)."""

from fastapi.testclient import TestClient

from axport.main import create_app

client = TestClient(create_app())


def test_health_responds():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] in {"ok", "degraded"}


def test_health_reports_config_loaded():
    body = client.get("/health").json()
    assert body["checks"]["config"]["loaded"] is True
    assert body["checks"]["config"]["config_version"] == "0.1"


def test_health_never_exposes_key_values():
    """키 값이 응답에 섞이지 않는지 본다 (명세서 §10)."""
    import sys
    from pathlib import Path

    vault = Path(__file__).resolve().parents[2] / "api-vault" / "scripts"
    if not (vault / "api_keys.py").is_file():
        return  # api-vault 없이도 이 테스트는 실패하지 않는다
    sys.path.insert(0, str(vault))
    import api_keys

    raw = client.get("/health").text
    for name in api_keys.available():
        value = api_keys.get_key(name)
        assert value and value not in raw, f"{name} 값이 응답에 노출됨"


def test_rule_set_not_usable_in_production():
    """별표2의2 미확보 상태에서 운영 판정이 열려 있으면 안 된다."""
    body = client.get("/health").json()
    assert body["checks"]["versions"]["rule_set_usable_in_production"] is False


def test_unfinished_features_are_disabled():
    body = client.get("/health").json()
    for name, enabled in body["checks"]["features"].items():
        assert enabled is False, f"{name} 이 미구현인데 활성화돼 있다"


def test_undecided_settings_endpoint():
    res = client.get("/health/config/undecided")
    assert res.status_code == 200
    assert res.json()["count"] > 0  # 명세서 §2 미정 항목이 남아 있어야 정상
