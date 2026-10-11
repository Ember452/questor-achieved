# tools —— 模块设计篇（M2.2）

状态: 随开工落盘 | 2026-10-11 | provenance: `# Reimplements FlowCoder tools/{base,registry,file_state_cache}.py — pitfalls: B-12..B-19`

## 职责与边界

八工具（用户裁决 2026-10-11）：read / edit / write / search / list / todo / run /
process。工具只声明参数（pydantic 即 schema）与执行；**授权判定在 executor**
（唯一 limen.gate 消费者，工具摸不到门——架构测试强制）；执行环境经 ToolContext 注入。

## 方法与决策

- **授权-执行序列**（executor）：未知（B-17 计熔断）≠ 禁用（不熔断）→ 参数校验失败
  转错误结果（FlowCoder 行为 11）→ 构造 ToolCallInfo（路径缺省在此填、相对路径在此
  解析为绝对——门看到规范输入）→ `decide` → deny 带完整方言 → 执行 → 并行批
  `gather(return_exceptions=True)`（B-15）→ 结果按原始调用顺序回填（B-16 的另一半）。
- **filestate 门禁**：写过先读过 + 读后未被外部改动（mtime_ns）；新建文件放行、
  外部删除后放行重建。
- **run 的进程树管理**（ADR-0007/0015）：Windows 每个命令派生即入 kill-on-close
  Job Object，超时/停止 `TerminateJobObject` 整树硬杀；POSIX 进程组 killpg。
  前台等待 = 轮询 poll，超时即"零拷贝后台移交"——进程本就在 ProcessManager 里，
  避免 communicate+收养的管道竞争。结果恒带 `sandboxed: false`（ADR-0007 诚实
  标注，B-18 无降级路径）。
- **edit 的歧义语义**：0 次匹配 → 文件不动 + difflib 最近似 3 行；>1 次 → 文件不动
  + 出现行号；绝不猜（wuu 语义，overview §3）。
- **search**：offset 分页；修订号绑定（overview 的快照分页）随 M3 review/ADR-0005
  （留痕于 development-plan）。
- **todo**：会话内存清单；落盘随 M4 orchestration（留痕）。

## 实测踩坑（对抗测试钉住，已进 pitfalls.md）

- **B-77**：pywin32 的 PyHANDLE 被 GC 时关闭底层句柄——Job Object 句柄若只留
  `int(handle)` 拷贝，Assign 时报"句柄无效"；必须把 PyHANDLE 本体存进
  ManagedProcess 持活。
- **B-78**：增量读管道必须 `read1`——`read(65536)` 阻塞到缓冲满/EOF，后台输出
  卡在首行后不可见。

## 对应测试

`test_tools_executor`（B-15/16/17 + 授权序列）、`test_tools_impl`（八工具真实文件）、
`test_tools_run_process`（B-12/13/14/19 + Job Object 整树）、
`tests/architecture/test_permission_gate_single_entry`。
