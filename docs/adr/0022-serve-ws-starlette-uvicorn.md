# ADR-0022 — serve 传输层引入 starlette + uvicorn

状态: accepted
日期: 2026-10-12 | 关联: M3b-3 / `overview.md` §4（新增第三方依赖须先落 ADR）、
§8（一套会话层两种传输）、§13 未决项 5（对外暴露的边界）、§14（可逆性优先）、
`structure.md` §5 §7、ADR-0006（桌面壳与浏览器面板边界）、ADR-0013（M2 依赖引入纪律）、
ADR-0016（providers 自建 wire 层 over httpx）、`docs/architecture/modules/serve.md`、B-60 B-96

## 结论

M3b-3 落 WS 传输时，serve 层引入两个运行时依赖：

1. **`starlette>=0.40`**（ASGI 框架）：只用来做 `WebSocket` 端点与静态伺服，
   不引入 `fastapi`——本项目 handler 是 `(params, ctx) -> dict` 的纯函数族，不需要依赖注入与
   参数校验层；FastAPI 的多余抽象会把 serve 变成"另一套 handler 形状"，破 R4。
2. **`uvicorn>=0.30`**：只做本地/开发 ASGI 服务器；M8 自托管部署若要 gunicorn worker 或
   hypercorn，按新增依赖纪律另开 ADR。uvicorn 不进生产链路的核心（serve/ws.py 是 ASGI
   app，与具体服务器解耦）。

**明确不引入的**：`aiohttp`（与 httpx 重叠，ADR-0016 已定 httpx 是 providers 唯一 HTTP 客户）、
`fastapi`（理由见上）、`wsproto` / `websockets`（uvicorn 自带 WS 实现，本期不做子协议协商）。

**默认绑定**：`uvicorn` 启动硬 assert `host == "127.0.0.1"`（`test_serve_http_refuses_non_localhost`
钉住）；`--host 0.0.0.0` 或任意非 127.0.0.1 一律启动即报错。对外暴露属 L4 能力，需另开鉴权 ADR
（overview §13 未决项 5，wuu 教训"配对即授予控制权"）。

**与 Dispatcher 的接缝**：每个 WebSocket 连接建立时 `Fanout.subscribe()` 拿一个
`asyncio.Queue`，`WebSocket` 端点从自己的 queue 消费通知；上行帧 `await dispatcher.handle_line`，
下行经 sink 写回。传输层零业务知识，与 stdio 完全平级（overview §8 一套会话层两种传输）。

## 理由与取舍

- **为什么现在做**：M3 交付要求"网页 localhost 宿主与桌面共用同一契约"（overview §12
  M3 出口判据）；不引入 ASGI 就没法在同一进程里跑 WS + 静态伺服，只能把 UI 交给 vite dev
  server 或外部反代，属把产品形态让给外部工具。
- **为什么不引 FastAPI**：FastAPI 的 `@app.post` 装饰器 + Pydantic 参数校验与 Dispatcher 的
  `(params, ctx)` handler 是**两套形状**；同时用会让"GUI 能力必须经协议可达"（overview §14）
  出现两条入口，M8 加鉴权要改两处。
- **为什么不引 aiohttp**：ADR-0016 已定"providers 唯一 HTTP 客户端 = httpx"；再加一个客户端
  库会让 `uv.lock` 与 pip-audit 的面扩大一倍，且 aiohttp 自带的 server 侧与 starlette 重叠。
- **代价**：多两个运行时依赖（`starlette` + `uvicorn`，共 ~1.5 MB 依赖树，均 BSD 系许可）；
  uvicorn 与 Windows asyncio ProactorEventLoop 的已知坑要在 `tests/integration/` 里覆盖，
  不能只测 Linux/Mac（B-79 同族盲区）。

## 被否决的选项

- **纯标准库自写 WebSocket**：需要手解 RFC 6455 帧格式、掩码、控制帧、fragmentation，属
  AGENTS §二 (a) 类明令禁止的"重新发明边界层"。
- **FastAPI + WebSocket 端点**：与 Dispatcher handler 形状冲突；见上。
- **hypercorn**：ASGI 服务器，能力与 uvicorn 重叠；本项目不需要 HTTP/2 与 TLS 内置（走外部
  Caddy 反代，属 M8 议题）。多一个选项没有第二使用者。
- **aiohttp 同时做 client 与 server**：与 ADR-0016 冲突；providers 侧已经选 httpx。
- **桌面壳 Tauri 起本地 WS**（不引 starlette）：ADR-0024 桌面壳已推到 M4/M5；M3 交付里
  浏览器 localhost 是必要项，不能靠桌面壳。
- **不做鉴权就绑 0.0.0.0**：违反 overview §13 未决项 5；本期只本地，硬 assert 兜住。

## 适用条件与失效条件

**适用**：M3b-3 起 serve 的 WS 传输与本地网页宿主。
**触发重新评审**：① M8 自托管部署需要 TLS 终结 + HTTP/2 → 评审换 hypercorn 或 Caddy 反代；
② 出现第二种 ASGI 消费者（如 IM 渠道 webhook）→ 抽 `serve/http.py` 的 app factory；
③ starlette 或 uvicorn 停维 / 出现无法绕过的安全缺陷 → 按 ADR-0013 的依赖替换流程重开。
