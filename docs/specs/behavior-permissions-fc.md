# behavior-permissions-fc —— FlowCoder 权限判定行为规格（Questor `limen` 对照蓝本）

来源：FlowCoder `src/flowcoder/permissions/checker.py`（171 行）+ `modes.py`（34 行）+
`sandbox.py`（57 行）+ `dangerous.py`（196 行）。扫描日期 2026-10-11。
Questor 模块归属：`limen`（三档语义以 wuu 为权威，本文提供**判定顺序与防御细节**的对照）。

---

## 1. 六层短路判定（`permissions/checker.py#L44-73`）

顺序命中即返回，层间无合并：

| 层 | 判定 | 证据 |
| --- | --- | --- |
| L0 | Plan 模式白名单（4 工具）+ 规划文件写入放行 | `checker.py#L20,L75-90` |
| L1 | 安全只读命令放行 → 危险命令黑名单拒绝 | `checker.py#L92-104` |
| L2 | 路径沙箱（read/write 类工具，缺路径参数=deny） | `checker.py#L106-122` |
| L3 | YAML 规则引擎 allow/deny | `checker.py#L124-131` |
| L4 | 模式矩阵兜底（6 模式 × read/write/command 三类，显式表驱动） | `checker.py#L133-140`、`modes.py#L14-29` |
| L5 | ask（人工确认） | `checker.py#L73` |

- **边界行为**：规则引擎未命中返回 None 下落；模式矩阵产出 ask 也返回 None 触发 L5。
- **坑**：B-10（L0 的 Plan 特例渗透进 checker——Questor 拒绝）、B-32（危险清单结构化可扩展）、
  B-33（模式矩阵表驱动）、B-34（短路先决不合并）。

### Questor 采纳决定（六层 → limen 单门的映射）
- L1 保留：安全命令放行 + 危险黑名单硬拒（对应 wuu HardDeny 语义）；
- L2 升级为 limen 核心：**可达性推导**（wuu `ResolvePath` 语义，见 behavior-limen-wuu.md）；
- L3 规则引擎 **M1 不做**（无使用者，YAGNI；M7 扩展面再议）；
- L4 模式矩阵 → 三档表驱动（read_only/standard/unconfined × 工具类）；
- L5 ask → `habena` 收紧型审批；
- L0 拒绝：Plan 是循环层提醒 + 计划文件属普通写域，不做权限特例。

## 2. 路径沙箱的穿越防御（`permissions/sandbox.py`）

- **允许根**：project_root（resolve 后）+ 系统临时目录 + extra（`#L15-19`）。
- **check 流程**（`#L25-57`）：expanduser → 相对路径拼根 → absolute → `resolve(strict=True)`；
  **不存在路径**：向上找最近存在祖先 → resolve 祖先 → 拼回尾部 → **必须再
  `resolve(strict=False)` 重查**——注释明言：拼回不存在尾部时可能重新引入 ".." 段，
  而 `relative_to` 是纯词法匹配不消除 ".."，不重查即可穿越沙箱（`#L45-48`）。
- **边界行为**：拒绝时返回人读原因（"路径 X 超出沙箱范围" / "无法解析路径"）。
- **坑**：B-30（二段 resolve）。

### Questor 采纳决定
二段 resolve 语义沿用进 limen 可达性推导；拒绝原因升级为 wuu 的
`error_kind + reason + model_next_action` 方言。

## 3. 危险命令与安全命令

- **危险黑名单**：8 类正则（`rm -rf /`、`mkfs.`、`dd of=/dev/`、`chmod -R 777 /`、fork bomb、
  `curl|sh`、`wget|sh`、`> /dev/sd`），**结构化清单可由用户规则追加**（`dangerous.py#L10-18,L184-187`）。
- **安全只读命令白名单**：`is_safe_command`（`dangerous.py#L160` 起）命中即放行，不走后续层。
- **坑**：B-32。

### Questor 采纳决定
沿用结构化清单模式；白名单内容重写时逐条重审（"只读不能证明无害"的判定最终归 wuu 语义）。

---

## 本区域坑条目（同步进 pitfalls.md；编号已于 2026-10-11 修正——三条曾误标为同一编号）

| 编号 | 归属 | 一句话 | 证据 |
| --- | --- | --- | --- |
| B-30 | limen | 不存在路径拼接尾部可能重新引入 ".."：resolve 祖先后必须对完整结果再 resolve(strict=False) 重查 | `permissions/sandbox.py#L45-48` |
| B-31 | limen | 触路径工具缺路径参数视为 deny 而非跳过 | `permissions/checker.py#L117-118` |
| B-32 | limen | 危险命令黑名单用结构化正则清单（可追加），不做散落 if/else | `permissions/dangerous.py#L10-18,L184-187` |
| B-33 | limen | 档位语义用显式表驱动（模式 × 工具类矩阵），不做分支散布 | `permissions/modes.py#L14-29` |
| B-34 | limen | 判定层短路先决、命中即返回，层间不做合并回溯 | `permissions/checker.py#L44-73` |
