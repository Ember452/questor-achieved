"""Questor 测试基建：fake home / fake provider / fake git。

**不属于生产路径**——只允许被测试 import（tests/architecture 会检查反向：
生产代码 import questor.testenv 视为违规）。

- `fake_home`：隔离 `~/.questor` 到临时目录，防测试污染真实会话记录；
- fake provider / fake git 随 M2 引擎与工具模块物化（占位声明见下）。
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def fake_home() -> Iterator[Path]:
    """把 HOME/USERPROFILE 指到临时目录，隔离 ~/.questor 等用户态路径。

    yield 临时目录路径；退出时清理并恢复环境变量。
    """
    original = {k: os.environ.get(k) for k in ("HOME", "USERPROFILE", "QUESTOR_HOME")}
    with tempfile.TemporaryDirectory(prefix="questor-test-home-") as tmp:
        # Windows 的 TMP 可能带 8.3 短名（CI runner 实测 C:\Users\RUNNER~1\...），
        # 而 questor_home() 会 resolve() 展开为长名（B-76）——fixture 统一先展开，
        # 保证 yield 出的路径与写入 env 的路径同一形态，测试的路径比较不因形态分裂
        tmp_path = Path(tmp).resolve()
        os.environ["HOME"] = str(tmp_path)
        os.environ["USERPROFILE"] = str(tmp_path)
        os.environ["QUESTOR_HOME"] = str(tmp_path / ".questor")
        try:
            yield tmp_path
        finally:
            for key, value in original.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
