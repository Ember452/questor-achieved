# ADR-0013 — M2.1 地基依赖引入（pydantic v2 / keyring / import-linter）

状态: accepted
日期: 2026-10-11 | 关联: `AGENTS.md` §四（新依赖先落 ADR；跨边界数据一律 pydantic v2）、
`overview.md` §4（核心依赖保持极简）、`structure.md` §5（import-linter 矩阵）、ADR-0012

## 结论

M2.1 开工引入三个第三方依赖，其余一律不引：

| 依赖 | 组 | 用途 | 版本下界 |
| --- | --- | --- | --- |
| `pydantic` | 运行时 | 跨边界数据绑定（AGENTS §四"跨边界数据一律 pydantic v2，禁止裸 dict"；schemas JSON 仍是真相源，pydantic 只做绑定） | `>=2.0` |
| `keyring` | 运行时 | `secrets` 模块的 OS keyring 后端（Windows 凭据管理器等），overview §6 "凭据存储（OS keyring 优先）" | `>=25.0` |
| `import-linter` | dev | 依赖方向的声明式契约（structure §5 预案："随 M2 首批真实模块引入"），与 AST 矩阵双层并存 | `>=2.0` |

## 理由与取舍

- **pydantic v2**：早已是既定纪律（overview §4"pydantic v2 起步"），M1 只因"模块未物化"未引入。
  M2.1 的 `schemas/model.py` 绑定与 gesta 实体是第一个真实使用者。代价：安装体量（pydantic-core），
  换来类型校验与不可变模型（frozen）的机械保证。
- **keyring**：Windows 凭据管理器经 `keyring` 库访问是事实标准；自己经 ctypes 调 DPAPI/CredWrite
  属于重新发明边界层。文件回落（0600 + 告警）只作 keyring 不可用时的退路，不是平等后端。
  代价：传递依赖若干（jaraco 类），均为成熟维护中的包。
- **import-linter**：AST 矩阵测试只能查"顶层包 import 了谁"，查不了循环 import、也挡不住
  同包内绕行。声明式 layers 契约在 CI 里独立执行，两层各查各的。0 违规起步、不设 baseline
  （structure §5）。代价：CI lint job 多跑一条命令（本地与 CI 同步加，parity 测试跟随）。

## 被否决的选项

- **手写 pydantic 替代（dataclass + 手工校验）**：违反 AGENTS §四明文纪律，且 frozen/校验器/
  JSON schema 输出都要重造。
- **ctypes 直调 Windows 凭据 API**：边界层学费已在 wuu 付过（它用系统机制），ctypes 方案还要
  自行处理跨平台分支；keyring 把平台差异收进一个稳定接口。
- **只要 AST 矩阵不要 import-linter**：M1 复审明确把 import-linter 定为 M2 首批模块的随行义务
  （structure §5 预案、`contracts.yml` 注释），跳过即偏离已定决策。
- **SQLAlchemy/cryptography 等一并引入**：M2.1 没有第二个真实使用者（SQLite 索引推迟到 M4，
  见 development-plan M2.1 实际结果留痕）。

## 适用条件与失效条件

**适用**：M2.1 起长期有效；新增依赖仍须各自落 ADR。

**触发重新评审**：① keyring 在目标平台出现不可修复的缺陷 → 文件后端转正需新 ADR；
② import-linter 与 AST 矩阵出现长期重复报警 → 收敛为一层（保留可执行的那层）；
③ pydantic 主版本升级破坏绑定生成 → 锁定 v2 大版本，升级走独立 ADR。
