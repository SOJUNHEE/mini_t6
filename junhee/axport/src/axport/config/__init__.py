"""중앙 설정 (명세서 §11).

설정값의 단일 출처는 config/settings.toml 이다.
UI·서버·보고서에 같은 값을 중복 하드코딩하지 않는다.
"""

from axport.config.settings import ConfigError, Settings, get_settings

__all__ = ["ConfigError", "Settings", "get_settings"]
