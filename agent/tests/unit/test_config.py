"""P0: config is validated at start-up, secrets never leak into messages, `.env.example` is complete."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from returns_manager.config import REPO_ROOT, Settings
from returns_manager.errors import ConfigError, ExitCode

ENV_EXAMPLE = REPO_ROOT / ".env.example"


@pytest.fixture(autouse=True)
def _no_ambient_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


def _load(env_file: Path) -> Settings:
    return Settings(_env_file=env_file)  # type: ignore[call-arg]


def test_env_example_lists_every_setting() -> None:
    keys = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", ENV_EXAMPLE.read_text(encoding="utf-8"), re.MULTILINE))
    fields = {name.upper() for name in Settings.model_fields}
    assert fields - keys == set(), "settings missing from .env.example"
    assert keys - fields == set(), ".env.example has variables the settings do not know"


def test_env_example_parses_and_matches_prompt_defaults() -> None:
    s = _load(ENV_EXAMPLE)
    assert s.gemini_api_key is None or s.gemini_api_key.get_secret_value() == ""
    assert s.rm_judgment_model == "gemini-3.8-flash"
    assert s.rm_audit_model == "gemini-3.6-flash"
    assert s.rm_max_round_trips == 2
    assert s.rm_signed_url_ttl_s == 300
    assert s.rm_max_daily_spend_usd == "0"


def test_env_example_values_never_swallow_comments() -> None:
    # python-dotenv parses `KEY=   # note` as the value "# note"; comments must sit on their own lines.
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        if re.match(r"^[A-Z][A-Z0-9_]*=", line):
            assert "#" not in line.split("=", 1)[1], f"inline comment on a variable line: {line!r}"
    s = _load(ENV_EXAMPLE)
    for name, value in s.model_dump().items():
        if isinstance(value, str):
            assert not value.lstrip().startswith("#"), f"{name.upper()} parsed a comment as its value"


def test_invalid_value_is_rejected(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("RM_JUDGMENT_THINKING=extreme\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        _load(env)


def test_sampling_like_values_are_validated(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("RM_AUDIT_SAMPLE_RATE=1.5\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        _load(env)


def test_require_names_missing_settings_without_values(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("SUPABASE_SERVICE_ROLE_KEY=super-secret-value\n", encoding="utf-8")
    s = _load(env)
    with pytest.raises(ConfigError) as exc:
        s.require("database_url", "supabase_service_role_key")
    assert exc.value.exit_code == ExitCode.CONFIG_INVALID
    assert "DATABASE_URL" in str(exc.value)
    assert "SUPABASE_SERVICE_ROLE_KEY" not in str(exc.value)  # it is set, so not reported
    assert "super-secret-value" not in str(exc.value)


def test_secrets_are_masked_in_repr(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY=abc123-secret\n", encoding="utf-8")
    s = _load(env)
    assert "abc123-secret" not in repr(s)
    assert "abc123-secret" not in str(s.model_dump())
