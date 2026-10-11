# config —— 模块设计篇（M2.1）

状态: 随开工落盘 | 2026-10-11 | 参照: wuu `internal/config/settings_layer.go`（语义，未搬代码）；pitfalls: B-57 B-75

## 职责与边界

分层加载与合并：用户层 `~/.questor/config.toml`（base）→ 项目共享层
`<root>/.questor/config.toml` → 项目本地层 `.questor/config.local.toml`。
表递归深合并、标量与列表整体覆盖、输入绝不 mutate。项目根由调用方传入
（M2.2 workspaces / M2.3 cli 装配点），`None` 时只读用户层。

## strip 语义（B-57/B-75）

`USER_ONLY_FIELDS = {api_key, auth_token, permission_mode}` 在两个项目层以
大小写不敏感**全拼写**删除（`API_Key` 删、`my_api_key` 不误伤），任意深度；
每处 strip 发一次性去重警告（同层同字段进程内只发一次）。
`permission_mode` 只能来自用户配置（data-model §2，B-58 注）。

## 错误呈现

坏 TOML 抛 `ConfigError`（带文件路径）——配置错误必须可见，不静默跳过；
缺失层跳过（配置稀疏合法）。快照 frozen，`layers_applied` / `stripped`
供 initialize 的 `needs_setup`/`issues` 呈现（M2.3 serve 消费）。

## 对应测试

`tests/unit/test_config_loader.py`（合并顺序、strip 大小写变体与不误伤、
一次性警告、坏 TOML、合并不改写输入）。
