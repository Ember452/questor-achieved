# limen —— 模块设计篇（Phase 2a 批次 2a：门链与收紧型审批）

状态: 门链已落地（2026-10-14）；旧入口 `gate.decide()` 仍服务未重写的工具层，**批次 3a 硬到期删除**
provenance: `# Ported from wuu@2026.10.6 internal/tools/{boundary.go,toolkit.go,review.go,authorization.go,tool_info.go} + internal/approvefor/review.go`
行为规格: `docs/specs/behavior-limen-wuu.md`；契约: `protocol.md` §7 错误方言、`overview.md` §5

> 旧版本篇按 FlowCoder 的"六层权限"写；母本对齐后 FlowCoder 退出参照系（ADR-0038），
> 那部分旧结论以 git 历史留存，不再作为本篇依据。

## 职责与边界

系统里**唯一**能回答"这次动作允许吗"的地方。三柱里它同时是**可干预**（档位与审批是人插手
的落点）与**可验证**（每次拒绝都带可读理由并进会话记录）的边界。

它**不**：解析路径（那是 `tools` 的 `ResolvePath`，母本同构——门只跑只读闸与 Guard 链）、
执行工具（`tools.executor`）、持久化（`gesta`）、决定"接下来做什么"（`engine`）。
依赖方向按 structure §3：只 import 标准库与 `schemas`；可达根与凭据文件名以纯数据注入。

## 两层结构，一条链

| 层 | 文件 | 只回答这件事 |
| --- | --- | --- |
| 硬判定 | `boundary.py` | "允许吗"——`{enforce, allow_mutations, guards}` 三元组 + `mutates(kind, read_only)` 表 + `BoundaryDenied`（带 `reason`/`model_next_action`）。**没有 ask，绝不阻塞等输入**（B-51） |
| 链 | `chain.py` | 按母本定序把 hook → boundary →（特例位）→ Reviewer → Authorizer 串起来 |
| 审批 | `approval.py` | Approve for me 的**收紧型**语义：硬拒三件、送审判定、五态结果 |
| 授权 | `authorizer.py` | 最后防线：可选策略提供方，只能再限制，报错即拒，只认字面 `"allow"` |
| 档位表 | `matrix.py` | 三档 → 边界三元组的显式表（B-33）；**没有"关守卫"这一列**，档位解除不了守卫（B-54）正是靠"表里无此开关"保证 |

定序是**安全属性而不是风格**（B-130）：Authorizer 排在 Reviewer 之前、或 boundary 被挪到
hook 之后，都能让逐条结果测试全绿而实际语义失效。护栏用调用记录仪断言序列，而非只断言结果。

## 关键语义（逐条有测试）

- **只收紧不提权**：审批与 Authorizer 都不能把 boundary 的拒绝翻成允许；参数里带
  `permission_mode`/`permission-mode` = `unconfined` 一律硬拒（B-55）。
- **默认分支是拒**：审批结果五态 `allow/deny/unsure/failed/cancelled`，其中
  `failed`/`cancelled`/未知值一律按母本 default 分支落 `review_failed`；
  "非 deny 即允许"这种写法等于把坏掉的审批通道变成放行（B-56、B-131）。
- **shell 无条件送审**：分类为只读不能证明 `cat` 读不到凭据；且同时看原生工具名，
  缺 Kind 元数据不该成为绕过审批的后门。
- **硬拒看目标不看内容**：命令文本里出现 `auth.json` 不等于访问了它（仍走上下文审批，
  但不是硬拒）。
- **敏感判定单点**：复用 `sensitive.classify` 一张宽表。母本在 `tools` 与 `approvefor`
  各写一份（后者更窄），本仓不复制第二套真相，代价是硬拒比母本更严（port-ledger L-6）。
- **`ToolKind` 与门判定表必须同步**：新增工具类只扩 `schemas/model.ToolKind`，
  并且必须在 `MUTATING_KINDS`/`NON_MUTATING_KINDS` 之一出现，否则
  `test_every_tool_kind_is_classified_by_the_gate` 判红（B-133）。

## 待办与到期点（登记在 port-ledger，不留暗债）

- L-8：`gate.decide()` + `matrix` 与新链并存，**批次 3a 删**（同一语义两处实现）。
- L-2：`PermissionContext.checked` 的打标时机是"判定完成后"，母本 `markPermissionChecked`
  的确切调用点本轮未读到，批次 4 接入嵌套工具调用时复核。
- L-7：`ToolKind` 里临时保留的 `meta` 随批次 3a 收敛删除；`Exposure`/`ConcurrencySafe`
  随批次 3a 的工具注册表落地。

## 旧篇仍有效的已验证要点（不随重写丢失）

- **源码扩展豁免只给纯代码后缀**（`.py`/`.go`/…）；文档扩展（`.md`/`.txt`）**不豁免**——
  凭据目录里的文档按敏感处理，误伤文档的代价远小于放行凭据；`.env.example` 模板与
  `.pub` 公钥显式豁免（用例钉住）。
- **危险命令正则的尾部边界用 `(?=\s|$)` 而非 `\b`**——实测 `/` 后无单词边界，`\b` 会让
  行尾的 `rm -rf /` 逃过检测（对抗测试抓到后修正）。该黑名单仍是 Guard 链的一环（B-32），
  由工具层以 Guard 注入；它不是 wuu 的东西，属本仓保留的附加防护（登记于 L-6/L-8 同批）。
- **缺路径参数 = deny 且先于路径门**（B-31）：unconfined 不查路径门，但缺参是调用形状错误，
  不是"无边界可查"。
- **唯一消费入口护栏**：`test_permission_gate_single_entry`——只有 `tools/executor.py` 可
  import `limen.gate`；limen 包内 re-export 合法；并断言消费者存在（防护栏空转）。

## 对应测试

`tests/unit/test_limen_chain.py`（门链定序、幂等护盾、Authorizer fail-closed、审批五态、
硬拒三件、`mutates` 两张表、错误方言、unconfined 仍跑守卫链）；
`tests/architecture/test_permission_gate_single_entry.py`（唯一消费入口）、
`test_tool_kind_single_source.py`（单点定义 + 判定表覆盖）；
既有 `test_limen_matrix/guards/reachability.py` 覆盖旧入口，随批次 3a 一并迁移。
