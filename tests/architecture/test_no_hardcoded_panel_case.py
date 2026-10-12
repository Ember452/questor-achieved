"""护栏：AppShell / PanelHost 不得硬编码面板名（B-93；ADR-0020 视图注册表接口的护栏）。

新加面板只能经 `ui/src/panels/registry.ts` 的 `PANELS` 数组追加，外壳只走
`resolvePanel(activePanel)` 拿组件；一旦出现 `"review"` / `"files"` 字面 case，
就退化成"面板加一个改一次外壳"，E1 阶段几十块面板同时接入时会互相踩。

负向验证（写此测试时实测）：把 PanelHost.tsx 里 `activePanel === p.id` 改成
`activePanel === "review"` → 本测试 FAILED 指出行号；改回 → 绿。
"""

from __future__ import annotations

import pathlib
import re

UI = pathlib.Path(__file__).resolve().parents[2] / "ui" / "src"
SHELLS = [
    UI / "app-shell" / "AppShell.tsx",
    UI / "app-shell" / "PanelHost.tsx",
]
_PANEL_NAMES = "review|files|terminal|browser"
# 面板名以字面形式出现在比较/switch 语境中即违规（`case "review"` / `=== "files"` 等）
_PATTERN = re.compile(
    rf'(?:case|===|!==|==)\s*["\']({_PANEL_NAMES})["\']|["\']({_PANEL_NAMES})["\']\s*(?:===|!==|==|:)'
)


def test_app_shell_has_no_hardcoded_panel_names() -> None:
    violations: list[str] = []
    for path in SHELLS:
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _PATTERN.search(line):
                violations.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not violations, (
        "外壳源码出现面板名硬编码 case（新面板只能在 registry.ts 登记）：\n" + "\n".join(violations)
    )
