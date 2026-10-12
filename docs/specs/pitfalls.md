# 坑目录（pitfalls）

参照项目已踩过、Questor 重写时必须防住的坑。规则见本目录 `README.md` §二：
编号 `B-NN` 连续递增不复用；每条必须有归属模块与已验证证据；对应测试列 M1 允许
"待落"，模块开工时必须回填；**禁止为凑数收录无证据条目**。

| 编号 | 归属模块 | 一句话 | 来源 | 证据 | 对应测试 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| B-01 | engine | fire-and-forget 任务必须持强引用并观察异常，否则被 GC 中途回收且异常静默 | 异常分支 | FlowCoder `agent/core.py#L703-721` | 待落 |  open |
| B-02 | engine | 预算收敛轮撤光全部工具 schema 后，模型仍幻觉调用会零产出强杀——收敛轮应保留只读工具 | 异常分支 | FlowCoder `agent/core.py#L553-561` | `tests/unit/test_engine_loop.py::test_budget_converge_keeps_readonly_tools`、`::test_converging_round_still_requesting_tools_fails` |  open |
| B-03 | engine | 并行批不得清零 unknown 工具计数，防"每轮夹一个幻觉调用"逃逸 ≥3 熔断 | 异常分支 | FlowCoder `agent/core.py#L619-623` | `tests/unit/test_engine_loop.py::test_unknown_tool_breaker_fails_run`（并行批不清零由 `test_tools_executor.py::test_partition_consecutive_safe_merge` 与 executor 的 parallel 标记承载） |  open |
| B-04 | habena | 审批/提问 future 必须带超时（FlowCoder 300s），防前端失联挂死循环 | 异常分支 | FlowCoder `agent/core.py#L813-818` | 待落（habena M3） |  open |
| B-05 | engine | 循环阈值常量必须集中一张表（FlowCoder 散布 50/3/300s/5 于各处） | remediation 决策 | FlowCoder `agent/core.py#L137,L316,L813,L124` | `tests/unit/test_engine_shape.py::test_thresholds_live_in_constants_table` |  open |
| B-06 | engine | 循环必须拆显式状态机，不允许 1076 行单文件巨型函数 | remediation 决策 | FlowCoder `agent/core.py`（全文） | `tests/unit/test_engine_shape.py::test_no_giant_functions_in_loop` |  open |
| B-07 | engine | 子代理路径必须复用交互路径的同一状态机——FlowCoder 双实现已漂移（子代理无预算闸/无熔断/无输出恢复） | 异常分支对比 | FlowCoder `agent/core.py#L289 vs L911` | 待落（M2.2 无子代理，单一状态机即满足；子代理物化时回填） |  open |
| B-08 | engine | max_tokens 触顶恢复的状态每 run 重置，恢复轮次需有上限 | 异常分支 | FlowCoder `agent/output_recovery.py`、`core.py#L317,L502-513` | `tests/unit/test_engine_loop.py::test_output_recovery_escalates_once_then_retries`、`::test_output_recovery_gives_up_after_budget` |  open |
| B-09 | engine | 记忆观察/提取走后台任务不阻塞主循环；重提取按轮次间隔节流 | 异常分支 | FlowCoder `agent/core.py#L124-125,L523-530` | 待落（memory 模块 M4+） |  open |
| B-10 | limen | 权限门不得内嵌模式特例（FlowCoder 把 plan 文件路径塞进 checker 字段）——模式提醒是循环层职责 | 异常分支 | FlowCoder `agent/core.py#L437-447` | `tests/unit/test_limen_matrix.py::test_boundary_table_matches_overview_s9`（边界表无 Plan 特例档） |  open |
| B-11 | engine | 压缩成功后必须重注入环境/指令/记忆，否则压缩丢工作集 | 异常分支 | FlowCoder `agent/core.py#L389-397` | 待落（context M2.3） |  open |
| B-12 | tools | 退出码语义映射按管道最后一段判定，须覆盖 VAR= 前缀与 basename 提取 | 异常分支 | FlowCoder `tools/bash.py#L47-91` | `tests/adversarial/test_tools_run_process.py::test_grep_pipe_last_segment_exit1_is_no_match`、`::test_var_prefix_and_basename_extraction`、`::test_regular_command_nonzero_is_error` |  open |
| B-13 | tools | 命令超时必须 kill+wait 回收子进程，防僵尸进程残留 | 异常分支 | FlowCoder `tools/bash.py#L154-165` | `tests/adversarial/test_tools_run_process.py::test_job_object_kills_whole_tree`、`::test_run_timeout_moves_to_background` |  open |
| B-14 | tools | 工具输出解码必须 errors="replace"，防二进制输出炸 decode | 异常分支 | FlowCoder `tools/bash.py#L170` | `tests/adversarial/test_tools_run_process.py::test_format_output_decodes_invalid_utf8` |  open |
| B-15 | tools | 并行批 gather 必须 return_exceptions=True，单失败降级为错误结果不拖垮整批 | 异常分支 | FlowCoder `agent/tool_execution.py#L152-168` | `tests/unit/test_tools_executor.py::test_parallel_batch_survives_single_failure` |  open |
| B-16 | tools | 分区是"连续安全工具合并"，非安全工具打断并行段——顺序语义要保持 | 测试名/实现注释 | FlowCoder `agent/tool_execution.py#L44-49` | `tests/unit/test_tools_executor.py::test_partition_consecutive_safe_merge` |  open |
| B-17 | tools | 禁用工具与未知工具必须区分：只有未知计入熔断计数 | 异常分支 | FlowCoder `agent/tool_execution.py#L92-114` | `tests/unit/test_tools_executor.py::test_unknown_tool_flagged_not_disabled`、`::test_disabled_tool_is_not_unknown` |  open |
| B-18 | tools | 沙箱模式切换失败保持原模式并返回明确错误，绝不静默降级 | 测试名/docstring | FlowCoder `tools/bash.py#L128-144` | `tests/adversarial/test_tools_run_process.py::test_run_success_exit_code_and_sections`（sandboxed=false 恒标注；模式切换语义随 M8 容器物化补全） |  open |
| B-19 | tools | stdout/stderr 分段标注格式化；双空显式 "(no output)"，不留空串歧义 | 异常分支 | FlowCoder `tools/bash.py#L99-107` | `tests/adversarial/test_tools_run_process.py::test_format_output_sections_and_no_output` |  open |
| B-20 | context | 压缩重建消息必须带 transcript 路径逃生门——摘要有损，细节必须可达 | 异常分支 | FlowCoder `context/manager.py#L158-176` | 待落 | open |
| B-21 | context | 保留窗口绝不留悬空 tool_result：keep_start 回退到配对 assistant，宁可多留一对 | 异常分支 | FlowCoder `context/manager.py#L239-255` | 待落 | open |
| B-22 | context | 摘要前缀回收空间低于阈值时退化为不压缩，防"压了个寂寞" | 异常分支 | FlowCoder `context/manager.py#L258-262,L326-329` | 待落 | open |
| B-23 | context | 压缩熔断器连续失败 3 次后 open，自动压缩拒绝并提示手动 | 异常分支 | FlowCoder `context/manager.py#L270-282,L315-316` | 待落 | open |
| B-24 | context | 大结果落盘用 O_EXCL 幂等写：同 tool_use_id 只写一次，重复静默跳过 | 异常分支 | FlowCoder `context/tool_results.py#L66-76` | `tests/unit/test_gesta_store.py::test_spill_tool_result_idempotent_and_previewed`（O_EXCL 写原语由 `tests/unit/test_state_atomic.py::test_write_excl_first_true_second_false` 承载；context 模块 M2.3 开工时按其聚合语义补专属用例） | covered |
| B-25 | context | 替换决策跨轮持久（seen/replacements），且绝不 mutate 原始对话 | 异常分支 | FlowCoder `context/tool_results.py#L104-117,L121-134` | 待落 | open |
| B-26 | context | 聚合超限按单条大小降序逐个落盘替换直到达标 | 实现细节 | FlowCoder `context/tool_results.py#L159-183` | 待落 | open |
| B-27 | context | 陈旧裁剪若实现必须把边界记进状态——FlowCoder 无状态跑法自认 drift trade-off | docstring 自认 | FlowCoder `context/tool_results.py#L112-114` | 待落 | open |
| B-28 | context | 压缩阈值锚点优先真实 API 用量，冷启动退化字符估算 | 实现注释 | FlowCoder `context/manager.py#L307-310` | 待落 | open |
| B-29 | context | 摘要协议必须含"用户消息原文不可改写"约束与结构化分段 | 提示词资产 | FlowCoder `context/manager.py#L127-146` | 待落 | open |
| B-30 | limen | 不存在路径拼接尾部可能重新引入 ".."：resolve 祖先后必须对完整结果再 resolve(strict=False) 重查 | 异常分支 | FlowCoder `permissions/sandbox.py#L45-48` | `tests/unit/test_limen_reachability.py::test_b30_double_resolve_rejects_dotdot_tail`、`::test_b30_dotdot_tail_into_sibling` |  open |
| B-31 | limen | 触路径工具缺路径参数视为 deny 而非跳过 | 异常分支 | FlowCoder `permissions/checker.py#L117-118` | `tests/unit/test_limen_reachability.py::test_check_path_missing_param_denied`、`tests/unit/test_limen_matrix.py::test_missing_path_denied_not_skipped` |  open |
| B-32 | limen | 危险命令黑名单用结构化正则清单（可追加），不做散落 if/else | 实现模式 | FlowCoder `permissions/dangerous.py#L10-18,L184-187` | `tests/unit/test_limen_guards.py::test_dangerous_commands_detected`、`::test_benign_commands_pass` |  open |
| B-33 | limen | 档位语义用显式表驱动（模式 × 工具类矩阵），不做分支散布 | 实现模式 | FlowCoder `permissions/modes.py#L14-29` | `tests/unit/test_limen_matrix.py::test_boundary_table_matches_overview_s9` |  open |
| B-34 | limen | 判定层短路先决、命中即返回，层间不做合并回溯 | 实现模式 | FlowCoder `permissions/checker.py#L44-73` | `tests/unit/test_limen_matrix.py::test_sensitive_write_denied_every_mode`（READ_ONLY 档只读方言先决短路即顺序证明） |  open |
| B-35 | serve/M8 | 命令超时必须双层：容器内 TERM→KILL + 宿主 grace 兜底，缺一层就有逃逸窗口 | 实现注释 | FlowCoder `sandbox/container.py#L64-67,L135,L160` | 待落 | open |
| B-36 | serve/M8 | 容器归还即销毁重建防状态串台；池创建统一打 label 供 reaper 清遗留 | 实现模式 | FlowCoder `sandbox/pool.py#L32,L62-101`、`sandbox/reaper.py#L43-55` | 待落 | open |
| B-37 | evals | 评测默认温度 0 保可复现；超时失败不回喂（无有效失败信息） | 实现细节 | FlowCoder `eval/runner.py#L96-101,L167` | 待落 | open |
| B-38 | orchestration | 状态迁移 Hook 的异常不得只 print 吞掉，必须 logging 并上浮观测面 | 异常分支 | EvoFlow `collab/state_transitions.py#L208-224` | 待落 | open |
| B-39 | orchestration | 禁止重载领域词命名（EvoFlow `evoflow/plans/` 是模型套餐，与任务 plan 撞名） | 目录实存 | EvoFlow `packages/harness/evoflow/plans/`（catalog/bindings/adapters） | 待落 | open |
| B-40 | vigilia | 清扫必须有分批游标：无 offset 重查同一 top-N 会紧密空转 | docstring 自认历史坑 | EvoFlow `zombie_run_sweeper.py#L39-42` | 待落 | open |
| B-41 | vigilia | cron/调度依赖本地时钟（休眠/漂移敏感），同分钟去重是唯一防重放闸 | 实现细节 | EvoFlow `automation_runner.py#L33` | 待落 | open |
| B-42 | vigilia | once 任务触发成功立即幂等标记 once_fired，标记失败记 warning 不阻塞 | 实现细节 | EvoFlow `automation_runner.py#L945-951` | 待落 | open |
| B-43 | orchestration | 编排门返回结构化错误载荷（error_code/message/hint）而非抛异常——模型可读可重试 | docstring+实现 | EvoFlow `collab/supervisor_plan_gate.py#L1,L93-108` | 待落 | open |
| B-44 | vigilia | 运行状态真值在运行时侧时，重启必有 stale running——需启动 + 周期双 reconcile | docstring 自认历史坑 | EvoFlow `zombie_run_sweeper.py#L19-48` | 待落 | open |
| B-45 | gesta | gate/审批类消息必须先持久化定序，用户的跟进行才能排在后面 | Transcript 规则注释 | EvoFlow `agents/human_gate_tools.py#L14-16` | `tests/unit/test_gesta_store.py::test_turn_seq_single_point_allocation`（seq 由 store 持锁单点分配，调用方不可指定） | covered |
| B-46 | gesta | 会话正文不做百表 SQLite 单体；Questor 用 append-only JSONL 真相源 + SQLite 仅可重建索引 | 规模实测 | EvoFlow `persistence/schema.py`（2191 行/123 表）、`persistence/chat_message_content.py#L1` | `tests/architecture/test_gesta_append_only.py`（append-only 机械保证）、`tests/unit/test_gesta_store.py::test_index_matches_rebuild_and_self_heals`（索引为可重建缓存）、`tests/integration/test_gesta_roundtrip.py`（JSONL 唯一真相源回放） | covered |
| B-47 | gesta | 事件流要有独立镜像/持久化位支撑断线恢复 | schema 实存 | EvoFlow `persistence/schema.py#L449,461` | `tests/integration/test_gesta_roundtrip.py::test_full_lifecycle_replay`（Event 随记录流持久化，seq 为续传锚点） | covered |
| B-48 | （M7 mcp/记忆） | FTS5 中文检索用 CJK bigram + OR 引号技巧（unicode61 会把中文连成整串） | 实现注释 | EvoFlow `memory/store.py#L557` | 待落 | open |
| B-49 | vigilia | per-task asyncio.Lock 字典 + 守卫锁防 tick 重入同一任务 | 实现模式 | EvoFlow `unattended_task_pipeline.py#L40-41,L211-217` | 待落 | open |
| B-50 | limen | read_only 的浏览器粒度：拦 navigate/click/type、放 observe/screenshot（ReadOnly 短路在 mutates 之前） | 实现注释 | wuu `internal/tools/boundary.go#L65-80` | `tests/unit/test_tools_impl.py::test_todo_granularity_in_read_only_mode` |  open |
| B-51 | limen | Guard 不得阻塞等用户输入、不得返回 ask——硬判与审批严格分层 | 接口注释 | wuu `internal/tools/boundary.go#L38-42` | `tests/unit/test_limen_matrix.py::test_gate_has_no_ask_effect`（AST 扫 gate.py 无 'ask' 字面量） |  open |
| B-52 | limen | 拒绝错误必须带 model_next_action，指导模型下一步而非只说不行 | 实现模式 | wuu `internal/tools/boundary.go#L48-52,L90` | `tests/unit/test_limen_matrix.py::test_file_read_outside_root_denied_when_enforced`（model_next_action 非空断言） |  open |
| B-53 | limen | 敏感路径按段匹配 + 源码扩展名豁免（credentials.go 是源码），防子串误伤与 symlink 绕过 | 注释+实现 | wuu `internal/tools/sensitive_paths.go#L13-14,L34-64` | `tests/unit/test_limen_guards.py::test_credential_directory_is_sensitive`、`::test_source_extension_exempt`、`::test_private_keys` |  open |
| B-54 | limen | 敏感写包括 unconfined 一律拒；unconfined 读降级输出脱敏——档位不解除守卫 | 语义规格 | wuu `internal/tools/sensitive_paths.go` | `tests/unit/test_limen_guards.py::test_write_blocked_all_modes`、`::test_read_blocked_unconfined_downgrades`、`tests/unit/test_limen_matrix.py::test_sensitive_write_denied_every_mode` |  open |
| B-55 | habena | 审批硬拒三件：凭据调用、参数试图 permission_mode 提权、敏感路径写；判定用目标非内容 | 实现+测试名 | wuu `internal/approvefor/review.go#L87-112`、`review_test.go#L31` | 待落 | open |
| B-56 | habena | 审批五态 allow/deny/unsure/failed/cancelled；unsure/failed 不是安全判定，不得当总括授权 | 实现常量 | wuu `internal/approvefor/review.go#L15` | 待落 | open |
| B-57 | config | 仓库/共享配置分层合并时 strip 用户专属安全字段（provider/凭据/permission_mode） | 注释+实现 | wuu `internal/config/settings_layer.go#L23,L48-63,L108` | `tests/unit/test_config_loader.py::test_user_only_fields_stripped_from_project_layers`、`::test_strip_warning_deduped_within_process` | covered |
| B-58 | limen | 沙箱 provider 契约：必须 full enforcement，partial 拒绝；不支持平台 fail closed | 实现常量 | wuu `internal/processsandbox/sandbox_other.go#L11-14` | `tests/unit/test_config_loader.py::test_user_only_fields_stripped_from_project_layers`（M2.1 已落） |  open |
| B-59 | serve | 反向请求的响应先路由给 pending 调用表等待者，再进 method switch，否则被 unknown method 吞掉 | 实现注释 | wuu `internal/appserver/server.go#L205` | 待落 | open |
| B-60 | serve | 协议版本严格相等，不做降级兼容 | 实现常量 | wuu `internal/appserver/protocol.go#L26` | 待落 | open |
| B-61 | serve | deferred content 与反向 RPC 都是客户端 opt-in 能力声明，不默认开启 | schema 字段 | wuu `internal/appserver/protocol.go#L279-285` | 待落 | open |
| B-62 | serve | 慢发现/维护一律后台化（startBackground），串行分发不被卡住 | 实现模式 | wuu `internal/appserver/server.go#L436,L659,L955` | 待落 | open |
| B-63 | habena | 插话 client_id 幂等：INSERT OR IGNORE + "client_id 在 history 中即已送达" | SQL 实现细节 | wuu `internal/session/inbox.go#L59,L93` | 待落 | open |
| B-64 | habena | steer 的 ExpectedTurnID：空=旧客户端兼容放行，非空不匹配当前 turn=拒绝 | 实现+校验函数 | wuu `internal/appserver/turn_handlers.go#L880-887` | 待落 | open |
| B-65 | habena | held_user_work 双 origin（queue/steer）落盘，整表替换事务，重启重建 | 实现细节 | wuu `internal/session/held_user_work.go#L11-12,L24-46` | 待落 | open |
| B-66 | review | diff 在写工具执行时刻计算并随结果持久化，前端不吃事后重扫的二手 diff | 实现注释 | wuu `internal/tools/diff.go#L33-35` | 待落 | open |
| B-67 | habena | 插话消费只在步前边界（BeforeStep）；live 分叉允许未结算的最终答案作分叉点 | 实现+调用点 | wuu `internal/agent/loop.go#L400-401`、`internal/appserver/fork.go#L234` | 待落 | open |
| B-68 | schemas | 生成物必须跨平台字节可复现：banner 里的路径一律用正斜杠，`path.relative()` 直接入文会让 Linux runner 重生成结果与 Windows 提交件不一致，gen:check 必然报漂（已发生：CI 红、本地绿） | CI fix 记录 | `ui/scripts/gen-types.mjs#L31-42`、`ui/src/rpc/generated/app_server-v0-1.d.ts#L1` | ci.yml `test` job 的 windows leg 跑 `npm --prefix ui run gen:check` | covered |
| B-69 | ci | 写进 CI 的命令必须先原样本地跑过；禁止只存在于 CI 的 flag（否则本地永远验不到它）——已发生：给 pytest 加了不存在的 `--full-path`，双 OS 全红 | 本项目 CI 失败记录 | `justfile`、`.github/workflows/ci.yml` | `tests/architecture/test_ci_parity.py::test_ci_invents_no_gate_commands_of_its_own` | covered |
| B-70 | ci | 本地 `language: system` 钩子依赖的必须先装：`pre-commit run --all-files` 排在 `npm ci --prefix ui` 之前时，gen-check 钩子必炸 `ERR_MODULE_NOT_FOUND` | 本项目 CI 失败记录 | `.pre-commit-config.yaml`、`.github/workflows/ci.yml` | 待落（属 workflow 步骤顺序，无单元可断言；靠本地原样跑兼顶） | open |
| B-71 | state | 锁文件释放后禁止删除——删除-重建会让并发进程锁到不同 inode，互斥失效 | 实现注释 | wuu `internal/storelock/store_lock.go#L33-35` | `tests/unit/test_state_locks.py::test_lock_file_survives_release`、`tests/adversarial/test_state_lock_contention.py` | covered |
| B-72 | state | 原子写的临时文件必须与目标同目录——跨目录 rename 不原子，崩溃可留半写目标文件 | 实现细节 | wuu `internal/securefs/securefs.go#L44-56` | `tests/adversarial/test_state_atomic_failure.py::test_temp_file_lives_in_target_directory`、`::test_failure_leaves_no_partial_target_and_no_temp` | covered |
| B-73 | state | 路径解析的 env 覆盖必须每次调用时求值——import/init 时求值会让测试与多实例拿到陈旧 home | 实现细节 | wuu `internal/statepath/statepath.go#L34-37` | `tests/unit/test_state_paths.py::test_home_env_read_at_call_time` | covered |
| B-74 | gesta | 会话 JSONL 读取必须容忍残尾（空行与坏行跳过）——崩溃半行不得阻断回放与后续追加 | 实现注释 | wuu `internal/agentthread/store.go#L375-406` | `tests/adversarial/test_gesta_tail_tolerance.py`（三用例：回放、续追加、索引重建） | covered |
| B-75 | config | 共享配置层的用户专属字段 strip 必须大小写不敏感全拼写删除——raw map 合并时大小写变体绑定同一字段 | 实现细节 | wuu `internal/config/settings_layer.go#L279-294` | `tests/unit/test_config_loader.py::test_user_only_fields_stripped_from_project_layers`（含 API_Key 变体删除与 my_api_key 不误伤） | covered |
| B-76 | testenv | Windows 的 TMP 可带 8.3 短名（CI runner 实测 `RUNNER~1`）：`resolve()` 展开长名后与原始字符串不等，任何 raw-vs-resolved 直接比较的断言在本机绿、runner 红——fake_home 必须先 resolve 再喂 env 与 yield | 本项目 CI 失败记录 | `.github/workflows/ci.yml` test job (windows-latest) 红 `test_home_env_read_at_call_time`、`test_standard_dirs_live_under_home`；`src/questor/testenv/fake_home.py` | `tests/unit/test_state_paths.py::test_standard_dirs_live_under_home`（fake_home 统一形态后在短名 runner 上同绿） | covered |
| B-77 | tools | pywin32 的 PyHANDLE 被 GC 时关闭底层句柄——Job Object 句柄只留 int 拷贝则 Assign 报"句柄无效"，必须把 PyHANDLE 本体持活在 ManagedProcess 上 | 本项目实测（run 工具首跑即现） | `src/questor/tools/processmgr.py#_new_kill_on_close_job` docstring | `tests/adversarial/test_tools_run_process.py::test_run_background_then_read_and_stop`（spawn→assign→stop 全链） | covered |
| B-78 | tools | 增量读子进程管道必须 read1——`read(n)` 阻塞到缓冲满/EOF，后台输出卡在首行后不可见 | 本项目实测（后台进程读空输出） | `src/questor/tools/processmgr.py#_read_stream` 注释 | `tests/adversarial/test_tools_run_process.py::test_run_background_then_read_and_stop` | covered |
| B-79 | ci/平台 | 平台标记代码的单平台自测盲区：盘符路径（C:/Windows）在 POSIX 上是相对路径、会落回工作区内（越界测试永远放行）；`subprocess.CREATE_NEW_PROCESS_GROUP` 等 Windows-only 属性运行时惰性求值没问题、pyright 的 Linux 视角却报错——Windows 上自测全绿不等于 Linux leg 绿 | 本项目 CI 失败记录（ubuntu leg 红 `test_search_path_outside_root_denied` + pyright `reportAttributeAccessIssue`） | `.github/workflows/ci.yml` test matrix (ubuntu-latest)、`tests/unit/test_tools_impl.py`、`src/questor/tools/processmgr.py` | `tests/unit/test_tools_impl.py::test_search_path_outside_root_denied`（改平台中立路径 /outside）；pyright 一次性 `--pythonplatform=Linux` 复核 0 错（posix 视角入门禁需先重构 locks.py 的平台分支 import，留痕另评） | covered |
