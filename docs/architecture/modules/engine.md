# engine —— 模块设计篇（M2.2）

状态: 随开工落盘 | 2026-10-11 | provenance: `# Reimplements FlowCoder agent/{core,events,budget,output_recovery,conversation}.py — pitfalls: B-01..B-08 B-11`

## 职责与边界

内置引擎循环：turn 生命周期（queued→running→终态，经 gesta 白名单）、事件双轨
（对外 AgentEvent + 落盘 gesta 记录）、止损三重（M2.2 = 迭代数 + 时间维；token/成本
维随 M2.3 providers 的真实用量累计接入）。
ModelPort 是内核定义的 port（R1）——providers（M2.3）注册实现，循环不按厂商分支。
M2.3 形状定死：port 的方法签名只收 `ModelRequest`（住 `schemas/llm.py`），新字段
不再改签名；`aclose` 与 `capabilities` 是 port 的必备项（B-82/B-83）。

## 方法与决策

- **形状护栏（B-05/B-06 的机械形式）**：`tests/unit/test_engine_shape.py`——
  阈值常量只许住 constants.py（AST 扫 UPPER_CASE 赋值，护栏落地时当场咬住
  output_recovery 里重复的提示词常量，迁往 prompts 资产）；loop.py 单函数 ≤80 行
  （60 过紧——编排函数天然 60-80；真正的反例是 FlowCoder 的 ~400 行 `_run_loop`，
  理由记录在护栏 docstring）。
- **事件双轨与持久化边界**：`item/started|completed` / `turn/usage` / `run/status`
  落盘；**delta 不落盘**——正文以 message Item 为唯一真相，delta 是传输态
  （重复存储制造两套真相）；`TurnStarted/Converging/Loop*` 是内部节拍不单独入协议族。
- **B-02 收敛**：预算触限注入收敛请求 + **保留只读工具 schema**（FlowCoder 撤光的
  修正）；收敛轮仍幻觉工具调用 → 强制 failed。两条路径各有测试。
- **B-03 熔断**：未知工具连续 ≥3 终止；计数在 `_dispatch` 的批结果处裁决，
  并行批不清零、串行已知成功才清零。第一版实现丢了跨迭代累加——fake model 的
  "脚本耗尽即响亮报错"设计把它当场抓了出来（这正是 fake 对齐真实语义的价值）。
- **B-08 恢复**（M2.3 改形）：max_tokens 触顶后把**下一次请求的 `max_output_tokens`**
  提到天花板（由循环持有 `ceiling`，经 `RecoveryDecision.max_output_tokens` 回传）+ 最多
  3 次分段续写；非触顶轮计数清零；状态每 run 重置。**不再用 `set_max_output_tokens`
  写客户端内部状态**——同一个预算数字只能有一处真相，且并发共享一个客户端时
  逐请求携带才是对的（见 `engine/model.py` 的 port 注释）。
- **推理可见（M2.3）**：`StreamThinking` → 对外 `Thinking` 事件；**不写进正文**（写进去
  就会同时存在两套"模型说了什么"）。协议侧的事件族名待 M3 前端真接时连呈现与持久化
  形状一并定（`events.py` 已留痕），本期 `event_type_of` 归 "internal"。
- **取消传播**：CancelledError → 停进程树（ProcessManager 活对象句柄，无 PID 复用
  窗口）→ cancelled 终态 → **放行** CancelledError（AGENTS 纪律）。测试用
  `athrow(CancelledError)` 注入（aclose 只给 GeneratorExit，不是同一语义）。
- **事件类型遮蔽教训**：schemas 的 `RunStatus`（枚举）与 events 的 `RunStatus`
  （事件）同名——三处测试被"后导入遮蔽"咬过，统一别称（枚举 = `RS`，事件 =
  `RunStatusEvent`）。名字冲突本身就是坏味道，M3 接 habena 时考虑改名。

## 对应测试

`test_engine_loop`（单轮/工具往返/read_only 拒写/熔断/禁用不熔断/收敛两路/取消）、
`test_engine_shape`（B-05/06 护栏）、`tests/integration/test_single_turn_kernel`
（M2 出口演示：三步真实链 + 落盘可回放）。
