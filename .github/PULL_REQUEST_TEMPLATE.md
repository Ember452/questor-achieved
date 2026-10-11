<!-- 标题：type(scope): 一句话（英文 Conventional Commits，≤72 字符） -->

## 改动内容

<!-- what changed + WHY；一个 commit = 一个可独立回滚的逻辑变更 -->

## 自查（AGENTS.md 要求，勾选并贴实际输出）

```bash
just check
```

- [ ] `just check` 全绿（贴输出）
- [ ] 实现与其测试同 commit；护栏测试附**负向验证输出**（注入一次真实漂移，贴失败输出，再复原）
- [ ] 新坑条目（B-NN）已回填对应测试
- [ ] 契约改动已先改文档并递增版本号
- [ ] 不含真实会话 / prompt 全文 / 真实绝对路径 / 凭据
