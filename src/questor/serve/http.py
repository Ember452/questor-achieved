"""http —— 本地 ASGI 顶层 app（M3b-3，ADR-0022）：`ui/dist` 静态伺服 + `/ws` 端点。

**默认只绑 127.0.0.1** 是启动时硬约束（`assert_localhost_only`），对外暴露属 L4 能力
（overview §13 未决项 5，需另开 ADR + 鉴权）。

装配点：`create_app(create_engine, ui_dist)` 返回 starlette.app；`serve_http(app, host, port)`
用 uvicorn 起。cli 与 `just dev-web` 都走这一路径。uvicorn 只在本地跑，生产由 M8 部署另议。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from starlette.applications import Starlette
from starlette.routing import Mount, WebSocketRoute
from starlette.staticfiles import StaticFiles

from questor.engine import Engine
from questor.schemas.model import PermissionMode
from questor.serve.app_server import AppServer
from questor.serve.fanout import Fanout
from questor.serve.ws import make_ws_handler

_ALLOWED_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def assert_localhost_only(host: str) -> None:
    """对外暴露前必拒非本机 host（overview §13 未决项 5；鉴权属 M8 且需 ADR）。"""
    if host not in _ALLOWED_LOCAL_HOSTS:
        raise ValueError(
            f"M3 只允许本地绑定，host={host!r} 越界。"
            f" 可选：{sorted(_ALLOWED_LOCAL_HOSTS)}；对外暴露请走 M8 鉴权 ADR 后再开。"
        )


def create_app(
    *,
    create_engine: Callable[[str, PermissionMode], Engine],
    ui_dist: Path | None = None,
) -> Starlette:
    """装配一个 Starlette app：WS 端点 + 可选静态伺服（`ui/dist` 存在时挂）。

    每次连接 `subscribe()` 一个 Fanout 订阅；AppServer 是单例，跨连接共享 runs / inboxes。
    """
    fanout = Fanout()
    app_server = AppServer(create_engine=create_engine)
    ws_endpoint = make_ws_handler(app_server, fanout)
    routes: list[Mount | WebSocketRoute] = [WebSocketRoute("/ws", ws_endpoint)]
    if ui_dist is not None and ui_dist.is_dir():
        routes.append(Mount("/", app=StaticFiles(directory=str(ui_dist), html=True)))
    return Starlette(routes=routes)


def run_server(app: Starlette, *, host: str, port: int) -> None:
    """同步启动 uvicorn（阻塞到 Ctrl-C）；host 走 `assert_localhost_only` 再交 uvicorn。"""
    assert_localhost_only(host)
    import uvicorn  # noqa: PLC0415 —— 依赖 ADR-0022 引入；本地启动才需要，import 顶层会让 CI 拉整个 uvicorn 依赖面

    uvicorn.run(app, host=host, port=port, log_level="info")
