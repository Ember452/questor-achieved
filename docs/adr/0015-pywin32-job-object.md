# ADR-0015 — Windows 进程树管理引入 pywin32（平台标记依赖）

状态: accepted
日期: 2026-10-11 | 关联: ADR-0007（Windows 沙箱策略）、`tools/impl/run.py`（M2.2）、
`pitfalls.md` B-13、`docs/architecture/modules/tools.md`

## 结论

`tools` 的 `run` / `process` 工具在 Windows 上经 **Job Object** 管理进程树
（ADR-0007 第 4 条：所有命令经 Job Object 派生，超时/取消整树硬杀）。实现选
`pywin32`（`win32job` 绑定），以 **PEP 508 平台标记**声明为运行时依赖：

```toml
"pywin32>=306; sys_platform == 'win32'"
```

POSIX 安装不受影响（标记隔离）；Windows 上由 `tools/impl/run.py` 经 `sys.platform`
分支使用，POSIX 进程树走进程组（`start_new_session` + `os.killpg`），接口归一。

## 理由与取舍

- Job Object 的正确用法（CreateJobObject + JOBOBJECT_EXTENDED_LIMIT_INFORMATION 的
  JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE + AssignProcessToJobObject + TerminateJobObject）
  手写 ctypes 约几十行易错的结构体编组——正是"边界层学费 wuu 已付过"的场景，
  用维护中的绑定比重新发明编组更符合复用三分法。
- 平台标记依赖是 Windows-first 项目处理平台差异的标准形态：POSIX CI 与开发者
  不安装任何 win32 组件；`uv.lock` 保留双平台解析（B-68 的跨平台可复现纪律不受影响）。
- M2.1 的 `state/locks.py` 用 stdlib `msvcrt` 就够了（锁 1 字节不需要 win32）；
  本 ADR 只为 Job Object 开口子，不为"以后可能用到"。

## 被否决的选项

- **ctypes 手写 Job Object**：省一个依赖换几十行无测试覆盖的结构体编组；
  `JOB_OBJECT_EXTENDED_LIMIT_INFORMATION` 的对齐与 union 处理是经典错坑，
  错了不炸在派生时、炸在整树硬杀时——最不能失败的时机。
- **taskkill /T 外部命令**：靠解析外部工具输出，且没有"派生即入树"的保证
  （孙进程在 taskkill 之前逃逸）；Job Object 在创建时 Assignment，无逃逸窗口。
- **把 Job Object 推迟到 M3/M4**：B-13（超时 kill+wait 回收）、run 的后台移交、
  取消传播停进程树、PID 复用防护全部依赖进程树管理；推迟会让 run 工具
  在 Windows 上不完整，违反 ADR-0007 已定语义。

## 适用条件与失效条件

**适用**：Windows 上 run/process 的进程树管理；`pywin32` 锁定 `>=306`（win32job
稳定 API 面）。

**触发重新评审**：① pywin32 维护停滞且出现正确性缺陷 → 评估 `ctypes` 重写或
换 `win32-job` 类封装库（需新 ADR）；② 出现跨平台进程管理库（如 `psutil` 扩展）
能覆盖 Job Object 语义 → 可收敛为单一依赖；③ M8 容器执行环境落地后，
宿主进程树管理与容器内管理的关系需重新划界。
