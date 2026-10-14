# behavior-sandbox-eval-fc —— FlowCoder 沙箱与评测行为规格（Questor M8 执行环境 + `evals/` 参照）

来源：FlowCoder `src/flowcoder/sandbox/`（container/pool/reaper/limits）+
`eval/`（models/runner/__main__）+ `eval-data/`。扫描日期 2026-10-11。
Questor 模块归属：M8 执行环境（容器）、`evals/`（对照评测）。

---

## 1. 容器硬化默认值（`sandbox/container.py` + `limits.py`）

| 项 | 值 | 证据 |
| --- | --- | --- |
| 用户 | `NON_ROOT_USER = "65534:65534"` | `sandbox/container.py#L27` |
| 根文件系统 | `"read_only": True` | `sandbox/container.py#L180` |
| 可写点 | tmpfs 工作目录 + `/tmp`，`mode=1777` | `sandbox/container.py#L181` |
| 网络 | `network_enabled: bool = False`（默认断网） | `sandbox/container.py#L41` |
| 资源限额 | `memory_mb=256` / `cpus=1.0` / `pids_limit=128`（构造器校验全为正） | `sandbox/limits.py#L15-19,L33-36` |
| 双层超时 | 内层：容器内 `timeout` 命令（SIGTERM → `--kill-after` 补 SIGKILL，`#L64-67`）；外层：宿主侧 grace 后 `_kill_after_grace`（`#L135,L160`） | 见左 |

- **坑**：B-35（双层超时：容器内 TERM→KILL + 宿主 grace，两层缺一不可）。

### Questor 采纳决定
M8 容器执行环境沿用全部硬化默认值；M2 的 `run` 工具宿主执行不使用容器，但"超时两层"
语义在宿主侧同样成立（工具层 wait_for + 进程层 kill 回收，见 B-13）。

## 2. 容器池（`sandbox/pool.py`）

- **租借语义**：`start()` 预热 → `lease` 借出容器 → `execute` 跑命令 → `release` 归还
  （**销毁重建**，非复用，`pool.py#L62-101`）；`mark_failed` 由调用方在异常时标记，release
  时写入台账（`#L93-94`）。
- **背压**：池空排队；等待队列超 `max_queue` 抛 `PoolExhaustedError` **快速失败**
  （`#L6` 模块注释、`#L37`、`#L118-119`）。
- **台账与清道夫**：租借记录 `LeaseRecord{leased_at,...}` 是 reaper 对账依据（`#L54-58`）；
  池创建容器统一打 label，reaper/启动清理据此识别归属、清遗留（`#L32`、`reaper.py#L43-55`）。
- **坑**：B-36（归还即销毁重建防状态串台；reaper 按 label 清遗留）。

### Questor 采纳决定
M8 沿用"归还即销毁 + label 清道夫 + 快速失败背压"；M1 仅记录语义。

## 3. 评测流水线（`eval/`）

- **被测者协议**（`eval/models.py`）：`SolutionSolver.start() -> SolverSession`、
  `session.ask(prompt) -> AgentSolution{text, input_tokens, output_tokens, turns, error}`
  （`models.py#L46-55`）——**Questor agent 挂入对照只需写一个满足 ask 协议的 adapter**；
  `SandboxExecutor.run_test(files, timeout_s) -> ExecutionOutcome{exit_code, stdout, stderr,
  timed_out}`（`#L68-71`）。
- **trial 语义**：1 次生成 + 最多 `heal_rounds` 次修复重跑（`runner.py#L96-101`）；失败时把
  stderr/stdout（截 2000 字）喂回修复 prompt；超时直接断（无有效失败信息不回喂）。
- **k-sample 首胜**：`asyncio.wait(FIRST_COMPLETED)`，首个通过即取消其余 trial
  （`runner.py#L167`）。
- **可复现**：`--temperature` 默认 0.0；`--compare` 矩阵 k=1/heal=0、k=1/heal=3、k=3/heal=0
  （第一轮扫描报告，`eval/__main__.py`）。
- **失败四分类**（`eval/failure_tax.py`）：编译错 / 逻辑错（AssertionError）/ 测试理解错
  （其他运行时异常）/ 超预算（超时或修复轮耗尽）。
- **数据格式**：`eval-data/humaneval_plus.jsonl` 每条 =
  `{task_id, prompt, canonical_solution, entry_point, test}`。
- **坑**：B-37（可复现温度默认 0 + 超时不回喂）。

### Questor 采纳决定
`evals/runner/protocol.py` 采用同构三协议（Solver/Executor/Grader），Questor 与 FlowCoder
各写 adapter，同任务喂双 agent 比失败率；失败四分类沿用做语义对齐；温度默认 0。

---

## 本区域坑条目（同步进 pitfalls.md）

| 编号 | 归属 | 一句话 | 证据 |
| --- | --- | --- | --- |
| B-35 | serve/M8 | 命令超时必须双层：容器内 TERM→KILL + 宿主 grace 兜底，缺一层就有逃逸窗口 | `sandbox/container.py#L64-67,L135,L160` |
| B-36 | （M8 执行环境） | 容器归还即销毁重建防状态串台；池创建统一打 label 供 reaper 清遗留 | `sandbox/pool.py#L32,L62-101`、`sandbox/reaper.py#L43-55` |
| B-37 | evals | 评测默认温度 0 保可复现；超时失败不回喂（无有效失败信息） | `eval/runner.py#L96-101,L167` |
