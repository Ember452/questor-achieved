# wuu → Python(Windows) 移植风险台账

> 只读扫描对象：`d:\DEVELOP\My-project\wuu-main`（module `github.com/blueberrycongee/wuu`）
> 目标：把 wuu 的 Go 逻辑翻成 Python 并在 Windows 上运行，评估平台相关 / 系统级依赖的移植风险。
> 扫描方式：全量 `//go:build` 枚举 + 平台后缀文件 + `unsafe` / `syscall` / `golang.org/x/sys` / 文件系统语义 / PTY grep。
> 严重度：🔴阻断（Windows 无对应能力，功能缺失或安全模型失效）｜🟠高（需重写且易踩坑）｜🟡中（有现成库但语义差异需处理）｜🟢低（直接映射）。

---

## A. 给零背景读者：这是什么项目、为什么移植难、术语表

> 本节专为**没读过 wuu 源码的人**写，读完应能独立看懂后续所有风险表。已熟悉项目者可跳到 §0。

### A.1 wuu 是什么

wuu（Go 模块名 `github.com/blueberrycongee/wuu`）是一个**本地优先的 AI Agent 工作台**：命令行 `wuu` 与桌面端 Electron 共用一个 Go 内核。它本身**不调模型 API 干活**，而是编排**外部 LLM 命令行引擎**（Claude Code / Codex / Grok / Cursor / Devin 等，见 §10.2）并管理一堆**后台子进程与文件**。

**这决定了移植难点分布**：大模型业务逻辑是平台无关的纯 Python 可翻；但 wuu 的核心价值恰恰是「编排进程 + 沙箱隔离 + 文件安全 + 终端 + 凭据保管」——**全是操作系统强相关能力**。本台账列的就是这一层的坑。

### A.2 关键概念 → 代码模块对照

| 概念（新人疑问） | 通俗解释 | 对应模块 |
|---|---|---|
| **引擎 engine** | 被 wuu 拉起的外部 AI CLI（claude/codex…），每个是一个子进程 | `externalengine`、`claudeengine`、`codexengine`、`enginecatalog` |
| **MCP** | Model Context Protocol，给 Agent 挂外部工具的协议，server 常为 stdio 子进程 | `mcp` |
| **工具循环 / shell 工具** | Agent 要执行 bash/文件操作，这些命令在受控子进程里跑 | `tools`、`harness`、`loopdriver` |
| **进程管理器** | 统一负责后台进程的起、停、杀树、PTY 附着 | `process` |
| **进程写沙箱** | 限制子进程只能写工作区，防 AI 误删系统文件 | `processsandbox` |
| **执行环境 / 执行 worker** | 更重的 **Docker 容器**隔离 + 走 Unix socket 的常驻执行进程 | `executionenv`、`executionworker` |
| **app-server** | 内核对外（前端/Electron）暴露的协议层（JSON-RPC/WebSocket） | `appserver`、`sdk` |
| **凭据库 credentialstore / authstorage** | OS 凭据保险库（keyring）/ 本地 auth.json 文件 | `credentialstore`、`authstorage` |
| **插件 / 钩子 hook** | 扩展子进程与钩命令子进程，各自独立进程生命周期 | `pluginhost`、`hooks` |
| **会话持久化** | SQLite 存历史 + 文件锁保护并发 | `session`、`storelock` |
| **远程** | 连 Postgres 的远程账户 / 主机控制面 | `remote` |

### A.3 术语表（OS 概念一次讲清）

| 术语 | 是什么 | 平台 |
|---|---|---|
| **Seatbelt** | macOS 内核级沙箱，程序 `/usr/bin/sandbox-exec` 按 profile 限制文件/网络访问 | macOS |
| **Landlock** | Linux 内核(≥5.13)文件系统访问沙箱，进程自我设限只能写指定目录 | Linux |
| **Job Object** | Windows 内核对象，把一组进程捆一起统一限制资源/随句柄关闭整体杀掉 | Windows |
| **AppContainer** | Windows 应用沙箱（UWP/Edge 用），以特殊 SID 限文件/对象访问——本项目**写隔离的 Windows 落地方案** | Windows |
| **ConPTY** | Windows 伪控制台 API(1809+)，给控制台程序提供 PTY 式行为 | Windows |
| **winpty** | 更早的 Windows PTY 桥接层，`node-pty` 内部用它 | Windows |
| **PTY / pseudo-terminal** | Unix「假终端」，让非终端进程表现得像在真实终端里 | Unix |
| **DPAPI** | Windows 数据保护 API，用登录口令派生密钥加密，绑当前用户/机器 | Windows |
| **NTFS ACL** | Windows 文件访问控制表（能精确到用户/组/权限项）——对应 Unix 三组 rwx 权限位但强得多 | Windows |
| **wincred / Credential Manager** | Windows 凭据管理器，存密钥/token；API 为 `CredRead/CredWrite` | Windows |
| **reparse point / junction** | Windows 的目录「链接」，类似 Unix 符号链接但机制不同 | Windows |
| **AF_UNIX / Unix domain socket** | 本机进程间通信套接字（走文件路径） | Unix（Win10 1803+ 部分支持） |
| **flock / LockFileEx** | 文件锁：`flock`=Unix 建议锁，`LockFileEx`=Windows 区域强制锁（语义不同，见 E-4） | Unix / Windows |
| **PID 复用** | 进程死后其 ID 可能被新进程拿走；「身份指纹」= 靠进程创建时间区分，避免误杀同 ID 新进程 | 跨平台 |
| **`PR_SET_NO_NEW_PRIVS`** | Linux 内核标志：禁止进程经 setuid 等提权 | Linux |

### A.4 阅读路径建议

- **只想知道结论** → 读 §0 速览 + §6/§11 优先级清单（§11 覆盖了 §6 的旧结论）。
- **想逐条核对风险** → §5 主风险表；§8–§10 是 v2 补充的依赖层 / 运行时坑 / 架构修正（**覆盖并部分推翻** §2/§4 早期说法）。
- **§12 是方法论复盘**，与移植执行无关，可跳过。

---

## 0. 结论速览

| 结论 | 说明 |
|---|---|
| **无 cgo（自有代码）** | 全仓 0 处 `import "C"` / `#cgo`；直接依赖均为纯 Go（sqlite 走 `modernc.org/sqlite`）。所有系统调用走 `golang.org/x/sys/{unix,windows}` + `syscall`，无需处理 C 工具链。 |
| **沙箱有两层，进程级那层 Windows 空缺** | A 层 `processsandbox`：`sandbox_other.go`（`!darwin && !linux`）`platformSupported()=false`，Windows **无任何写隔离**（AppContainer 落点）。B 层 `executionenv`：**Docker 容器**（`--cap-drop=ALL`）才是 workspace 主隔离，Windows 依赖 Docker Desktop。见 §10。 |
| **Windows 凭据是功能阻塞点** | `credentialstore/keyring.go:54` `NewDesktopStore()` 对 `GOOS != darwin` **直接返回错误**——桌面凭据路径 macOS-only；wincred 后端虽可用但被代码挡住。移植必须先解此约束。 |
| **PTY 有两套，Go 层 Windows 空缺** | Go `manager_windows.go` `ptySupported()=false`（降级 pipe）；但 **desktop 壳自带 `node-pty`（winpty）**已能跨平台起终端。Windows 终端可行，取决于"PTY 属主给谁"。见 §10.2。 |
| **执行 worker 在 Windows 直接禁用** | `socket_windows.go` 两个入口都 `return errors.New("execution workers require a Unix environment")`，整个 `executionworker` 子系统 Windows 不可用。 |
| **权限位安全模型在 Windows 失效** | `securefs` 全靠 `0o600/0o700`，Windows 的 `chmod` 只映射只读属性，组/其他位是 no-op——凭据文件的"其他用户不可读"保证在 Windows 不成立，必须换 ACL/DPAPI。 |
| **进程树终止语义差异** | Unix 靠 `kill(-pgid)` 打进程组；Windows 靠 `taskkill /T /F` 沿父链走，二者对"孤儿进程/脱离父链的孙进程"行为不同。 |

---

## 1. Build tag 文件清单（逐个说明用途）

### 1.1 进程沙箱 `internal/processsandbox/`（**重点**）

| 文件 | build tag | 用途 |
|---|---|---|
| `sandbox_darwin.go` | `darwin` | **Seatbelt**：调 `/usr/bin/sandbox-exec -p <profile>`，把原命令改写成 `sandbox-exec -- <cmd>`；额外用 `/usr/bin/getconf DARWIN_USER_CACHE_DIR` 解析 Keychain 的 MDS 缓存目录并放行 `file-write*`；`filepath.EvalSymlinks` 解析缓存真实路径。 |
| `sandbox_linux.go` | `linux` | **Landlock**：`init()` 里识别 `--wuu-filesystem-sandbox` 自重执行 helper；`landlockABI()` 要求 ABI≥3；用 `unix.Syscall(SYS_LANDLOCK_CREATE_RULESET/ADD_RULE/RESTRICT_SELF)` + `Prctl(PR_SET_NO_NEW_PRIVS)` 施加"仅 WritableRoots 可写"策略，再 `unix.Exec` 起真实命令；策略经 base64(JSON) 走 argv 传入。 |
| `sandbox_other.go` | `!darwin && !linux`（**含 Windows**） | **空实现 / 显式不支持**：`platformSupported()=false`；`applyPlatform` 返回 `ErrUnavailable on <GOOS>`。 |

> ⚠️ Windows 走的就是 `sandbox_other.go` —— **当前无任何写隔离**。见风险项 E-1。

### 1.2 MCP 子进程组 `internal/mcp/`（**重点：Job Object**）

| 文件 | build tag | 用途 |
|---|---|---|
| `process_windows.go` | `windows` | **Job Object**：`CreateJobObject` + `SetInformationJobObject(JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE)`；子进程以 `CREATE_SUSPENDED` 起、`AssignProcessToJobObject` 后再 `NtResumeProcess`（`ntdll.dll` via `NewLazySystemDLL`）保证早期后代继承 job；`killProcessTree` 用 `TerminateJobObject`；`OpenProcess(PROCESS_SET_QUOTA\|TERMINATE\|SUSPEND_RESUME)`。失败降级为直接 `Process.Kill`。 |
| `process_unix.go` | `!windows` | `Setpgid:true` 起新进程组，`killProcessTree` = `syscall.Kill(-pid, SIGKILL)`。 |

### 1.3 进程身份指纹 `internal/process/process_identity_*`（**重点**）

| 文件 | build tag | 用途 |
|---|---|---|
| `process_identity_darwin.go` | `darwin` | `unix.SysctlKinfoProc("kern.proc.pid", pid)` 取 `P_starttime` 作为身份，防 PID 复用。 |
| `process_identity_linux.go` | `linux` | 读 `/proc/<pid>/stat`（starttime ticks）+ `/proc/stat`（btime）+ `/proc/sys/kernel/random/boot_id` + `/proc/self/auxv`（AT_CLKTCK，`#define linuxAuxClockTicks=17`），换算启动时间并生成 `linux-v1:<bootid>:<ticks>` 身份。 |
| `process_identity_windows.go` | `windows` | `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` + `GetProcessTimes` 取创建时间 FILETIME（100ns），生成 `windows-v1:<ticks>`。**Windows 已有实现**，Python 用 `psutil` 或 `GetProcessTimes` 直接映射。 |

### 1.4 进程/PTY 管理器 `internal/process/manager_*`（**重点**）

| 文件 | build tag | 用途 |
|---|---|---|
| `manager_unix.go` | `!windows` | **PTY**：`github.com/creack/pty` 开 master/slave；`Setsid+Setctty` 让子进程成为会话首进程并绑定控制终端；自写 `unix.Poll` 循环 + `SetNonblock` + `IoctlSetWinsize(TIOCSWINSZ)` 调整窗-size；进程组 `Setpgid` + `Getpgid` + `signalProcessGroup(SIGTERM/SIGKILL)`；`verifyProcessGroup` 防 PID 复用；`processExists` = `kill(pid,0)`。 |
| `manager_windows.go` | `windows` | `ptySupported()=false`，`startPTYProcess/Write/resizePTY` 全部返回"不支持"错误；`configureProcessGroup` = `CREATE_NEW_PROCESS_GROUP + HideWindow`；`taskkillTree` = `taskkill /pid /t [/f]` 沿父链杀树；`processExists` = `OpenProcess+GetExitCodeProcess(STATUS_PENDING)`。 |

### 1.5 执行 worker 套接字 `internal/executionworker/socket_*`

| 文件 | build tag | 用途 |
|---|---|---|
| `socket_unix.go` | `!windows` | **Unix domain socket**：`/tmp/wuu-execution-<uid>/worker-<sha1>.sock`；`os.Lstat` 校验目录权限 `0077` 且 owner uid 匹配；`syscall.Flock(LOCK_EX)` 协调冷启动；`net.Listen("unix")`+`Chmod 0600`；`Setsid` detach 起 worker；`ExtraFiles`（fd 3）+ 就绪字节做无 sleep 启动握手；`unixConn.CloseWrite()` 半关闭。 |
| `socket_windows.go` | `windows` | **禁用**：`Connect` / `ServeSocket` 均返回 `"execution workers require a Unix environment"`。 |

### 1.6 外部引擎 / 钩子进程

| 文件 | build tag | 用途 |
|---|---|---|
| `internal/externalengine/process_unix.go` | `!windows` | `Setpgid` + `Kill(-pid, SIGKILL)`。 |
| `internal/externalengine/process_windows.go` | `windows` | `killChild` = `taskkill /T /F /PID` 后 `Process.Kill`；`configureChild` 空实现。 |
| `internal/hooks/hook_process_unix.go` | `!windows` | `Setpgid` + `Cancel` 里 `Kill(-pid, SIGKILL)`（`ESRCH`→`ErrProcessDone`）。 |
| `internal/hooks/hook_process_windows.go` | `windows` | `CREATE_NEW_PROCESS_GROUP+HideWindow`；`Cancel` 起独立 2s ctx 调 `taskkill /t /f`。 |

### 1.7 Shell 解析 `internal/shellpath/resolve_*`

| 文件 | build tag | 用途 |
|---|---|---|
| `resolve_unix.go` | `!windows` | `LoginBash()` = `bash -lc`；`Sh()` = `sh -c`；`CommandEnv` 原样透传。 |
| `resolve_windows.go` | `windows` | `sync.OnceValues` 缓存 `findGitBash`（探测固定路径 + PATH）；`LoginBash()` 用 **Git Bash `-c`（非 `-lc`）**；`Sh()` 复用 `LoginBash()`（Windows 无 `/bin/sh`）；`CommandEnv` 显式注入 Git 工具目录。 |

### 1.8 登录 shell PATH 探测 `internal/enginecatalog/lookup_*`

| 文件 | build tag | 用途 |
|---|---|---|
| `lookup_unix.go` | `unix` | 起 `$SHELL`（`-i -l -c` 或 fish 专用脚本）带标记 `__WUU_PATH_START__/END__` 抓 PATH（吸收 nvm/mise/Homebrew）；`Setpgid` + `Kill(-pid)` 清理；`testing.Testing()` 时跳过。 |
| `lookup_windows.go` | `windows` | `readLoginShellPath()` 直接返回 `nil`（**探测被跳过**）。 |

### 1.9 文件锁族（14 对，全部同一 Unix/Windows 双实现模式）

均为 `!windows` 用 `syscall.Flock(LOCK_EX[|LOCK_NB])` / `windows` 用 `LockFileEx[|LOCKFILE_FAIL_IMMEDIATELY]`+`UnlockFileEx`（`ERROR_LOCK_VIOLATION`/`EWOULDBLOCK` 判"已被占"）：

- `internal/authstorage/filelock_{unix,windows}.go`
- `internal/agentcontrol/worker_execution_lock_{unix,windows}.go`
- `internal/storelock/store_lock_{unix,windows}.go`
- `internal/remote/host/process_lock_{unix,windows}.go`
- `internal/session/appserver_presence_lock_{unix,windows}.go`
- `internal/session/plugin_generation_lock_{unix,windows}.go`
- `internal/session/thread_execution_lock_{unix,windows}.go`
- `internal/session/thread_lifecycle_lock_{unix,windows}.go`
- `plugins/memory/filelock_{unix,windows}.go`

> 另 `internal/session/inference_process_alive_{unix,windows}.go`：unix = `kill(pid,0)`（`EPERM` 也算活）；windows = `OpenProcess+GetExitCodeProcess==STATUS_PENDING`（`ERROR_ACCESS_DENIED` 也算活）。

### 1.10 测试与专用 build tag（非移植目标，仅记录）

`//go:build darwin/linux/windows/!windows` 的 `_test.go`（如 `tool_shell_sandbox_darwin_test.go`、`tool_bash_sandbox_darwin_test.go`、`tool_shell_process_test.go`、`sandbox_linux_test.go`、`manager_pty_*_test.go`、`inference_process_alive_windows_test.go`）；以及功能开关 tag `//go:build wuu_real_model_e2e`（`internal/runtime/real_model_e2e_test.go`）。Python 侧对应"按平台 skip 的测试"，用 `pytest.mark.skipif` 即可。

---

## 2. cgo / 系统调用 / 特权 API 用法汇总

| # | API / 机制 | 出现位置 | 平台 |
|---|---|---|---|
| A1 | **Seatbelt `sandbox-exec`** 外部二进制 + `getconf` | `sandbox_darwin.go` | darwin |
| A2 | **Landlock** syscall（`LANDLOCK_CREATE_RULESET/ADD_RULE/RESTRICT_SELF`）+ `Prctl(PR_SET_NO_NEW_PRIVS)` + `unsafe.Pointer` 构造规则结构体 + `unix.Open(O_PATH\|O_CLOEXEC)` + `unix.Exec` 自重执行 | `sandbox_linux.go` | linux |
| A3 | **Job Object**（`CreateJobObject`/`SetInformationJobObject`/`AssignProcessToJobObject`/`TerminateJobObject`）+ `CREATE_SUSPENDED` + `NtResumeProcess`（ntdll 懒加载）+ `unsafe.Pointer/Sizeof` | `mcp/process_windows.go` | windows |
| A4 | **进程时间/存活** `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)`+`GetProcessTimes`+`GetExitCodeProcess` | `process_identity_windows.go`、`manager_windows.go`、`inference_process_alive_windows.go` | windows |
| A5 | **文件区域锁** `LockFileEx/UnlockFileEx` + `Overlapped` | 9 个 `*_windows.go` 锁文件 | windows |
| A6 | **POSIX 文件锁** `syscall.Flock` | 9 个 `*_unix.go` 锁文件 + `socket_unix.go` | unix |
| A7 | **进程组信号** `Setpgid/Setsid/Setctty` + `Kill(-pgid, SIGTERM/SIGKILL)` + `Getpgid` | `manager_unix.go`、`mcp/process_unix.go`、`externalengine`、`hooks`、`enginecatalog/lookup_unix.go` | unix |
| A8 | **PTY** `creack/pty` + `unix.Poll/SetNonblock/IoctlSetWinsize(TIOCSWINSZ)/Read/Write` + `SyscallConn().Control` | `manager_unix.go` | unix |
| A9 | **Unix domain socket** `net.Listen/Dial("unix")` + `CloseWrite` + `/tmp` + `os.Getuid` + `ExtraFiles`(fd 继承) | `socket_unix.go` | unix |
| A10 | **sysctl proc** `unix.SysctlKinfoProc` | `process_identity_darwin.go` | darwin |
| A11 | **/proc 伪文件系统** `stat`/`btime`/`boot_id`/`auxv` | `process_identity_linux.go` | linux |
| A12 | **信号捕获** `signal.NotifyContext(os.Interrupt, syscall.SIGTERM)`、`signal.Notify(brokenPipe, syscall.SIGPIPE)` | `cmd/wuu/remote.go`、`exec_lifecycle.go`、`cmd/wuu-server/main.go`、`plugin_dev.go` | 全平台（SIGPIPE 在 Windows 从不产生，见 §9） |
| A13 | **无令牌/特权提升 API** | 全仓 grep `OpenProcessToken/AdjustTokenPrivileges/CreateRestrictedToken/CreateProcessWithToken/ImpersonateLoggedOnUser/LogonUser` → **0 命中**（注意：wincred/ConPTY/ACL 仍属 Windows 系统 API，见 §8） | — |

> ✅ 关键利好：**当前代码不使用任何 Windows 访问令牌 / 特权提升 API**，因此移植不需要处理"以受限令牌起进程"这类高危改造。写隔离若要上 Windows，是**从零加 AppContainer**，而非"翻译已有令牌代码"。
> ⚠️ `unsafe.Pointer` + 结构体内存布局（Landlock 规则、Job Object 限制）在 Go 里手工对齐；Python 无指针，改用 `ctypes`/`struct` 或封装库可绕开这一整类 UB 风险。

---

## 3. 文件系统语义假设

| # | 假设 | 出现位置 | Windows 差异 |
|---|---|---|---|
| C1 | **权限位 0o600/0o700 承载安全边界**（凭据/会话库/父目录 owner-only） | `internal/securefs/securefs.go`（全模块）、`authstorage`、各 `filelock` 用 `securefs.FileMode` | Windows `os.Chmod`→`SetFileAttributes`，仅"写→只读"一个 bit；**组/其他位是 no-op**，"其他用户不可读"不成立。 |
| C2 | **符号链接安全判定** `os.Lstat` + `info.Mode()&os.ModeSymlink` + `filepath.EvalSymlinks`，marker/缓存路径拒绝软链 | `securefs.go`（`TightenHomeOnce`/`tightenOne`/`SafeToPrint`）、`sandbox_darwin.go` | Windows 软链需 `SeCreateSymbolicLinkPrivilege`/开发者模式；junction/reparse point 不以 `ModeSymlink` 报告，检测逻辑**静默失效**。 |
| C3 | **rename 原子写**（临时文件 + `os.Rename` 覆盖，崩溃不留半文件） | `securefs.WriteFileAtomic`、`plugins/memory/plugin.go`、`workspace_memory.go` | Windows `MoveFileEx(REPLACE_EXISTING)` 跨卷/目标被占用时语义与时序不同，"原子"弱于 POSIX。 |
| C4 | **`/tmp` 与 `os.Getuid()` 硬编码** 构造私有 socket 目录 | `socket_unix.go`（`/tmp/wuu-execution-<uid>`） | Windows 无 `/tmp`（`%TEMP%`）；`Getuid()` 返回 **-1**，目录名 `wuu-execution--1` 失去隔离意义。 |
| C5 | **大小写敏感路径比较** `filepath.IsAbs`/`rel` 前缀判定散落多处 | `toolkit.go`、`worktree/open_or_create.go`、`tools/tool_search.go`、`tool_context.go`、`git.go` | Windows 大小写不敏感、路径形式多（`C:\`、`\\srv\share`、`D:foo`）。**已在少数点处理**：`worktree.go:692` 用 `strings.EqualFold`（GOOS==windows 时）、`toolkit.go:1520` env 名大写归一、`shellCommandReferencesUNCPath` 拦 NTLM 泄漏。 |
| C6 | **权限收紧遍历** `TightenRecursive` BFS walk chmod 归一 + `.permissions-v1` marker | `securefs.go` | 依赖 C1/C2；Windows 上 chmod 归一无效，遍历会静默"成功"但没真正收紧。 |

---

## 4. PTY / 终端相关

| # | 点 | 出现位置 | Windows 现状 |
|---|---|---|---|
| D1 | PTY 抽象层 `ptySupported`/`startPTYProcess` | `manager_unix.go`（真 PTY） vs `manager_windows.go`（返回不支持） | Windows **降级为 pipe 模式**；tty 交互（全屏 TUI、`^C` 行编辑、SIGWINCH resize）在 pipe 下不可用。 |
| D2 | 终端 resize `TIOCSWINSZ` | `manager_unix.go:resizePTY` | Windows 需 `SetConsoleWindowInfo`/ConPTY resize，无 ioctl 等价物。 |
| D3 | 内嵌终端 / 交互式 CLI（bash 工具、MCP stdio、外部引擎） | `process`、`mcp`、`externalengine`、`hooks` | wuu **未使用 ConPTY**（`windows-pty`/`CreatePseudoConsole` 全仓 0 命中）；凡标 `tty:true` 的调用在 Windows 都走无 PTY 分支。 |

> ConPTY（`CreatePseudoConsole`，Win10 1809+）是补齐 D1–D3 的官方路径；Python 侧对应 `pywinpty`。

---

## 5. 风险台账（风险项 / 位置 / Windows 现成解 / Python 替代方案 / 严重度）

### E-1 进程写隔离（沙箱）

| 风险项 | 位置 | Windows 现成解 | Python 替代方案 | 严重度 |
|---|---|---|---|---|
| Windows 沙箱空实现，`ErrUnavailable` | `processsandbox/sandbox_other.go` | **无现成等价**（Seatbelt/Landlock 皆非 Windows） | **AppContainer** 写隔离升级路径：`CreateAppContainerProfile`→受限 SID→只在 `WritableRoots` 上 `SetNamedSecurityInfoW` 授予该 SID `GENERIC_WRITE`，其余目录不授权；以 `CreateProcess` 带 `PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITY`（`UPDATE_PROC_THREAD_LIST`）起子进程。**Python**：`pywin32`/`ctypes` 调 `kernel32.Advapi32`，或走 `windows.security` 封装；无纯标准库方案，需自建 FFI。 | 🔴 |
| Landlock ABI≥3 + 自重执行 helper（fd/argv base64 策略） | `sandbox_linux.go` | Linux 专有 syscall，Windows 无 | Python 在 Windows **不复刻 Landlock**；写隔离统一改 AppContainer（见上）；Linux 分支若也要跑 Python 可保留（`prctl`/`landlock` via `ctypes`），但属另一目标平台。 | 🔴 |
| Seatbelt profile 生成（含 Keychain MDS 例外） | `sandbox_darwin.go` | darwin 专有 | Windows 无关；仅当同码要跑 mac 时才需 `sandbox-exec`（Python 仍用 subprocess 起 `sandbox-exec`）。 | 🟢(Win) |
| `Policy`/`validatePolicy` 策略模型（Mode/WorkspaceWrite/WritableRoots） | `processsandbox/*.go` | 数据模型平台无关 | 直接移植为 Python dataclass/enum；Windows 后端把它编译成 AppContainer ACL 计划。 | 🟡 |

### E-2 子进程组与树终止

| 风险项 | 位置 | Windows 现成解 | Python 替代方案 | 严重度 |
|---|---|---|---|---|
| MCP 进程组 = Job Object（`KILL_ON_JOB_CLOSE` + `CREATE_SUSPENDED` + `NtResumeProcess`） | `mcp/process_windows.go` | ✅ Windows 原生 Job Object | **`psutil`**：`p.wait` 无法杀树时，用 Job Object。纯 py 方案：`pywin32`/`ctypes` `CreateJobObjectW`+`SetInformationJobObject`+`AssignProcessToJobObject`，`CloseHandle` 即杀树（等价 KILL_ON_JOB_CLOSE）；或退而用 `taskkill /PID /T /F`。**subprocess 本身不支持 job**。 | 🟠 |
| unix `kill(-pgid, SIGKILL)` 打进程组 | `mcp/process_unix.go`、`manager_unix.go`、`externalengine`、`hooks` | Windows **无 POSIX 进程组** | Python：`taskkill /T`（父链）或 Job Object；**注意语义差**——孤儿/脱离父链的后代 Windows 杀不到，Job Object 才能兜住全树。 | 🟠 |
| `taskkill` 外部命令做树杀（非优雅、无 SID 保证） | `manager_windows.go`、`externalengine/process_windows.go`、`hook_process_windows.go` | ✅ 已是 Windows 方案 | Python 直接 `subprocess.run(["taskkill","/PID",pid,"/T","/F"], creationflags=CREATE_NO_WINDOW)`；建议升级为 Job Object 以覆盖 `taskkill` 漏掉的脱离父链进程。 | 🟡 |
| 进程身份指纹（防 PID 复用） | `process_identity_windows.go` | ✅ `GetProcessTimes` 创建时间 | Python：`psutil.Process(pid).create_time()` 生成 `windows-v1:<create_time>` 身份；unix 分支的 `/proc`、`sysctl` 移植用 `psutil` 统一跨平台。 | 🟢 |

### E-3 PTY / 终端

| 风险项 | 位置 | Windows 现成解 | Python 替代方案 | 严重度 |
|---|---|---|---|---|
| tty 模式进程（内嵌终端 / TUI / 交互式 bash） | `manager_unix.go`（pty）/`manager_windows.go`（不支持） | ✅ ConPTY（Win10 1809+），但 **wuu 未用** | Python 用 **`pywinpty`**（`PtyProcess.spawn`）实现 ConPTY；resize 用 `setwin((cols,rows))`。若无 `pywinpty`，退回 `subprocess` 管道 + 手动 `\r\n`/ANSI 处理（体验降级）。 | 🔴 |
| `TIOCSWINSZ` 窗口尺寸 ioctl | `manager_unix.go:resizePTY` | ConPTY / `SetConsoleWindowInfo` | `pywinpty.setwin`；纯标准库无方案。 | 🟠 |
| 非阻塞 poll 读写循环（master fd） | `manager_unix.go:copyPTYOutput/Write/poll` | Windows 控制台/管道模型不同（无 `unix.Poll` on char device） | Python：`asyncio` + `pywinpty` 的 reader 线程，或 `select` 不适用于 win console，需用 overlapped IO / 后台线程 drain。 | 🟠 |

### E-4 文件锁与单实例协调

| 风险项 | 位置 | Windows 现成解 | Python 替代方案 | 严重度 |
|---|---|---|---|---|
| `syscall.Flock`（建议锁，进程级，跨平台不存在） | 9 个 `*_unix.go` 锁 | Windows 无 `flock` | Python：Windows 用 `msvcrt.locking(LK_LOCK)` 或 `pywintypes` `LockFileEx`；跨平台可用 `portalocker`（自动选 fcntl/msvcrt）或 `filelock` 库。 | 🟡 |
| `LockFileEx`/`UnlockFileEx` + `Overlapped`（区域强制锁） | 9 个 `*_windows.go` 锁 | ✅ Windows 原生 | `portalocker`（Windows 后端即 `LockFileEx`）或 `pywin32`；**注意** Windows 区域锁与"文件被独占打开"耦合，Python 需持有同一句柄。 | 🟢 |
| `LOCKFILE_FAIL_IMMEDIATELY`/`ERROR_LOCK_VIOLATION` 判非阻塞占用 | `store_lock_windows.go`、`worker_execution_lock_windows.go` | ✅ | `portalocker` non-blocking 模式抛异常即等价；或 `msvcrt.locking(..., LK_NBRLCK)`。 | 🟢 |
| 进程存活探测 `kill(pid,0)`（EPERM 视活） | `inference_process_alive_unix.go`、`manager_unix.go:processExists` | Windows `OpenProcess+GetExitCodeProcess` | Python：`psutil.pid_exists(pid)` 或 `os.kill(pid,0)`（Windows 下 `os.kill` 语义不同，建议 `psutil.Process(pid).is_running()`）。 | 🟢 |

### E-5 执行 worker（Unix domain socket）

| 风险项 | 位置 | Windows 现成解 | Python 替代方案 | 严重度 |
|---|---|---|---|---|
| `net.Listen("unix")` + `/tmp` + `os.Getuid` + `Chmod 0600` + 目录权限校验 | `socket_unix.go` | Win10 1803+ **支持 AF_UNIX**（`socket.AF_UNIX`），但**权限模型/`CloseWrite`/`ExtraFiles` fd 继承**不同或缺失 | Python：`socket.socket(AF_UNIX, SOCK_STREAM)`（Win10+）走命名管道路径即可；但 `socketPath` 的 `/tmp`+`Getuid`+`0077` 校验需整体重写为 Windows ACL；`ExtraFiles` 就绪管道 fd 继承在 Windows **不可用**，改端口/named event。 | 🔴 |
| `Connect`/`ServeSocket` Windows 直接返回错误 | `socket_windows.go` | 功能整体缺失 | Python 需在 Windows **新实现** worker 生命周期（named pipe `asyncio` 或 TCP loopback + 令牌），否则该子系统不可移植。 | 🔴 |
| 冷启动 `Setsid` detach + 就绪字节握手 | `socket_unix.go:84-100` | 无 `Setsid` | Python：`subprocess` `creationflags=DETACHED_PROCESS\|CREATE_NEW_PROCESS_GROUP` + 就绪改用 named event / TCP 探测。 | 🟠 |

### E-6 Shell / PATH 解析

| 风险项 | 位置 | Windows 现成解 | Python 替代方案 | 严重度 |
|---|---|---|---|---|
| `bash -lc` 登录 shell（版本管理器/PATH 注入） | `shellpath/resolve_unix.go`、`enginecatalog/lookup_unix.go` | Git Bash `-c`（`resolve_windows.go` 已实现）；登录 shell PATH 探测被禁用（`lookup_windows.go`→nil） | Python：`shutil.which("bash")`/定位 Git Bash；PATH 探测在 Windows 改读注册表/`os.environ["PATH"]`（无 `$SHELL -i -l -c` 语义）。 | 🟡 |
| `CommandEnv` 注入 Git 工具目录、MSYS 路径转换（`//server`↔UNC） | `shellpath/resolve_windows.go` + `gitBashCommandEnv` | ✅ 已有 | Python 移植需复刻 Git Bash 路径翻译（MSYS `/c/...`↔`C:\...`）；注意 `shellCommandReferencesUNCPath` 的 **NTLM 凭据泄漏防护**（`\\srv` / `//srv` 都要拦）。 | 🟠 |
| `set +x` / `command printf` 标记抓 PATH | `lookup_unix.go:posixPathScript` | POSIX shell 专有 | Windows 用 PowerShell/CMD 等价脚本或跳过（现状即跳过）。 | 🟢 |

### E-7 文件系统安全边界（`securefs`）

| 风险项 | 位置 | Windows 现成解 | Python 替代方案 | 严重度 |
|---|---|---|---|---|
| **凭据/会话文件 owner-only 权限位（0o600/0o700）** | `securefs.go` 全模块 + `authstorage` | ❌ `chmod` 仅只读 bit；组/其他位 no-op → 机密隔离**失效** | Python 在 Windows 用 **NTFS ACL**：`pywin32` `SetNamedSecurityInfo` 只授当前用户 SID `FULL/READ`，关闭继承；凭据本身建议 **DPAPI**（`win32crypt.CryptProtectData`，用户/机器绑定）或 Windows Credential Manager。 | 🔴 |
| `TightenRecursive`/`TightenHomeOnce` 启动一次性权限迁移 + `.permissions-v1` marker | `securefs.go` | Windows 上 chmod 归一无效，遍历静默"假成功" | Python：迁移逻辑改走 ACL 收紧；marker 软链检测改 `os.stat(...).st_reparse_tag`/`FILE_ATTRIBUTE_REPARSE_POINT`。 | 🟠 |
| `filepath.EvalSymlinks` + 拒绝软链写 | `securefs.go`、`sandbox_darwin.go` | Windows 软链/junction 不同 | Python：`os.path.realpath` 比对；reparse point 用 `ctypes` 查 `DeviceIoControl(FSCTL_GET_REPARSE_POINT)` 或 `pywin32`。 | 🟠 |
| `WriteFileAtomic`（temp+rename 崩溃安全） | `securefs.go` | `MoveFileEx(REPLACE_EXISTING)` 语义弱 | Python：`os.replace`（Windows 可覆盖但非跨卷原子）；目标被占用需重试；机密建议配合 ACL 先建后写。 | 🟡 |
| 大小写不敏感路径比较 | `worktree.go:692`、`toolkit.go:1520` 等 | 已部分用 `EqualFold`/大写归一 | Python：路径键统一 `os.path.normcase()`；env 用 `os.environ`（Windows 本就大小写不敏感，注意别重复键）。 | 🟡 |

### E-8 信号与生命周期

| 风险项 | 位置 | Windows 现成解 | Python 替代方案 | 严重度 |
|---|---|---|---|---|
| `signal.NotifyContext(os.Interrupt, SIGTERM)` 优雅退出 | `cmd/wuu/remote.go`、`exec_lifecycle.go`、`wuu-server/main.go` | Windows 有 CTRL_C_EVENT（≈SIGINT）；**SIGTERM 基本不投递** | Python：`signal.SIGINT` 可用；`SIGTERM` Windows 收不到，改 Win32 `SetConsoleCtrlHandler`（`pywin32`/`win32console`）或 Ctrl-Break 处理。 | 🟡 |
| `signal.Notify(brokenPipe, syscall.SIGPIPE)`（让写关闭管道返回 EPIPE） | `exec_lifecycle.go:18` | **Windows 从不产生 SIGPIPE**（Go/Python 网络走 Winsock，写断管返回 `OSError`/异常而非信号） | Python：删掉 SIGPIPE 注册（`signal.SIGPIPE` 在 Windows 不存在会 `AttributeError`）；捕获 `BrokenPipeError`/`OSError(22/109)` 处理断管。 | 🟡 |
| `SIGHUP`（挂断）语义 | unix 通用 | Windows 无 | Python：忽略或改服务停止事件。 | 🟢 |

### E-9 无风险 / 利好项

| 风险项 | 位置 | 结论 | 严重度 |
|---|---|---|---|
| cgo / C 工具链 | 全仓 | **0 处**，无需处理 C ABI/交叉编译 | ⚪ |
| Windows 访问令牌 / 特权 API | 全仓 grep | **0 处**（无 `CreateRestrictedToken`/`AdjustTokenPrivileges` 等），令牌类高危移植负担为零 | ⚪ |
| 进程身份 windows 实现、文件锁 windows 实现、Git Bash shellpath | 对应 `*_windows.go` | **已有 Windows 原生实现**，Python 直接映射同名 Win32 调用 | ⚪ |

---

## 6. 移植优先级建议（按台账严重度）

1. 🔴 **写隔离（E-1）**：Windows 是空白，规划 AppContainer 后端，把 `Policy{Mode,WritableRoots}` 编译成"受限 SID + 定向 ACL"，用 `CreateProcess` 的 capability 属性落地。Python 无标准库方案，预留 `ctypes`/`pywin32` FFI 工作量。
2. 🔴 **执行 worker（E-5）**：`socket_windows.go` 是"直接禁用"，Windows 需从零起（named pipe / loopback + 令牌），并替换 `ExtraFiles` fd 继承握手。
3. 🔴 **PTY / 内嵌终端（E-3）**：wuu 未用 ConPTY，Windows 交互体验缺失；引 `pywinpty`。
4. 🔴 **文件权限安全边界（E-7）**：`securefs` 的 0o600 模型在 Windows 静默失效，最高危的"假安全"；必须换 ACL + DPAPI/Credential Manager。
5. 🟠 **进程树终止（E-2）**：`kill(-pgid)` 的 POSIX 语义无 Windows 等价；统一升级 Job Object 兜全树，避免 `taskkill /T` 漏杀。
6. 🟡 **文件锁 / 信号 / shellpath（E-4/E-6/E-8）**：有现成库（`portalocker`、`SetConsoleCtrlHandler`、`os.path.normcase`），按语义差异逐点替换即可。

---

## 7. 扫描覆盖说明（v2 已修订）

- **v1 缺陷**：多处 grep 被静默截断在 25 条，build tag 未完整枚举，`internal/` 77 个子包只精读约 10 个，未查 go.mod 依赖层平台绑定，桌面壳 / Docker 执行子系统未展开。已在 v2 全部补齐（见第 8–11 节）。
- **v2 已完整枚举**：
  - `//go:build` 全量：**39 个平台后缀文件** + `sandbox_other.go` + `enginecatalog/lookup_unix.go`（`unix` tag）+ `executionworker/socket_windows.go` + `authstorage/filelock_*`；共约 42 个非测试平台文件（Glob + 分片 grep 交叉验证）。
  - `golang.org/x/sys/windows` 非测试引用：**14 个文件**（未截断，完整）——mcp/process_windows、manager_windows、process_identity_windows、9 个 `*_lock_windows.go`、hooks/hook_process_windows、externalengine 不用 x/sys/windows 只 taskkill。
  - `golang.org/x/sys/unix` 非测试引用：**3 个文件**（sandbox_linux、process_identity_darwin、manager_unix）。
  - `syscall` 标准库非测试引用：**23 个文件**（含 `manager.go`/`claudeengine/transport.go`/`cmd/wuu/*.go` 等无平台后缀文件里的跨平台调用）。
  - `runtime.GOOS` 非测试分支：**21 个位置**（分 4 组 grep 交叉去重）——逐条见 §9。
- **v2 依赖层已审**（`go.mod` 47 行 + 使用位点 grep）：见 §8。
- **未展开**：`desktop/node_modules/**`（Electron 打包产物、node-pty/winpty、monaco-editor）——仅确认存在与用途，不逐行；`desktop/native/cua-mac/**` Swift 代码（macOS CUA/截图/输入注入，**非 Go**，超出本次 Go→Python 范围，仅登记为 macOS-only 事实）。测试文件仅记录 tag 与 `syscall.Umask` 等 Windows 不支持调用，不逐行。
- **本台账仍为静态只读扫描**，未运行构建/测试；🔴 项落地前建议在 Win10 1903+ 做 ConPTY / AF_UNIX / wincred / Job Object 能力探测。

---

## 8. 依赖层平台绑定（v2 新增，v1 完全遗漏）

> 上一轮只看 wuu 自有源码，`go.mod` 里的直接依赖才是 Windows 移植的真正拦路虎。逐条：

| 依赖 | 用途 | 平台实现 | Windows 现状 | Python 对位 |
|---|---|---|---|---|
| **`github.com/zalando/go-keyring`** | OS 凭据保险库抽象（`credentialstore/keyring.go`） | macOS `security` 子进程 / Linux Secret Service over **`godbus/dbus`** / **Windows `danieljoos/wincred`**（WinCred API `CredRead/CredWrite/CredDelete`） | ✅ wincred 后端可用，但 **`NewDesktopStore()` 硬编码 `runtime.GOOS != "darwin"` 直接返回错误**——桌面模式的 keyring 路径**拒绝非 macOS**。移植时需决定：Windows 是走 `NewKeyringStore`（wincred）还是复刻 `NewDesktopStore` 限制 | **`keyring` (PyPI)**——同抽象、后端 `keyring.WindowsBackend` 走 wincred；或用 `pywin32.win32cred` 直调 |
| **`github.com/fsnotify/fsnotify`** | 配置/插件热重载（`appserver/config_watch.go`、`appserver/plugin_generation_watch.go`） | Linux inotify / macOS FSEvents / **Windows `ReadDirectoryChangesW`** | ✅ fsnotify Windows 支持完善，语义略有差异（`Rename` 在 Windows 拆成 move-out/move-in，`Chmod` 事件不派发） | **`watchdog`**（Windows 后端就是 `ReadDirectoryChangesW`） |
| **`github.com/creack/pty`** | Unix PTY（`manager_unix.go`） | 仅 Unix，**Windows 不支持** | ❌ Go 层 Windows 无 PTY；参见 D 类 | `pywinpty`（ConPTY），或复用 desktop `node-pty` |
| **`modernc.org/sqlite`** + **`modernc.org/libc`** | 会话库（`session/history_recovery.go`、`session/session.go`） | **纯 Go**（Go 翻译的 libc） | ✅ 跨平台无阻塞，但**忽略 `mode` 参数**（`session.go:1139` 注释："Directory at 0o700, file at 0o600. modernc.org/sqlite ignores ..."），需 `securefs.PreCreateFile` 先建后开 | **`sqlite3` 标准库**（Windows 内置），权限改走 ACL/DPAPI |
| **`github.com/jackc/pgx/v5`** | Postgres 账户存储（`remote/account/postgres.go`、`remote/pgtest/database.go`） | 网络协议，跨平台 | ✅ | `psycopg[binary]` |
| **`charm.land/catwalk`** | LLM 模型目录（`providers/catwalk_*.go`、`runtime/session.go`） | 纯数据/嵌入资源 | ✅ 平台无关 | 直接移植数据表 |
| **`github.com/coder/websocket`** | app-server 协议（推测） | 跨平台 | ✅ | `websockets` / `aiohttp` |
| **`github.com/mattn/go-isatty`**（indirect） | TTY 检测（可能被 catwalk 等间接使用） | Win32 `GetConsoleMode` | ✅ | `sys.stdout.isatty()`，或 `ctypes.GetConsoleMode` |

> **v1 的错误结论修正**：§E-9 曾写「无 Windows 特权/系统级 API 依赖」——**wincred（凭据写入）就是 Windows 系统级凭据 API**，`node-pty/winpty` 是 Windows 控制台子系统，`ReadDirectoryChangesW` 是 Windows 内核通知 API。这三类**上一轮都没登记**。§E-9 的「无令牌/特权提升 API（`OpenProcessToken`/`AdjustTokenPrivileges`/`CreateRestrictedToken`）」结论仍成立（grep 0 命中且未截断），但应理解为「无高危令牌代码」，不代表 Windows 侧零系统 API 工作量。

---

## 9. Windows 运行时特有坑（v2 新增，散落于无平台后缀文件里的 GOOS 分支）

> 上一轮只扫了 `_windows.go` 后缀文件，但**更多 Windows 差异藏在没后缀的通用文件里**（`runtime.GOOS == "windows"` 分支）。全仓 21 处，逐条：

| 位置 | 差异 | 严重度 |
|---|---|---|
| **`internal/claudeengine/transport.go:285/293`** | `Process.Signal(os.Interrupt)` 后 `Process.Signal(syscall.SIGTERM)` 兜底 Claude 子进程退出。**Go 文档明说：Windows 上 `os.Process.Signal` 只支持 `os.Kill`，SIGTERM/SIGINT 返回 `syscall.EWINDOWS`——错误被 `_ =` 吞掉，"优雅关闭"在 Windows 实际静默失败**。 | 🟠 |
| **`internal/gitattribution/wrapper.go:104`** | `cygpath -u` 转换 Windows 路径为 MSYS 路径，Git Bash 依赖 | 🟠 |
| **`internal/gitattribution/wrapper.go:146`** | Windows 下 Git Bash `command -v git` 返回**无 `.exe` 后缀**的路径，wuu 手工补 `.exe` 后再 `os.Stat` 判定 | 🟠（Python `subprocess` 有相同坑：Windows `shutil.which("git")` 通常给 `git.exe` 但 Git Bash 语境下要给 `git`） |
| **`internal/shellpath/normalize.go:19`** | `NormalizeBashCommand`：Windows 专属正则把 `2>nul`/`>nul` 改写成 `2>/dev/null`——模型输出带 cmd.exe 肌肉记忆，在 Git Bash 里会创建名叫 `nul` 的文件。**Python 若走 Git Bash 需要复刻；若改走 PowerShell/cmd 需要反向映射**。 | 🟠 |
| **`internal/pluginhost/process.go:804`** | Windows 子进程 env 白名单额外 14 项（`SYSTEMROOT`/`SYSTEMDRIVE`/`USERPROFILE`/`APPDATA`/`LOCALAPPDATA`/`ProgramFiles`/`ProgramFiles(x86)`/`ProgramData`/`CommonProgramFiles[(x86)]`/`PROCESSOR_ARCHITECTURE`/`PROCESSOR_IDENTIFIER`/`COMPUTERNAME`/`USERNAME`） | 🟡 |
| **`internal/worktree/open_or_create.go:444`**、**`internal/worktree/worktree.go:692`** | `sameCanonicalPath` / 工作树路径比较：Windows 用 `strings.EqualFold`（大小写不敏感） | 🟡 |
| **`internal/tools/env.go:462`（`relInsideRoot`）** | 沙箱根包含判定：Windows 用 `strings.ToLower` 折叠后比对（保留原大小写返回 rel） | 🟡 |
| **`internal/tools/toolkit.go:1520`（`mergeEnv`）** | 环境变量名 Windows 大小写不敏感（`Path`/`PATH`），归一到大写避免重复键 | 🟡 |
| **`internal/runtime/plugin_artifact_service.go:360`** | `file://` URI → 路径时，Windows 需剥掉 URI 形式的**前导 `/`**（`/C:/foo` → `C:/foo`）。这是 RFC 8089 + Windows 盘符的经典冲突 | 🟡 |
| **`internal/process/manager.go:579`** | 工作空间根 EvalSymlinks 后大小写折叠（同 worktree/env.go 系列） | 🟡 |
| **`internal/credentialstore/keyring.go:54`（`NewDesktopStore`）** | `runtime.GOOS != "darwin"` → 返回错误 "desktop credential store requires macOS Keychain"。**桌面凭据路径 macOS-only，Windows 需要显式决定用什么**（wincred / DPAPI / 允许 NewKeyringStore 走） | 🔴 |
| **`internal/providers/anthropic/quota.go:150`** | Claude Code OAuth 配额读取：`runtime.GOOS != "darwin"` 或 `CLAUDE_CONFIG_DIR` 非空即拒绝，再走 `security find-generic-password -s "Claude Code-credentials" -w`。**Windows 无 macOS Keychain → 配额降级为 `QuotaErrorSignIn`**（功能缺失，非崩溃） | 🟡 |
| **`cmd/wuu/login.go:111`（`openBrowser`）** | OAuth 浏览器拉起 darwin→`open`/windows→`rundll32 url.dll,FileProtocolHandler <url>`/default→`xdg-open`。**已实现 Windows 分支** | ⚪ |
| **`internal/enginecatalog/catalog.go:26`** | Antigravity 引擎 args：`runtime.GOOS == "linux"` 才加 `--uid=`；Windows/Mac 不加 | 🟢 |
| **`internal/enginecatalog/lookup.go`**（160/212/236/289/311 五处） | 引擎目录解析的多处 `runtime.GOOS == "windows"` 分支（具体语义未逐行读，但存在 Windows 专门逻辑） | 🟡 |
| **`internal/executionenv/environment.go:270`** | Docker `--user uid:gid` 仅当 `GOOS==linux` 时按 `os.Getuid()` 拼接；Windows/macOS 不加 uid → **容器内 root 运行** | 🟠（见 §10） |

---

## 10. 双层沙箱与双终端架构（v2 新增：修正 v1 的窄化视角）

### 10.1 wuu 实际有 **两条独立的隔离路径**

上一轮只讲了 `processsandbox`（Seatbelt/Landlock）。全仓 grep 后：**另一条是 Docker 容器执行**，`internal/executionenv/environment.go` 用 `exec.CommandContext(ctx, "docker", "run", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--pids-limit=512", "--mount type=bind,...", ...)` 起完整 Linux 容器工作空间。

| 隔离层 | 位置 | 适用 | Windows 现状 |
|---|---|---|---|
| **A. 进程级 fs 沙箱**（Landlock / Seatbelt） | `processsandbox/sandbox_{darwin,linux,other}.go` | 直接跑 shell 工具子进程（bash、hooks、MCP server 等） | ❌ `sandbox_other.go` `platformSupported()=false` |
| **B. Docker 容器** | `executionenv/environment.go`、`executionworker/`（unix socket） | 独立 execution profile 的 workspace 隔离 | ⚠️ Windows 需 **Docker Desktop**（WSL2/HyperKit VM）；Linux 容器跑在 VM 里；bind mount 走 Hyper-V FUSE/Plan9（长路径/软链/权限位跨 VM 边界语义丢失） |

**结论修正**：v1 推荐 "AppContainer 补 processsandbox 空缺"——**若目标 Windows 用户接受 Docker Desktop，B 路径反而是更完整的现成解**（含 net/uid/proc 隔离，不止文件写）。AppContainer 适合"无 Docker、想原生轻量"的场景。两条路线要在移植设计里显式二选一或分层。

- Docker on Windows 具体坑：`--user uid:gid` 被跳过（GOOS=linux 分支），Windows 下容器以 root 起；bind mount 传 Windows ACL 到 Linux 侧几乎不可控（Docker 会呈现 0777 或 root-owned）；`HOME=/tmp/wuu-home` 是容器内 Linux 路径不影响宿主；`--network=none` 依赖 Windows Docker Desktop CNI 行为。

### 10.2 wuu 实际有 **两套 PTY**

| PTY 层 | 位置 | 平台 | 说明 |
|---|---|---|---|
| **A. Go 后端 PTY** | `internal/process/manager_unix.go` 用 `creack/pty` | 仅 Unix（Win `ptySupported()=false`） | 供 codex/claude/grok 等 tty-mode 引擎使用 |
| **B. Desktop 前端 PTY** | `desktop/node_modules/node-pty/deps/winpty/**` | **跨平台**（Win 走 winpty，Unix 走 posix_openpt） | Electron 内嵌终端用 |

**结论修正**：v1 说"Windows PTY 缺失"——**这只对 Go 后端成立**。桌面壳自带 node-pty 已能起 ConPTY/winpty，如果 Python 后端不做 tty、把 tty 交给 Electron 层，Windows 也能有终端。纯 CLI/Linux 场景则必须自接 `pywinpty`。设计前需明确"谁是 PTY 属主"。

---

## 11. 修订后的移植优先级（v2）

按新增事实重排：

1. 🔴 **A. 进程级 fs 沙箱空缺**（E-1） → 二选一：AppContainer（原生、轻量、仅文件写）或依赖 Docker Desktop（B 路径，含完整 Linux 隔离）。
2. 🔴 **credentialstore 桌面 macOS-only 硬约束**（§9 `keyring.go:54`）——**功能可用性阻塞**：桌面凭据在 Windows 直接被拒，Python 侧要么放开让 wincred 上，要么改用 DPAPI/Windows 凭据管理器。**这条是 v1 完全没发现的**。
3. 🔴 **执行 worker Unix socket + Setsid + ExtraFiles**（E-5）——Windows 需完全重写（named pipe / loopback TCP + 事件）。
4. 🔴 **securefs 权限位假安全**（E-7）——Windows ACL + DPAPI 替换 `0o600/0o600`，`TightenRecursive` 迁移到 ACL 收紧。
5. 🟠 **PTY**（E-3）——若走 CLI/无 Electron 场景：`pywinpty`；若桌面壳已带 node-pty，后端可让位。
6. 🟠 **claudeengine/transport SIGTERM 静默失败**（§9 第 1 行）——Python `subprocess` Windows 上 `terminate()`=TerminateProcess，`send_signal(SIGINT)` 要 CREATE_NEW_PROCESS_GROUP + CTRL_C_EVENT；建议统一 Job Object 兜底。
7. 🟠 **shell 命令归一（`NormalizeBashCommand` + `cygpath` + `.exe` 补全 + Git Bash 依赖）**（§9 第 2/3/4 行）——**架构 fork 决策点**：Python 是沿用 Git Bash（需复刻全部修补），还是换 PowerShell/cmd（需重写 shellpath 与 git wrapper）。
8. 🟠 **进程树终止**（E-2）——`kill(-pgid)` 无 Windows 等价，Job Object 或 `taskkill /T`。
9. 🟡 **fsnotify / keyring / 环境变量白名单 / 大小写折叠路径比较 / `file://` 前导斜杠剥离**（§8 + §9）——Python 有对应库和模式，按点替换。
10. 🟢 **信号 / openBrowser / catalog 参数**（`cmd/wuu/login.go`、`enginecatalog/catalog.go`）——已有 Windows 分支，直接映射。

---

## 12. 反思：v1 扫描的失败模式与本次修正

**v1 为什么会漏**（诚实复盘，供后续同类任务规避）：
1. **对 grep "Results limited to 25 matches" 提示视而不见**——直接用截断结果下"全量"结论；应用分片/子目录多次搜索交叉验证。
2. **只看 `*_windows.go` 等文件名后缀**——但 `runtime.GOOS == "windows"` 分支大量藏在无后缀的通用文件里（本次 §9 列出 21 处，v1 只看了 5 处）。
3. **完全没读 `go.mod`**——依赖层的平台绑定（wincred/fsnotify/creack-pty/modernc-sqlite/node-pty）是移植的主要成本项，v1 漏了整整一层。
4. **只精读约 10 个 internal 包，未先做"哪 21 处含 GOOS"的全景枚举**——`executionenv`（Docker）、`credentialstore`（keyring）、`appserver`（fsnotify）、`claudeengine`（SIGTERM）、`gitattribution`（cygpath+.exe）、`pluginhost`（env 白名单）都在 v1 视野外。
5. **`desktop/` 目录未展开**——直接以"非 Go 逻辑翻译范围"打发；但 `desktop/native/cua-mac`（macOS Swift CUA）和 `desktop/node_modules/node-pty+winpty`（Windows PTY 已有实现）都是**系统级平台依赖**，属于用户问题的范围。
6. **`grep '^//go:build'` 遇 25 限就放弃了 git grep / rg 兜底**——三种工具都试过但没做第四种（PowerShell `Get-ChildItem | Select-String`），本可彻底完成。

**v2 已补齐**：§8 依赖层、§9 通用文件里的 GOOS 分支、§10 双沙箱+双终端架构、§11 修订优先级、§7 完整覆盖清单。
