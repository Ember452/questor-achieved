"""cli —— 命令行入口（overview §6；矩阵上只可 import serve/engine/providers/config/schemas）。

薄壳是硬约束不是风格：CLI 不自己拼工具环境、不直接读会话目录——那两件事分别归
:mod:`questor.serve.assembly` 与 gesta。否则桌面壳将来要复刻一遍装配代码，等于两条
会漂移的启动路径（overview §14「不存在只有桌面壳能调的私有端点」同样管命令行）。

**stdout 洁净**（B-87）：`--json` 时 stdout 每行一帧 JSON，日志与人类可读输出走 stderr。
本期只落 `version` / `session list` / `exec`；`init` 与 `session show` 未做（缺 serve 侧
方法），已记在 development-plan 的 M2.3 实际结果里，不当已完成。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from pathlib import Path
from typing import Any, NoReturn

from questor.config import load_config
from questor.providers import ModelSpec, ProtocolName, create_model
from questor.schemas.model import PermissionMode
from questor.serve import AppServer
from questor.serve.assembly import build_engine, ensure_workspace_for_root, exec_turn
from questor.serve.dispatch import HandlerCtx
from questor.serve.envelope import encode_line
from questor.serve.http import assert_localhost_only, create_app, run_server
from questor.serve.notifications import notification_of
from questor.serve.stdio import serve_stdio, write_line
from questor.version import build_commit, questor_version

__all__ = ["main", "model_spec_from_config"]

_ENV_API_KEY = "QUESTOR_MODEL_API_KEY"
_CLI_CTX = HandlerCtx(request_id="cli", principal="cli", trace_id="cli")


def _log(message: str) -> None:
    """诊断与人类可读输出一律走 stderr：stdout 是给机器读的（B-87）。"""
    print(message, file=sys.stderr)


def model_spec_from_config(config: dict[str, Any]) -> ModelSpec:
    """配置字典 → `ModelSpec`。缺段/未知协议都显式爆炸，不用默认值蒙混。"""
    from pydantic import SecretStr

    table = config.get("model")
    if not isinstance(table, dict):
        raise ValueError(
            "配置缺少 [model] 段。最小可用配置：[model] 里给 protocol / base_url / model"
        )
    try:
        protocol = ProtocolName(str(table.get("protocol", ProtocolName.ANTHROPIC_MESSAGES)))
    except ValueError as exc:
        raise ValueError(f"未知 model.protocol：{table.get('protocol')!r}") from exc
    api_key = str(table.get("api_key") or os.environ.get(_ENV_API_KEY, ""))
    if not api_key:
        _log(f"警告：未配置凭据（config [model].api_key 或 {_ENV_API_KEY}），请求可能被端点拒")
    window = table.get("context_window")
    max_output = table.get("max_output_tokens")
    return ModelSpec(
        protocol=protocol,
        model=str(table.get("model") or ""),
        base_url=str(table.get("base_url") or ""),
        api_key=SecretStr(api_key) if api_key else None,
        context_window=int(window) if window else None,
        max_output_tokens=int(max_output) if max_output else None,
        supports_thinking=_opt_bool(table.get("supports_thinking")),
        supports_prompt_cache=_opt_bool(table.get("supports_prompt_cache")),
    )


def _opt_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _no_engine(thread_id: str, mode: PermissionMode) -> NoReturn:
    """会话/新建路径不需要引擎；被调即装配错误。"""
    raise AssertionError(f"不该起引擎：thread={thread_id} mode={mode}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="questor", description="Questor auditable agent")
    sub = parser.add_subparsers(dest="command", required=True)

    version = sub.add_parser("version", help="打印版本与构建标识")
    version.add_argument("--json", action="store_true", help="stdout 输出一帧 JSON")

    session = sub.add_parser("session", help="会话查询")
    session_sub = session.add_subparsers(dest="session_command", required=True)
    session_sub.add_parser("list", help="列出已落盘会话（一行 JSON）")

    execute = sub.add_parser("exec", help="非交互执行一轮任务")
    execute.add_argument("user_text")
    execute.add_argument("--thread", default=None, help="会话 id；缺省时新建")
    execute.add_argument("--resume", action="store_true", help="从盘上重建历史后继续")
    execute.add_argument("--cwd", default=".", help="工作目录（同时是注册根）")
    execute.add_argument(
        "--mode",
        choices=[mode.value for mode in PermissionMode],
        default=PermissionMode.STANDARD.value,
    )
    execute.add_argument("--json", action="store_true", help="stdout 每行一帧通知（机读）")

    serve = sub.add_parser("serve", help="启动长命服务（本地 http + WS）")
    serve_sub = serve.add_subparsers(dest="serve_command", required=True)
    http_run = serve_sub.add_parser("http", help="本地 http 宿主：ui/dist + /ws（ADR-0022）")
    http_run.add_argument("--host", default="127.0.0.1", help="仅允 127.0.0.1 / localhost / ::1")
    http_run.add_argument("--port", type=int, default=8765)
    http_run.add_argument("--cwd", default=".", help="工作目录（新建会话的默认根）")
    http_run.add_argument("--ui-dist", default=None, help="前端构建产物目录（缺省自动探 ui/dist）")
    stdio_run = serve_sub.add_parser(
        "stdio", help="本机 stdio NDJSON sidecar 宿主（桌面壳拉起，与 WS 同一方法表）"
    )
    stdio_run.add_argument("--cwd", default=".", help="工作目录（新建会话的默认根）")

    # M4 编排：薄命令，一切经 serve（AGENTS 纪律：CLI 不得有第二套装配路径）
    task = sub.add_parser("task", help="任务看板（经 serve）")
    task_sub = task.add_subparsers(dest="task_command", required=True)
    task_sub.add_parser("list", help="列出任务（一行 JSON）")
    task_show = task_sub.add_parser("show", help="查看单个任务")
    task_show.add_argument("task_id")
    task_create = task_sub.add_parser("create", help="新建任务（无落库计划会被编排门拒）")
    task_create.add_argument("title")
    task_create.add_argument("--plan", dest="plan_id", default=None, help="绑定计划 id")

    goal = sub.add_parser("goal", help="长跑目标（经 serve）")
    goal_sub = goal.add_subparsers(dest="goal_command", required=True)
    goal_sub.add_parser("list", help="列出目标（一行 JSON）")
    goal_create = goal_sub.add_parser("create", help="新建长跑目标")
    goal_create.add_argument("thread_id")
    goal_create.add_argument("objective")
    goal_create.add_argument("--max-rounds", type=int, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "version":
            return _cmd_version(args)
        if args.command == "session":
            return asyncio.run(_cmd_session_list())
        if args.command == "serve":
            if getattr(args, "serve_command", None) == "stdio":
                return _cmd_serve_stdio(args)
            return _cmd_serve_http(args)
        if args.command == "task":
            return asyncio.run(_cmd_task(args))
        if args.command == "goal":
            return asyncio.run(_cmd_goal(args))
        return asyncio.run(_cmd_exec(args))
    except (ValueError, KeyError) as exc:
        _log(f"错误：{exc}")
        return 2
    except KeyboardInterrupt:  # pragma: no cover - 交互中断不是缺陷
        _log("已中断")
        return 130


def _cmd_version(args: argparse.Namespace) -> int:
    payload = {"version": questor_version(), "commit": build_commit()}
    if args.json:
        print(encode_line(payload))
    else:
        _log(f"questor {payload['version']} ({payload['commit']})")
    return 0


async def _cmd_session_list() -> int:
    server = AppServer(create_engine=_no_engine)
    result = await server.thread_list({}, _CLI_CTX)
    print(encode_line(result))
    return 0


async def _cmd_task(args: argparse.Namespace) -> int:
    """任务看板薄命令（经 serve；编排门拒绝由 main 的 ValueError 分支回报）。"""
    server = AppServer(create_engine=_no_engine)
    if args.task_command == "show":
        result = await server.task_show({"task_id": args.task_id}, _CLI_CTX)
    elif args.task_command == "create":
        result = await server.task_create({"title": args.title, "plan_id": args.plan_id}, _CLI_CTX)
    else:
        result = await server.task_list({}, _CLI_CTX)
    print(encode_line(result))
    return 0


async def _cmd_goal(args: argparse.Namespace) -> int:
    """长跑目标薄命令（经 serve）。"""
    server = AppServer(create_engine=_no_engine)
    if args.goal_command == "create":
        result = await server.goal_create(
            {
                "thread_id": args.thread_id,
                "objective": args.objective,
                "max_rounds": args.max_rounds,
            },
            _CLI_CTX,
        )
    else:
        result = await server.goal_list({}, _CLI_CTX)
    print(encode_line(result))
    return 0


async def _create_thread(args: argparse.Namespace) -> str:
    thread_id = f"thread-{uuid.uuid4().hex[:12]}"
    workdir = Path(args.cwd).expanduser().resolve()
    # workspace_id 归一化单点在 workspaces.register（overview §14 路径单点解析）；
    # CLI 不得自己算 sha256，否则修哈希时两边会偷偷漂移。
    workspace_id = await asyncio.to_thread(ensure_workspace_for_root, workdir)
    server = AppServer(create_engine=_no_engine)
    await server.thread_create(
        {
            "id": thread_id,
            "workspace_id": workspace_id,
            "title": args.user_text[:60],
            "permission_mode": args.mode,
        },
        _CLI_CTX,
    )
    return thread_id


async def _cmd_exec(args: argparse.Namespace) -> int:
    snapshot = load_config(project_root=Path(args.cwd).expanduser().resolve())
    spec = model_spec_from_config(snapshot.data)
    model = create_model(spec)
    thread_id = args.thread or await _create_thread(args)
    try:
        engine = build_engine(
            model=model,
            cwd=args.cwd,
            mode=PermissionMode(args.mode),
            thread_id=thread_id,
        )
        async for event in exec_turn(
            engine, thread_id=thread_id, user_text=args.user_text, resume=args.resume
        ):
            _emit(event, machine=args.json)
        return 0
    finally:
        await model.aclose()  # B-83：成功与失败都要收口


def _emit(event: Any, *, machine: bool) -> None:
    """`--json` 走协议通知族（与 serve 同一映射，不另造一套 CLI 专用形状）。"""
    notification = notification_of(event)
    if machine:
        if notification is not None:
            print(encode_line({"method": notification.method, "params": notification.params}))
        return
    detail = getattr(event, "text", None) or getattr(event, "status", None) or ""
    _log(f"[{type(event).__name__}] {detail}")


def _cmd_serve_http(args: argparse.Namespace) -> int:
    """启动本地 http 宿主（ADR-0022）：assert_localhost_only 拒绝非本机绑定。

    失败先返回非零码、不拉 uvicorn（`--host 0.0.0.0` 与未知 serve_command 都走这条路）。
    依赖一个可用的 [model] 配置（与 exec 同一入口），否则拒绝启动避免"宿主已开但一调就 401"。
    """
    if getattr(args, "serve_command", None) != "http":
        _log(f"未知 serve 子命令：{getattr(args, 'serve_command', None)!r}")
        return 2
    try:
        assert_localhost_only(args.host)
    except ValueError as exc:
        _log(f"错误：{exc}")
        return 2
    snapshot = load_config(project_root=Path(args.cwd).expanduser().resolve())
    spec = model_spec_from_config(snapshot.data)
    model = create_model(spec)
    cwd = str(Path(args.cwd).expanduser().resolve())

    def _factory(thread_id: str, mode: PermissionMode):  # noqa: ANN001 - Engine 类型已知但循环依赖
        return build_engine(model=model, cwd=cwd, mode=mode, thread_id=thread_id)

    ui_dist = Path(args.ui_dist) if args.ui_dist else Path("ui/dist")
    # 本地 host 代表一个工作区：起服务时就把 --cwd 登记为默认（路径单点解析在
    # workspaces），前端建会话/列文件不传 workspace_id 时落到它，避免瞎造 "ws-local" 幽灵 id。
    default_workspace_id = ensure_workspace_for_root(Path(cwd))
    app = create_app(
        create_engine=_factory,
        ui_dist=ui_dist if ui_dist.is_dir() else None,
        default_workspace_id=default_workspace_id,
    )
    try:
        run_server(app, host=args.host, port=args.port)
    finally:
        asyncio.run(model.aclose())  # B-83：服务退出时收口 HTTP 客户端
    return 0


def _cmd_serve_stdio(args: argparse.Namespace) -> int:
    """启动本机 stdio NDJSON sidecar 宿主（桌面壳拉起，ADR-0006/0024）。

    sidecar 以管道方式连本进程的 stdin/stdout：stdin 接 `connect_read_pipe`，stdout 只写
    协议帧（日志走 stderr，B-87）。方法表与 `serve http` 同源（都经 AppServer.build_dispatcher），
    不为桌面开私有端点。需一个可用 `[model]` 配置（与 exec/http 同入口）才能跑 run。
    """
    snapshot = load_config(project_root=Path(args.cwd).expanduser().resolve())
    spec = model_spec_from_config(snapshot.data)
    model = create_model(spec)
    cwd = str(Path(args.cwd).expanduser().resolve())

    def _factory(thread_id: str, mode: PermissionMode):  # noqa: ANN001 - Engine 类型已知但循环依赖
        return build_engine(model=model, cwd=cwd, mode=mode, thread_id=thread_id)

    server = AppServer(
        create_engine=_factory, default_workspace_id=ensure_workspace_for_root(Path(cwd))
    )

    async def _drive() -> None:
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        # sidecar 以管道连 stdin；控制台直连不支持（非本机拉起场景）。
        await asyncio.get_running_loop().connect_read_pipe(lambda: protocol, sys.stdin.buffer)
        await serve_stdio(server, reader=reader, write=write_line(sys.stdout))

    try:
        asyncio.run(_drive())
    finally:
        asyncio.run(model.aclose())  # B-83：退出时收口 HTTP 客户端
    return 0
