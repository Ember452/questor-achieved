"""声明的 Python 解释器下界，必须与工具链实际执行的下界一致。

为何需要这条测试：对外承诺的下界是 >=3.12（见 pyproject 的 requires-python），
而开发机跑的是 3.13（见 .python-version）。如果 pyright 和 ruff 不钉到同一个下界，
3.13 才有的 API 会静悄悄被使用，包在 3.12 用户那里直接坏掉。
三处中任何一处漂移都是真缺陷，不是风格问题。
"""

import re
import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def _floor_from_requires_python(raw: str) -> tuple[int, int]:
    # requires-python 只取形如 "3.12" 的主次版本，其余约束文字不参与比较
    match = re.search(r"(\d+)\.(\d+)", raw)
    assert match is not None, f"cannot parse requires-python: {raw!r}"
    return int(match.group(1)), int(match.group(2))


def _floor_from_ruff_target(raw: str) -> tuple[int, int]:
    match = re.fullmatch(r"py(\d)(\d\d)", raw)
    assert match is not None, f"cannot parse ruff target-version: {raw!r}"
    return int(match.group(1)), int(match.group(2))


def _floor_from_pyright(raw: str) -> tuple[int, int]:
    major, _, minor = raw.partition(".")
    return int(major), int(minor)


def test_declared_python_floor_is_consistent_across_the_toolchain() -> None:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))

    declared = _floor_from_requires_python(data["project"]["requires-python"])
    ruff = _floor_from_ruff_target(data["tool"]["ruff"]["target-version"])
    pyright = _floor_from_pyright(data["tool"]["pyright"]["pythonVersion"])

    # 失败信息必须同时列出三处的值，否则定位不到是哪一处改了
    assert declared == ruff == pyright, (
        f"python floor drift: requires-python={declared} "
        f"ruff.target-version={ruff} pyright.pythonVersion={pyright}"
    )
