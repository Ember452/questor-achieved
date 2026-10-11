"""硬断言：权限判定无绕过路径——limen.gate 只能被 tools/executor import。

R3（overview §9"权限判定只有一处入口"）的机械形式：工具实现与循环代码都摸不到
门，工具执行必须经 executor 的授权-执行序列。M1 占位的"三条硬断言"至此全部落地
（append-only 与状态迁移单入口见 tests/architecture/ 其余两文件）。

负向验证（2026-10-11）：在 tools/impl/read.py 临时注入
``from questor.limen.gate import decide`` → 本测试 FAILED（出现第二个消费者）→
复原 → 绿；随后删除 executor 本身再验证"守卫有齿"分支同样会咬。
"""

from __future__ import annotations

import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[2] / "src" / "questor"

# limen.gate 的唯一合法消费者（相对 SRC 的模块路径前缀）
_ALLOWED_CONSUMER = ("tools", "executor.py")
_GATE_MODULES = frozenset({"questor.limen.gate", "limen.gate"})


def _imports_gate(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in _GATE_MODULES:
            return True
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _GATE_MODULES:
                    return True
    return False


def test_gate_has_exactly_one_consumer() -> None:
    violations: list[str] = []
    consumers: list[str] = []
    for py in sorted(SRC.rglob("*.py")):
        rel = py.relative_to(SRC)
        if rel.parts[0] == "limen":
            continue  # limen 包内部（__init__ 再导出、matrix 查表）合法——门的老家
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        if not _imports_gate(tree):
            continue
        if rel.parts[:2] == _ALLOWED_CONSUMER:
            consumers.append(str(rel))
        else:
            violations.append(str(rel))
    assert not violations, (
        "limen.gate 被授权入口之外的模块 import——出现绕过权限门的路：\n" + "\n".join(violations)
    )
    # 守卫要有齿：合法消费者必须真实存在（防"消费器改名后断言空转"）
    assert consumers, "tools/executor.py 未消费 limen.gate——唯一入口名不成立，需同步本测试"
