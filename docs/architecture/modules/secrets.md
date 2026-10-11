# secrets —— 模块设计篇（M2.1）

状态: 随开工落盘 | 2026-10-11 | 参照: wuu `internal/credentialstore`（语义，未搬代码）；依赖: ADR-0013（keyring）

## 职责与边界

凭据存取：OS keyring 优先（Windows 凭据管理器等）；keyring 失败回落
`<home>/secrets/<key>` 明文文件（0600，一次性告警明说"这不是加密存储"——
诚实呈现优先）。删除两处都清。

## 纪律（红线 ①）

- 值一律以 `pydantic.SecretStr` 出入：`repr` / `str` 不泄漏，显式
  `get_secret_value()` 才可见——凭据值永不进日志与会话记录。
- 键名即回落文件名：统一走 `validate_filename_component`（拒绝分隔符/冒号/点项）。
- keyring 后端的失败形态不可枚举：`except Exception` 一律回落（这是边界层
  容错，不是业务逻辑吞错）。

## 对应测试

`tests/unit/test_secrets_store.py`（keyring 往返经 `testenv/fake_keyring`、
repr 不泄漏、回落文件与一次性告警、POSIX 0600、双存清删）。
