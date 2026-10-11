# capability —— 模块设计篇（M2.1）

状态: 随开工落盘 | 2026-10-11 | 依赖裁决: ADR-0012（不 import config）

## 职责与边界

L4 能力旗标注册表：`FeatureFlag`（mcp/skills/hooks/plugins/web_host/im_channels/
containers/browser_panel）默认**全关**，显式 enable 才存在——与协议侧
"能力 opt-in 声明"（B-61）同源；`enabled_names()` 供协议 initialize 回显。

## 取舍

- stdlib only（不 import schemas/config）：旗标是"能力存在与否的声明"，
  读配置是装配职责（M2.3 serve/cli 组装时把 config 值注入 `enable_only`）。
- 非线程安全：组装发生在启动期单线程；引入并发需求时按 ADR 升级。
- `by_name` 对未知名字显式报错——组装层解析配置时不得静默忽略未知旗标。

## 对应测试

`tests/unit/test_capability.py`（默认全关、幂等开关、快照式覆盖、未知旗标）。
