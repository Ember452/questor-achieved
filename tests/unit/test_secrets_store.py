"""secrets 单元行为：keyring 路径、文件回落、红线 ①（repr 不泄漏凭据值）。"""

from __future__ import annotations

import logging
import os
import pathlib

import pytest
from pydantic import SecretStr

import questor.secrets.store as secrets_store
from questor.secrets import delete_secret, get_secret, set_secret
from questor.state.paths import questor_home
from questor.testenv.fake_home import fake_home
from questor.testenv.fake_keyring import fake_keyring

SECRET_VALUE = "sk-questor-unit-test-value"


def test_keyring_roundtrip() -> None:
    with fake_home(), fake_keyring() as backend:
        assert get_secret("provider-key") is None
        set_secret("provider-key", SECRET_VALUE)
        assert backend.store[("questor", "provider-key")] == SECRET_VALUE
        found = get_secret("provider-key")
        assert isinstance(found, SecretStr)
        assert found.get_secret_value() == SECRET_VALUE
        assert delete_secret("provider-key") is True
        assert get_secret("provider-key") is None
        assert delete_secret("provider-key") is False


def test_secret_repr_never_leaks_value() -> None:
    """红线 ①：凭据值不进 repr/日志——SecretStr 遮蔽是出口纪律。"""
    with fake_home(), fake_keyring():
        set_secret("provider-key", SECRET_VALUE)
        found = get_secret("provider-key")
        assert found is not None
        assert SECRET_VALUE not in repr(found)
        assert SECRET_VALUE not in str(found)
        assert found.get_secret_value() == SECRET_VALUE  # 显式取值才可见


def _inject_keyring_outage(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("injected keyring outage")

    monkeypatch.setattr("keyring.set_password", _boom)
    monkeypatch.setattr("keyring.get_password", _boom)
    # 每个用例独立观察回落告警：重置进程级"只警告一次"登记
    monkeypatch.setattr(secrets_store, "_fallback_warned", False)


def test_falls_back_to_file_when_keyring_fails(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    with fake_home():
        _inject_keyring_outage(monkeypatch)
        with caplog.at_level(logging.WARNING, logger="questor.secrets.store"):
            set_secret("provider-key", SECRET_VALUE)
            assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1
            found = get_secret("provider-key")
        assert found is not None
        assert found.get_secret_value() == SECRET_VALUE
        path = questor_home() / "secrets" / "provider-key"
        assert path.read_text(encoding="utf-8") == SECRET_VALUE


def test_fallback_file_is_owner_private_posix(monkeypatch: pytest.MonkeyPatch) -> None:
    if os.name == "nt":
        pytest.skip("Windows 的 chmod 只影响只读位，mode 语义不作断言")
    import stat

    with fake_home():
        _inject_keyring_outage(monkeypatch)
        set_secret("provider-key", SECRET_VALUE)
        path = questor_home() / "secrets" / "provider-key"
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.parametrize("bad", ["", ".", "..", "a/b", "a\\b", "a:b", "a b"])
def test_invalid_key_rejected(bad: str) -> None:
    with fake_home(), fake_keyring(), pytest.raises(ValueError):
        set_secret(bad, SECRET_VALUE)


def test_delete_clears_both_stores(tmp_path: pathlib.Path) -> None:
    with fake_home(), fake_keyring():
        set_secret("both-places", SECRET_VALUE)
        # 再写一份文件副本（模拟"曾经回落过"的机器）
        file_path = questor_home() / "secrets" / "both-places"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("stale", encoding="utf-8", newline="\n")
        assert delete_secret("both-places") is True
        assert not file_path.exists()
        assert get_secret("both-places") is None
