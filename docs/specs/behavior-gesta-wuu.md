# behavior-gesta-wuu —— wuu append-only 事件存储行为规格（Questor `gesta` 蓝本）

来源：wuu `internal/agentthread/store.go`（542 行）。扫描日期 2026-10-11，行号当日核实。
Questor 模块归属：`gesta`。契约约束另见 `docs/architecture/data-model.md` §2 §5（唯一真相源）。

---

## 1. 事件日志追加（`agentthread/store.go#appendEventLocked`，L528-542）

- **输入**：Event 记录（CreatedAt 为零值时补 UTC 当前时间）。
- **输出**：一行 JSON 经 `json.Encoder.Encode`（自带换行）追加到 `events.jsonl`。
- **边界行为**：打开方式固定 `O_CREATE|O_WRONLY|O_APPEND`（0600），**从不以截断模式打开**；
  追加发生在锁内；每行整行落地，读侧靠"残尾跳过"容忍崩溃半行。

### Questor 采纳决定
沿用：gesta 对会话正文只允许 append 打开（架构测试 AST 禁 truncating 写模式）；
Questor 每线程一个 `<thread_id>.jsonl`（data-model §5），seq 由追加方在锁内分配。

## 2. 事件读取与残尾容忍（`agentthread/store.go#loadEvents`，L379-406）

- **输入**：events.jsonl 路径。
- **输出**：事件列表；文件不存在返回空（不报错）。
- **边界行为**：逐行 `bufio.Scanner`，空行跳过；**JSON 解析失败的行直接 continue**——
  崩溃产生的半行残尾被静默跳过（`#L375-378` 注释："appends land whole lines and the
  scanner skips an incomplete tail"）；读侧**不拿锁**（纯读者，见 §4）。
- **坑**：B-74。

### Questor 采纳决定
沿用：`load_thread()` 逐行解析、空行与坏行跳过；残尾容忍是**回放可用**的前提（崩溃后
不修复也能读），且跳过不影响后续追加（下一次 append 仍 O_APPEND 到文件末尾）。

## 3. 索引原子替换（`agentthread/store.go#writeThreadsLocked`，L496-526）

- **输入**：索引全量内容（threads.json）。
- **输出**：索引文件被整体替换。
- **边界行为**：`MarshalIndent` + 尾部 `\n`；`os.CreateTemp(同目录)` 写入后 `os.Rename`
  替换；失败路径显式删除临时文件；**不做 fsync**（wuu 对索引走的是轻量路径——凭据与关键
  状态才走 securefs 全套，见 behavior-state-wuu §3）。

### Questor 采纳决定
沿用：`threads.json` 摘要索引（线程元数据，不含正文）走 temp+rename 轻量路径；
索引可从 JSONL 全量重建（data-model §5 "可重建"；SQLite FTS 搜索索引按 B-46 属 M4，
Questor M2.1 以 JSON 索引承载，偏离已在 development-plan M2.1 实际结果留痕）。

## 4. 锁契约与读侧免锁（`agentthread/store.go#L355-373`）

- **输入**：读-改-写（RMW）方法调用。
- **输出**：RMW 全程持双锁（进程内 mu → storelock.Acquire）；纯读方法两锁都不拿。
- **边界行为**：状态是事件流的 fold（`resultDeliveryState`，`#L408-427`）——**绝不修改
  旧行**，判定 = 重放；"写者在等跨进程锁的全程持有进程内 mu"被明确作为不让学生读等锁的
  理由（`#L359-361` 注释）；幂等靠"先扫日志按 resultID 查重再追加"（`#L190-199`）。

### Questor 采纳决定
沿用：gesta RMW（建线程、状态迁移、追加）全程持 `state.locks` 的 store 锁；读与回放免锁；
状态迁移经 `transitions.py` 白名单函数产生**新记录**追加，不改写历史（data-model §3.1
"旁路写入视为契约破坏"）。

---

## 本区域坑条目（同步进 pitfalls.md）

| 编号 | 归属 | 一句话 | 证据 |
| --- | --- | --- | --- |
| B-74 | gesta | 会话 JSONL 读取必须容忍残尾（空行与坏行跳过）——崩溃半行不得阻断回放与后续追加 | wuu `internal/agentthread/store.go#L375-406` |
| B-75 | config | 共享配置层的用户专属字段 strip 必须大小写不敏感全拼写删除——raw map 合并时大小写变体绑定同一字段 | wuu `internal/config/settings_layer.go#L279-294` |
