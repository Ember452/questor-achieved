# behavior-tools-fc —— FlowCoder 工具层行为规格（Questor `tools` 蓝本）

来源：FlowCoder `src/flowcoder/tools/base.py`（52 行）+ `tools/bash.py`（217 行）+
`agent/tool_execution.py`（171 行）。扫描日期 2026-10-11。Questor 模块归属：`tools`。

---

## 1. 工具契约（`tools/base.py`）

- **输入**：每个工具是 `Tool` ABC 子类，声明 `name` / `description` / `params_model`（pydantic）/
  `category`（read|write|command）/ `is_concurrency_safe`（默认 False）/ `is_system_tool` /
  `should_defer`（延迟加载标记）/ `permission_content_field` / `permission_path_field` /
  `permission_path_default`。
- **输出**：`execute(params) -> ToolResult{output: str, is_error: bool}`；`get_schema()` 由
  pydantic `model_json_schema()` 生成并弹掉 title（`tools/base.py#L44-51`）。
- **边界行为**：
  - `is_read_only` 由 category 推导（`#L40-41`）；
  - **权限层从声明的字段抽取判定值**——不声明的工具在规则匹配中视为无内容/无路径；
    触达文件系统的工具必须声明 `permission_path_field`，否则路径沙箱层会跳过它
    （`#L30-34` 注释明言）；
  - `SKIP_DIRS` 全局忽略集（.git/.venv/node_modules/__pycache__/.tox/.mypy_cache，`#L14`）。
- **证据**：见行号。

### Questor 采纳决定
沿用契约字段；`permission_*_field` 的"声明驱动判定值抽取"沿用（limen 不硬编码工具名）。

## 2. Bash 工具（`tools/bash.py`）

- **输入**：`command: str`、`timeout: int = 120`（上限 `MAX_TIMEOUT=600`，`#L22,L96,L147` 取 min）。
- **输出**：`STDOUT:\n…\nSTDERR:\n…` 分段格式化，双空时显式 `(no output)`（`#L99-107`）；
  `is_error` 由退出码语义映射判定（见下）。
- **边界行为**：
  - 超时：`asyncio.wait_for` 超时 → `proc.kill()` + `await proc.wait()` 回收 → 错误结果
    "command timed out after Ns"（`#L154-165`）；
  - **退出码语义映射**：`grep/egrep/fgrep/rg/diff/find/test/[` 的阈值是 2（exit 1 = "没有匹配/
    有差异/条件为假"，不是错误）；判定按**管道最后一段**的基础命令名（跳过 `VAR=VALUE` 前缀、
    取 basename，`#L27-74`）；默认非零即错（`#L77-91`）；
  - 解码用 `errors="replace"`，二进制输出不炸 decode（`#L170`）；
  - 双通道 off/docker 语义一致；模式切换先预热预检，失败**保持原模式并返回明确错误**
    （不静默降级，`#L128-144`）；docker 池延迟创建、池大小 2（`#L44,L195-202`）；宿主退出
    `aclose()` 清池防残留容器（`#L215-217`）；
  - **权限审批与危险命令检测在授权层先于本工具执行**，两通道语义一致："权限门永远在沙箱之前"
    （`#L7-8` 模块 docstring）。
- **坑**：B-12（退出码映射）、B-13（超时回收）、B-14（replace 解码）。

### Questor 采纳决定
全收。Questor 的 `run` 工具沿用退出码映射表与"权限门在沙箱之前"次序；超时回收写进对抗用例。

## 3. 分区算法（`agent/tool_execution.py#L28-50`）

- **输入**：一轮全部 tool_calls + 注册表。
- **输出**：`ToolBatch{concurrent, calls}[]`——**连续的** concurrency-safe 工具合并进同一并行批；
  遇到非安全工具另起串行批（`#L44-49`）。
- **边界行为**：safe 判定 = 工具存在 + 标记并发安全 + 当前未被禁用（`#L42`）——被禁用工具
  会打断并行段并走串行路径的禁用早退。

### Questor 采纳决定
沿用"连续合并"算法（非全局重排——保持模型发出的调用顺序语义）。

## 4. 执行路径与异常降级（`agent/tool_execution.py`）

- **三早退**（`execute_direct_tool_call#L82-123`）：未知工具（`is_unknown=True`，计入熔断）/
  禁用工具（错误结果，**不计** unknown）/ 正常执行；耗时统一 `time.monotonic` 计量。
- **校验与异常转结果**：`execute_validated_tool` 把 ValidationError / 任意异常都转成
  `ToolResult(is_error=True)`，**不向循环抛**（`#L71-79`）。
- **并行执行器**（`StreamingExecutor#L126-171`）：按提交序号提交、按序号回收（结果顺序与
  提交一致）；`gather(return_exceptions=True)`——单个工具异常降级为一条错误 ToolResult，
  **不拖垮整批**。
- **坑**：B-15（gather 降级）、B-16（分区打断语义）、B-17（未知 vs 禁用区分）。

### Questor 采纳决定
全收；"结果顺序 = 提交顺序"进契约测试。

---

## 本区域坑条目（同步进 pitfalls.md）

| 编号 | 归属 | 一句话 | 证据 |
| --- | --- | --- | --- |
| B-12 | tools | 退出码语义映射按管道最后一段判定，须覆盖 VAR= 前缀与 basename 提取 | `tools/bash.py#L47-91` |
| B-13 | tools | 命令超时必须 kill+wait 回收子进程，防僵尸进程残留 | `tools/bash.py#L154-165` |
| B-14 | tools | 工具输出解码必须 errors="replace"，防二进制输出炸 decode | `tools/bash.py#L170` |
| B-15 | tools | 并行批 gather 必须 return_exceptions=True，单失败降级为错误结果不拖垮整批 | `agent/tool_execution.py#L152-168` |
| B-16 | tools | 分区是"连续安全工具合并"，非安全工具打断并行段——顺序语义要保持 | `agent/tool_execution.py#L44-49` |
| B-17 | tools | 禁用工具与未知工具必须区分：只有未知计入熔断计数 | `agent/tool_execution.py#L92-114` |
| B-18 | tools | 沙箱模式切换失败保持原模式并返回明确错误，绝不静默降级 | `tools/bash.py#L128-144` |
| B-19 | tools | stdout/stderr 分段标注格式化；双空显式 "(no output)"，不留空串歧义 | `tools/bash.py#L99-107` |
