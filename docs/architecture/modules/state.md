# state —— 模块设计篇（M2.1）

状态: 随开工落盘 | 2026-10-11 | provenance: `# Reimplements wuu@wuu-main internal/statepath/statepath.go + internal/securefs/securefs.go + internal/storelock/store_lock.go — pitfalls: B-71 B-72 B-73`

## 职责与边界

路径单点解析（`QUESTOR_HOME` 每次调用时求值，B-73）、原子写（同目录临时文件 → fsync →
`os.replace`，B-72）、O_EXCL 幂等写（B-24 的原语）、跨进程文件锁（内核持有、锁文件
永不删除、25ms 重试 / 60s 硬超时，B-71）、存储编码助手。全部为同步阻塞 API，
异步包装随 M2.2 engine 落地（engine 在事件循环内经 `asyncio.to_thread` 调用）。

## 公共 API（`questor.state`）

`questor_home / sessions_dir / index_dir / files_dir / workspaces_dir / config_path /
thread_path / tool_result_path / validate_entity_id / validate_filename_component /
sanitize_slug / workspace_dir_name / write_atomic / write_excl / mkdir_secure /
store_lock / StoreLock / LockTimeoutError`

## 边界行为要点

- id 两套校验：Questor 实体 id 严格 `^[a-z0-9][a-z0-9-]*$`（data-model §1）；
  外部 id（provider tool_use_id）按文件名组件校验（拒绝分隔符/冒号/点项）。
- 原子写任何一步失败：临时文件必被清理、目标保持旧内容；Windows 上 `os.replace`
  原子替换已存在目标，mode 位尽力而为、不作为安全保证。
- 锁的语义：内核持有（msvcrt.locking / fcntl.flock），进程死即释放——没有心跳、
  没有"陈旧锁清理"（加了反而引入竞态）；锁文件释放后留在原地（同 inode 竞态，B-71）。

## 对应测试

unit：`test_state_paths / test_state_atomic / test_state_locks`；
adversarial：`test_state_atomic_failure`（崩溃注入 + B-72 同目录）、
`test_state_lock_contention`（真实子进程：超时与死亡释放）。
