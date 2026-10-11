# limen —— 模块设计篇（M2.2）

状态: 随开工落盘 | 2026-10-11 | provenance: `# Reimplements wuu@wuu-main internal/tools/boundary.go + sensitive_paths.go + FlowCoder permissions/* — pitfalls: B-10 B-30 B-31 B-32 B-33 B-34 B-50..B-54 B-58`

## 职责与边界

唯一权威权限门：三档判定、可达性推导、敏感路径守卫、危险命令黑名单、模型可读
错误方言。依赖裁决（structure §5）：只 import 标准库与 schemas——可达根以纯数据
（`root_paths` 字符串列表）注入，**不 import workspaces**（is_within 的比较逻辑在
limen 内以 canonical + normcase + 分隔符边界重写，约 10 行，换来零依赖）。

## 方法：六层 → 三档 + 恒开守卫链

FlowCoder 六层判定（Plan 白名单/命令安全/路径沙箱/规则引擎/模式矩阵/ask 兜底）
的映射裁决（详见 `docs/specs/behavior-permissions-fc.md` 的采纳决定）：

| FlowCoder 层 | Questor 处置 | 落点 |
| --- | --- | --- |
| L0 Plan 白名单 | **拒绝**——Plan 是循环层提醒，计划文件属普通写域（B-10） | 无 |
| L1 命令安全 | 保留硬拒半边：危险命令结构化正则清单（B-32）；"安全白名单放行"随 M3 审批流（它回答"该不该送审"，M2.2 无送审层） | `commands.py` |
| L2 路径沙箱 | 升级为核心可达性推导（B-30 二段 resolve；B-31 缺参=deny 且**先于路径门**——unconfined 不查路径门但缺参仍是调用形状错误） | `reachability.py` |
| L3 规则引擎 | M2.2 不做（无第二个使用者，M7 再议） | 无 |
| L4 模式矩阵 | 三档 × 边界三元组**显式表**（B-33）：表里没有"关守卫"的列——档位不解除守卫（B-54）靠"表里没有那个开关"机械保证 | `matrix.py` |
| L5 ask 兜底 | 归 habena（M3）；Guard 契约不得返回 ask（B-51），护栏机械扫描 gate.py 无 "ask" 字面量 | 无 |

判定顺序（B-34 短路先决）：参数提权前哨 → 只读闸 → B-31 缺参 → 敏感路径
（B-53 按段匹配+源码扩展豁免；B-54 写恒拒/unconfined 读降级脱敏）→ 危险命令 →
路径门。拒绝一律带 `error_kind + reason + model_next_action`（B-52）。

## 取舍与被否决项

- 敏感路径的源码扩展**豁免清单只含纯代码扩展**（.py/.go/...）：文档扩展（.md/.txt）
  刻意不豁免——凭据目录里的文档按敏感处理，误伤文档的代价远小于放行凭据；
  `.env.example` 模板与 `.pub` 公钥显式豁免（实测用例钉住）。
- `rm -rf /` 类正则的尾部边界用 `(?=\s|$)` 而非 ``——实测 `/` 后无单词边界，
  `` 让行尾的 `rm -rf /` 逃过检测（对抗测试抓到后修正）。
- **架构断言（第三条硬线）**：`test_permission_gate_single_entry`——只有
  `tools/executor.py` 可 import `limen.gate`；limen 包内 re-export 合法；
  "守卫有齿"分支断言消费者存在。负向验证：向 impl/read.py 注入 import → 红 → 复原。

## 对应测试

`test_limen_matrix`（三档×调用形状全组合 + 无 ask 护栏）、`test_limen_guards`
（B-32/53/54）、`test_limen_reachability`（B-30/31/大小写/symlink）、
`tests/architecture/test_permission_gate_single_entry`。
