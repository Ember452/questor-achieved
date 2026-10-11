# behavior-state-wuu —— wuu 路径/原子写/文件锁行为规格（Questor `state` 蓝本）

来源：wuu `internal/statepath/statepath.go`（261 行）+ `internal/securefs/securefs.go`
（306 行）+ `internal/storelock/store_lock.go`（86 行，含 `store_lock_unix.go` /
`store_lock_windows.go`）。扫描日期 2026-10-11，行号当日核实。Questor 模块归属：`state`。

---

## 1. home 定位与 env 覆盖（`statepath.go#Home`）

- **输入**：`homeDir`（用户主目录）。
- **输出**：`<home>/.wuu` 的绝对路径；env `WUU_HOME` 非空（TrimSpace 后）时整体重定向为该值
  的绝对路径（`statepath.go#L34-51`）。
- **边界行为**：env 在**每次调用时**读取，非 import/init 时求值（B-73）；home 为空串且
  `os.UserHomeDir()` 失败 → 显式 error，不猜默认值。
- **坑**：B-73。

### Questor 采纳决定
沿用：`questor_home()` 每次调用读 `QUESTOR_HOME`（TrimSpace、非空即整体重定向、转绝对路径），
缺省 `~/.questor`。env 读取禁止发生在模块 import 时。

## 2. 工作区目录命名（`statepath.go#WorkspaceDir/#WorkspaceDirByID/#sanitizeSlug`）

- **输入**：wuuHome + rootDir（by-path）或 workspaceID（by-ID）。
- **输出**：`<slug>-<sha256[:16]>` 形态的目录名（by-path，`statepath.go#L158-176`）；
  by-ID 直接对 opaque ID 哈希不解析（`#L137`）。
- **边界行为**：by-path 先 `filepath.Abs` 再 `EvalSymlinks`（失败则用 abs），保证符号链接与
  真实路径映射同一目录（`#L169-171`）；`sanitizeSlug`（`#L238-261`）仅保留
  `[a-zA-Z0-9._-]`、其余折叠为单个 `-`、`Trim(".-")`、上限 48 字符（截断后再 trim）——
  天然杜绝路径分隔符进目录名；slug 为空回落 `"workspace"`。

### Questor 采纳决定
沿用：`workspaces` 注册用 slug-hash16 目录名；Python 侧用 `os.path.realpath` +
`hashlib.sha256`。hash 键保证"不可预测用户内容即目录名"。

## 3. 原子写（`securefs.go#WriteFileAtomic`，L41-84）

- **输入**：目标路径 + 全量字节。
- **输出**：目标文件被整体替换，内容为 data，mode 0600（`FileMode`，`#L30`）。
- **边界行为**：① 父目录先 `MkdirAll` 0700（`DirMode`，`#L35`）；② 临时文件用
  `os.CreateTemp(dir, ...)` 与目标**同目录**（`#L46`，B-72——跨目录 rename 不原子）；
  ③ rename 前完成 `Chmod(0600)` + `Sync()`（fsync）（`#L61-65`）；④ 任一步失败经 defer
  清理残留临时文件（`#L52-56`），目标文件永不半写；⑤ rename 后复核 mode，FUSE/overlay
  保留旧 mode 时补一次 chmod（`#L78-82`）；⑥ Windows：rename 走 `MoveFileEx(REPLACE_EXISTING)`
  可原子替换已存在目标，mode 位尽力而为、代码不得假设 chmod 可靠（测试在 Windows 跳过
  mode 断言，`securefs_test.go#L13-15`）。
- **坑**：B-72。

### Questor 采纳决定
沿用全部六条边界行为；`write_atomic()` 用 `tempfile.NamedTemporaryFile(dir=parent)` +
`os.replace`。普通索引类写入可免 fsync（wuu 的 threads.json 就免），凭据与关键状态走全套。

## 4. 跨进程文件锁（`store_lock.go` 全文）

- **输入**：store 目录。
- **输出**：独占锁句柄；`Release()` 幂等（nil receiver 与重复释放均安全，`#L74-86`）。
- **边界行为**：① 锁文件 `<dir>/.store.lock` 经 `O_CREATE|O_RDWR` 0600 打开，**释放后留在
  原地不删除**（`#L33-35` 注释：让所有竞争者始终锁同一 inode——删除-重建会让两个进程锁不同
  inode，B-71）；② 非阻塞 try-lock 循环 + 25ms 睡眠（`acquireRetryDelay`，`#L28`），硬超时
  1 分钟（`acquireTimeout`，`#L27`）报 "held by another owner for over 1m"，**不死等**；
  ③ 无心跳、无陈旧锁破坏——锁由内核持有，进程死即自动释放，加"陈旧锁清理"反而引入竞态；
  ④ Windows 用 `LockFileEx(LOCKFILE_EXCLUSIVE_LOCK|LOCKFILE_FAIL_IMMEDIATELY)`，ERROR_LOCK_VIOLATION
  视为"被他人持有"（`store_lock_windows.go#L12-22`）；POSIX 用 `flock(LOCK_EX|LOCK_NB)`，
  EINTR 重试（`store_lock_unix.go#L11-22`）；⑤ 调用方契约：进程内 mutex 先于跨进程锁；
  **纯读者两者都不拿**（读侧靠原子 rename 的索引 + 容忍残尾的 append 流，见 behavior-gesta-wuu）。
- **坑**：B-71。

### Questor 采纳决定
沿用：`state.locks.StoreLock` 上下文管理器，Windows 走 `msvcrt.locking(LK_NBLCK)`、POSIX 走
`fcntl.flock`，锁文件永不删除，25ms 重试 / 60s 超时（常量与 wuu 同量级）。

---

## 本区域坑条目（同步进 pitfalls.md）

| 编号 | 归属 | 一句话 | 证据 |
| --- | --- | --- | --- |
| B-71 | state | 锁文件释放后禁止删除——删除-重建会让并发进程锁到不同 inode，互斥失效 | wuu `internal/storelock/store_lock.go#L33-35` |
| B-72 | state | 原子写的临时文件必须与目标同目录——跨目录 rename 不原子，崩溃可留半写 | wuu `internal/securefs/securefs.go#L44-56` |
| B-73 | state | 路径解析的 env 覆盖必须每次调用时求值——import/init 时求值会让测试与多实例拿到陈旧 home | wuu `internal/statepath/statepath.go#L34-37` |
