# cli —— 模块设计篇（M2.3）

状态: 已落盘并真机验证（2026-10-12） | provenance: 形状参照 wuu `cmd/wuu` 的子命令划分，未搬代码
关联: B-87（stdout 洁净）、B-83（aclose）、ADR-0020（薄壳与 HandlerCtx）、`structure.md` §5（cli 依赖面）

## 职责与边界

命令行入口 `questor` / `qst`：`version`、`session list`、`exec [--resume]`。
矩阵上只可 import `serve` `engine` `providers` `config` `schemas` `version`——**拿不到
`tools`/`context`/`prompts`/`gesta`**。这不是限制而是设计：装配住在
:func:`questor.serve.assembly.build_engine`，会话读写住在 `serve`，于是 CLI 与将来的
桌面壳共用同一条启动路径（overview §14「GUI 能力必须经协议可达」也管命令行）。

代价如实记：`questor version` 需要 `version` 叶模块，所以给它开了一行矩阵（structure §5
已同步），而不是让 cli 去 import 一个上层模块。

## 方法与决策

- **stdout 洁净（B-87）**：`--json` 时每行一帧协议通知，其余一律 stderr。失败也不往
  stdout 吐半个字符（退出码 2 + stderr 原因），否则 runner 会把错误文本当帧解析。
- **`--json` 复用 serve 的事件映射**：`notification_of` 是唯一映射处——CLI 不自造
  一套"命令行专用形状"，否则同一个事件会有两种对外表示（两处真相）。
- **凭据来源只有两处**：`config` 的 `[model].api_key`（用户层；项目层的同名字段被
  `config` strip 掉，B-57/B-75）或环境变量 `QUESTOR_MODEL_API_KEY`。缺失时**告警并继续**
  而不是提前拒绝——本地端点（Ollama/vLLM 一类）可以合法地没有凭据。
- **工作区 id 是一处已知的重复计算**：cli 不能 import `workspaces`，只能自己算
  sha256[:16]。这条重复在 M3 `workspaces` 注册表落地时必须删掉改走 serve 方法，
  已在代码注释与本文件登记，不留成隐性双真相。
- **aclose 在 `finally` 里**：成功与失败两条路径都收口（B-83），并由
  `test_exec_closes_model_even_when_the_run_fails` 钉住失败路径。

## 本期未做（不当已完成）

- `init`（写配置样例）与 `session show`（单会话详情）：后者需要先给 `serve` 加
  `thread/show` 方法并同步 `protocol.md` §3——属契约增量，排到 M3（前端真接本来就要读单会话）。
- 进度条/彩色输出、`resume` 交互式选择器：界面面，可后置。

## 真机验证（M2 出口判据的证据）

```
questor exec "write hello.txt ... then read it back" --json
→ {"method":"run/status","params":{"status":"running"}}
→ {"method":"item/started","params":{... "name":"write" ...}}
→ {"method":"turn/usage","params":{"input_tokens":169,"output_tokens":148,"cache_read":1792,...}}
→ {"method":"run/status","params":{"status":"completed"}}   exit=0
questor session list → 该会话 last_seq=22, turn_count=1, run_count=1（落盘可回放）
```
这次真机跑通还当场曝出 B-88（assistant 轮次不入历史 → 真实端点 400 拒悬空 tool_result），
fake model 永远测不出来。
