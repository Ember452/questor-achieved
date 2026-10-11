# results —— 对照评测结果（不可变区）

- 目录按 `YYYY-MM-DD/<run-id>/` 组织，每目录一份符合 `../result.schema.json` 的
  `result.json` + artifacts（prompt / 原始报告 / grader 输出 / transcript / fixture，
  各带 sha256）。
- **被公开引用后不可修改**；重跑发新目录。
- **不放示例分数**——模板容易被误当证据。
- 禁含 API key、凭据、个人数据、私有仓库内容；redaction 必须记录在 result.json 的
  `disclosure.redactions`。
- 未完成的运行/含秘密的调试产物放 `bench/`（gitignore），不得移入本目录。
