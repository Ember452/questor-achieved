# behavior-limen-wuu —— wuu 权限门行为规格（Questor `limen` 权威蓝本）

来源：wuu `internal/tools/boundary.go` + `internal/tools/sensitive_paths.go` +
`internal/config/settings_layer.go` + `internal/approvefor/review.go` +
`internal/processsandbox/`。扫描日期 2026-10-11。Questor 模块归属：`limen`。

---

## 1. WorkspaceBoundary：唯一权威门（`internal/tools/boundary.go`）

- **结构**：`{Enforce bool, AllowMutations bool, Guards []Guard}`（`boundary.go#L15-19`）。
  三构造器：`StandardBoundary{true,true}`（默认，可达根内全权无审批）、
  `ReadOnlyBoundary{true,false}`（拒一切变更但仍约束读）、
  `UnconfinedBoundary{false,true}`（解除路径约束的逃生舱，`#L21-36`）。
- **判定**：`Check` = 只读闸（`!AllowMutations && mutates(info)` → 拒，`#L47-53`）+
  Guard 链逐个硬判（`#L54-61`）。**Guard 契约**：不得阻塞等用户输入、不得返回
  审批/ask 结果（`#L38-39` 注释）——硬 allow/deny 与审批链严格分层。
- **错误方言**：`boundaryError` 携带 `Reason` + `ModelNextAction`
  （"this agent is read-only; it may observe but not modify" /
  "use read-only tools, or tell the user this agent cannot make changes"，`#L48-52`、
  `#L90` 的格式串 `error_kind=boundary_denied reason=%q model_next_action=%q`）。
- **mutates 粒度**（`#L65-80`）：按 ToolKind 判——file/shell/test/git/agent/process/
  schedule/mcp/browser/plugin 全算 mutation；**browser 的 read-only 由 info.ReadOnly
  短路**：read-only 会话必须拦 navigate/click/type 但放行 observe/screenshot
  （`#L73-75` 注释明言）。
- **坑**：B-51（read_only 的浏览器类粒度：拦变更类、放观察类）、B-52（Guard 不得阻塞
  不得 ask——守卫与审批严格分层）、B-53（错误必须带 model_next_action 指导模型下一步）。

### Questor 采纳决定
limen 单门结构沿用 `{Enforce, AllowMutations, Guards}`；三档构造器一一对应；
`mutates` 的 ToolKind 分类表直译；错误方言 = `error_kind + reason + model_next_action`
（protocol.md 错误节）。

## 2. 敏感路径守卫（`internal/tools/sensitive_paths.go`）

- **规则**（`#L34-64` `sensitivePathReason`）：按路径段匹配——`.netrc`（"credentials"）、
  credential 配置、`credential|secret` 段（**源码扩展名豁免**：`credentials.go` 是认证
  源码不是凭据库，`#L13-14` 注释）、`id_rsa`/`id_ed25519`/`id_ecdsa` 私钥。
- **三档关系**（wuu 语义，Questor overview §9 已定）：写操作在**包括 unconfined 在内
  的一切模式**拒绝；unconfined 的读降级为输出脱敏而非拒绝；RedactToolOutput 恒开。
- **边界行为**：源码扩展名豁免要防符号链接别名绕过（basename 判定按段处理而非整串子串）。
- **坑**：B-54（源码扩展名豁免 + 按段匹配——naive 子串匹配会误伤 `credentials.go`）、
  B-55（unconfined 写仍拒、读降级脱敏——档位不解除守卫）。

### Questor 采纳决定
全收；"凭据文件连 wuu 自己都摸不到的地板"语义（自身配置也是敏感路径）一并收。

## 3. Approve for me：只收紧不提权（`internal/approvefor/review.go`）

- **`NeedsReview`**（`review.go#L60-87`）：standard 模式才生效（测试
  `TestNeedsReviewStaysOffOutsideStandard`，`review_test.go#L21-26`）；shell/bash 一律
  送审（"只读分类不能证明 cat 不会读凭据"，`#L137` 注释）；普通工作区读跳过
  （`review_test.go#L10-16`）。
- **`HardDenyReason`**（`review.go#L87-112`）：无审批者（含用户）可覆盖的硬拒——凭据类
  调用、**参数里试图 `permission_mode=unconfined`**（`#L112` 遍历
  `"permission_mode"/"permission-mode"` 键）、敏感路径写。判定用**目标不是内容**
  （`TestHardDenyUsesTargetsNotContent`，`review_test.go#L31`）。
- **结果五态**：allow/deny/`unsure`/failed/cancelled（`#L15` OutcomeUnsure）——failed/
  cancelled 明确声明"不是安全判定"。
- **坑**：B-56（审批不可提权：参数带 permission_mode 一律硬拒）、B-57（unsure/failed
  不得被模型当总括授权）。

### Questor 采纳决定
全收进 `habena`（收紧型审批接口）；硬拒三件进 limen Guard。

## 4. 设置分层：仓库配置不能提权（`internal/config/settings_layer.go`）

- **机制**：分层合并时 strip 用户专属字段——provider 连接图、内联凭据、扩展授权、
  **permission_mode**（`settings_layer.go#L23,L48-52,L62-63,L108` 注释："preserving the
  user-only security boundary"）；共享层 strip 内联 api_key（env 间接引用保留），本地
  settings 不 strip（本地即用户）。
- **边界行为**：项目层深合并只覆盖非安全字段——防"打开一个仓库就决定凭据发往哪里"。
- **坑**：B-58（项目配置 strip 用户专属安全字段；permission_mode 不可由仓库配置设定）。

### Questor 采纳决定
`config` 模块分层合并沿用 strip 清单；护栏测试"仓库配置不能提权"进 M2。

## 5. 进程沙箱策略（`internal/processsandbox/`）

- **Policy**：`{Mode: read_only|workspace-write, WritableRoots}`，从 boundary 推导
  （read_only→ReadOnly；可写根 = FileScopeRoots 剔除系统 tmp）。
- **fail closed**：`platformSupported()` 返回 false 的平台（Windows，`sandbox_other.go#L11-14`）
  直接 `ErrUnavailable`——受限模式命令执行失败并提示配置 provider 或显式 unconfined，
  **绝不静默降级裸跑**。
- **坑**：B-59（沙箱 provider 契约：必须 full enforcement，partial 被拒绝）。

### Questor 采纳决定
ADR-0007 已裁定 Windows 语义（路径门 + Job Object + 显式标注）；本条补充：Questor 的
run 工具在 standard 档必须声明"当前执行是否被 OS 沙箱覆盖"，未覆盖即按 ADR-0007 的
标注与确认流程走。

---

## 本区域坑条目（同步进 pitfalls.md）

| 编号 | 归属 | 一句话 | 证据 |
| --- | --- | --- | --- |
| B-51 | limen | read_only 的浏览器粒度：拦 navigate/click/type、放 observe/screenshot（ReadOnly 短路在 mutates 之前） | `internal/tools/boundary.go#L65-80` |
| B-52 | limen | Guard 不得阻塞等用户输入、不得返回 ask——硬判与审批严格分层 | `internal/tools/boundary.go#L38-42` |
| B-53 | limen | 拒绝错误必须带 model_next_action，指导模型下一步而非只说不行 | `internal/tools/boundary.go#L48-52,L90` |
| B-54 | limen | 敏感路径按段匹配 + 源码扩展名豁免（credentials.go 是源码），防子串误伤与 symlink 绕过 | `internal/tools/sensitive_paths.go#L13-14,L34-64` |
| B-55 | limen | 敏感写包括 unconfined 一律拒；unconfined 读降级输出脱敏——档位不解除守卫 | `internal/tools/sensitive_paths.go`（wuu 语义） |
| B-56 | habena | 审批硬拒三件：凭据调用、参数试图 permission_mode 提权、敏感路径写；判定用目标非内容 | `internal/approvefor/review.go#L87-112` |
| B-57 | habena | 审批五态 allow/deny/unsure/failed/cancelled；unsure/failed 不是安全判定，不得当总括授权 | `internal/approvefor/review.go#L15` |
| B-58 | config | 仓库/共享配置分层合并时 strip 用户专属安全字段（provider/凭据/permission_mode） | `internal/config/settings_layer.go#L23,L48-63,L108` |
| B-59 | limen | 沙箱 provider 契约：必须 full enforcement，partial 拒绝；不支持平台 fail closed | `internal/processsandbox/sandbox_other.go#L11-14` |
