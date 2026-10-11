"""硬断言：gesta 对会话正文只追加、绝不截断改写（data-model §1 §5）。

机制：AST 扫描 ``src/questor/gesta`` 全部源码——``open(...)`` 与 ``.open(...)`` 的
字面 mode 只允许 ``a`` / ``r``（含 ``b``/``t`` 修饰），出现 ``w`` / ``x`` / ``+`` 即
违规；mode 以关键字 ``mode=...`` 传入同样覆盖。写文件的唯一合法路径是
``state.write_atomic``（临时文件 + rename 替换，用于索引类派生物）与追加模式
打开正文——append-only 契约因此有机械保证。

负向验证（2026-10-11，两轮）：
1. 在 gesta/store.py 临时注入 ``with path.open("w") as handle:`` → 初版护栏
   **没有咬住**（.open 单参数形式被 len(args)<2 跳过）——据此修正为
   双形式（内置 open 第 2 参 / 方法 open 第 1 参 + mode 关键字）；
2. 复跑注入 → FAILED（truncating write modes in gesta）→ 复原 → 绿。
"""

from __future__ import annotations

import ast
import pathlib

GESTA_SRC = pathlib.Path(__file__).resolve().parents[2] / "src" / "questor" / "gesta"

_ALLOWED_MODE_CHARS = frozenset("artb")


def _literal_mode(call: ast.Call, positional_index: int) -> str | None:
    """取出 open 调用的 mode 字面量：位置参数或 ``mode=`` 关键字；非字面量返回 None。"""
    arg: ast.expr | None = None
    if len(call.args) > positional_index:
        arg = call.args[positional_index]
    else:
        arg = next((kw.value for kw in call.keywords if kw.arg == "mode"), None)
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    return None


def _mode_violations(tree: ast.AST) -> list[str]:
    bad: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "open":
            mode = _literal_mode(node, positional_index=1)
        elif isinstance(func, ast.Attribute) and func.attr == "open":
            mode = _literal_mode(node, positional_index=0)
        else:
            continue
        if mode is None:
            continue
        # 去掉 IO 修饰后仍含 w/x/+ 的 mode 一律视为截断/独占创建（都非追加）
        if not set(mode) <= _ALLOWED_MODE_CHARS or "+" in mode:
            bad.append(f"L{node.lineno}: open(..., {mode!r})")
    return bad


def test_gesta_never_opens_files_in_truncating_modes() -> None:
    violations: list[str] = []
    for py in sorted(GESTA_SRC.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for v in _mode_violations(tree):
            violations.append(f"{py.relative_to(GESTA_SRC)} {v}")
    assert not violations, "gesta 出现截断/独占写模式——append-only 契约被破坏：\n" + "\n".join(
        violations
    )
