"""cli 的单元行为：入口解析、配置→ModelSpec、stdout 洁净（B-87）。

B-87 的断言只有一条硬规则：**`--json` 时 stdout 的每一行都必须是可解析的 JSON 帧**，
日志与告警必须在 stderr。这条必须在真跑一次 exec 的路径上验，不能只测 version——
将来接桌面壳时，sidecar 的 stdout 也会被同样的规则管住。
"""

from __future__ import annotations

import json

import pytest

from questor.cli import main, model_spec_from_config
from questor.config import ConfigSnapshot
from questor.providers import ProtocolName
from questor.testenv.fake_home import fake_home
from questor.testenv.fake_model import FakeModel, ScriptedTurn


def _snapshot(model: dict[str, object]) -> ConfigSnapshot:
    return ConfigSnapshot(data={"model": model}, layers_applied=("user",), stripped=())


# ---- 配置 → ModelSpec ----


def test_missing_model_section_is_actionable() -> None:
    with pytest.raises(ValueError, match=r"\[model\]"):
        model_spec_from_config({})


def test_unknown_protocol_is_rejected_not_guessed() -> None:
    with pytest.raises(ValueError, match="未知 model.protocol"):
        model_spec_from_config(
            _snapshot({"protocol": "anthropic-batch", "base_url": "https://x", "model": "m"}).data
        )


def test_spec_carries_declared_window_and_cache_flag() -> None:
    spec = model_spec_from_config(
        _snapshot(
            {
                "protocol": "anthropic-messages",
                "base_url": "https://x",
                "model": "m",
                "api_key": "k",
                "context_window": 200_000,
                "supports_prompt_cache": False,
            }
        ).data
    )
    assert spec.protocol is ProtocolName.ANTHROPIC_MESSAGES
    assert spec.context_window == 200_000
    assert spec.supports_prompt_cache is False  # 显式覆盖优先于协议声明


# ---- version / session ----


def test_version_json_writes_single_frame_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["version", "--json"]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert set(payload) == {"version", "commit"}
    assert payload["commit"]  # 不允许空串糊过去（可能是 "source"，但不是假 hash）


def test_version_human_output_goes_to_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["version"]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("questor ")


def test_exec_without_config_exits_two(capsys: pytest.CaptureFixture[str], tmp_path) -> None:
    with fake_home():
        code = main(["exec", "说句话", "--cwd", str(tmp_path)])
    assert code == 2
    assert "错误" in capsys.readouterr().err
    assert capsys.readouterr().out == ""  # 失败不往 stdout 吐半句


# ---- exec 的机读输出（B-87）----


def test_exec_json_emits_only_protocol_frames(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path
) -> None:
    import questor.cli as cli

    model = FakeModel([ScriptedTurn(text="好的，完成了。")])
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda project_root=None: _snapshot(
            {
                "protocol": "anthropic-messages",
                "base_url": "https://x",
                "model": "m",
                "api_key": "k",
            }
        ),
    )
    monkeypatch.setattr(cli, "create_model", lambda spec, **kw: model)

    with fake_home():
        code = main(["exec", "说句话", "--cwd", str(tmp_path), "--json"])

    assert code == 0
    out = capsys.readouterr()
    lines = [line for line in out.out.splitlines() if line.strip()]
    assert lines, "exec --json 必须有机读输出"
    frames = [json.loads(line) for line in lines]
    assert all("method" in frame for frame in frames), "stdout 混进了非通知帧"
    assert [frame["method"] for frame in frames][0] == "run/status"


def test_exec_without_json_keeps_stdout_empty(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path
) -> None:
    """非机读模式：人类可读进度走 stderr，stdout 保持干净（同一规则的两种表现）。"""
    import questor.cli as cli

    model = FakeModel([ScriptedTurn(text="好的。")])
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda project_root=None: _snapshot(
            {
                "protocol": "anthropic-messages",
                "base_url": "https://x",
                "model": "m",
                "api_key": "k",
            }
        ),
    )
    monkeypatch.setattr(cli, "create_model", lambda spec, **kw: model)

    with fake_home():
        assert main(["exec", "说句话", "--cwd", str(tmp_path)]) == 0

    out = capsys.readouterr()
    assert out.out == ""
    assert "[RunStatus] running" in out.err and "[RunStatus] completed" in out.err


def test_exec_always_closes_the_model(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """B-83：成功与失败两条路径都要 `aclose`——否则 HTTP 客户端泄连接。"""
    import questor.cli as cli

    model = FakeModel([ScriptedTurn(text="好的。")])
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda project_root=None: _snapshot(
            {
                "protocol": "anthropic-messages",
                "base_url": "https://x",
                "model": "m",
                "api_key": "k",
            }
        ),
    )
    monkeypatch.setattr(cli, "create_model", lambda spec, **kw: model)

    with fake_home():
        assert main(["exec", "说句话", "--cwd", str(tmp_path), "--json"]) == 0

    assert model.closed is True


def test_exec_closes_model_even_when_the_run_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """失败路径同样收口：脚本不够用→模型抛错，`finally` 仍要关。"""
    import questor.cli as cli

    model = FakeModel([])  # 一轮脚本都没有，第一次调用即报错
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda project_root=None: _snapshot(
            {
                "protocol": "anthropic-messages",
                "base_url": "https://x",
                "model": "m",
                "api_key": "k",
            }
        ),
    )
    monkeypatch.setattr(cli, "create_model", lambda spec, **kw: model)

    with fake_home(), pytest.raises(AssertionError):
        main(["exec", "说句话", "--cwd", str(tmp_path), "--json"])

    assert model.closed is True
