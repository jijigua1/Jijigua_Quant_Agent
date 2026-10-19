"""Local offline CLI. No deployment, shell executor, arbitrary plugin or Key flags."""

import argparse
import getpass
from dataclasses import asdict
import re
from pathlib import Path
import sys

from .app import build, build_chat
from .contracts import ContractError, canonical
from .llm import MemorySecrets, ModelError
from .security import Budget, Denied, require_non_root
from .store import LedgerError, StateConflict, TaskStore

DEMO_GOAL = "查询模拟量价数据，计算模拟因子指标，判断是否需要进一步实验，并生成模拟研究摘要。"


def prompt_credential(visible=False):
    if visible and not sys.stdin.isatty():
        raise Denied('VISIBLE_KEY_REQUIRES_TERMINAL')
    while True:
        raw = input('DeepSeek Key (visible; paste key only): ') if visible else getpass.getpass('DeepSeek Key (not echoed): ')
        key = raw.strip()
        if visible:
            input('请在本机核对上面的 Key，然后按 Enter 清屏并继续：')
            # Clear both the screen and terminal scrollback before diagnostics.
            print('\x1b[2J\x1b[3J\x1b[H', end='', flush=True)
            try:
                import readline
                readline.clear_history()
            except ImportError:
                pass
        if not re.fullmatch(r'sk-[A-Za-z0-9_-]{16,253}', key):
            print('Key 格式检查失败：请仅输入 sk- 开头的完整 Key，不要带 Bearer、引号、内部空格或换行。')
            continue
        print(f'Key 已读取：{len(key)} 个字符；前缀、字符及空白检查通过。' +
              (' 已去掉首尾空白。' if key != raw else ''), flush=True)
        return key


def check_connection(provider):
    """One small request through the same adapter and cumulative budget."""
    from dataclasses import replace
    from .llm import Message, ModelRequest, Role
    from .providers.deepseek import DeepSeekAdapter
    diagnostic = DeepSeekAdapter(replace(provider.config, max_output_tokens=32),
        provider.secrets, provider.transport, provider.redactor)
    print('正在验证最小 DeepSeek 请求（同一凭证、接口及累计预算）…', flush=True)
    try:
        response = diagnostic.complete(ModelRequest((Message(Role.USER, 'Reply with the single word OK.'),)))
    except ModelError as exc:
        print(canonical({'connection_check': 'FAILED', 'code': exc.code,
                         'http_status': exc.http_status, 'provider_detail': exc.provider_detail}), flush=True)
        return False
    print(canonical({'connection_check': 'PASSED', 'model': response.actual_model,
                     'reply': provider.redactor.clean(response.content)[:100]}), flush=True)
    return True


def parser():
    p = argparse.ArgumentParser(prog="qra", description="Research Agent: offline Mock or trusted development profile")
    p.add_argument("--state-dir", type=Path, default=Path.cwd() / ".qra-state")
    p.add_argument("--provider", choices=["mock", "mock_alt", "deepseek"], default="mock")
    p.add_argument("--profile", choices=["offline", "development"], default="offline")
    from .quant import QUANT_SKILLS
    p.add_argument("--skill", choices=["mock_research", "data_query", *QUANT_SKILLS], default="mock_research")
    p.add_argument("--resources-manifest", type=Path)
    p.add_argument('--research-config',type=Path,help='Trusted operator configuration for reviewed quant tools and artifacts')
    p.add_argument("--prompt-key", action="store_true", help="Operator-only hidden prompt; never a Key command argument")
    p.add_argument('--visible-key', action='store_true', help='Opt-in local terminal echo, then clear before continuing')
    p.add_argument('--check-connection', action='store_true', help='One budgeted minimal API request before chat')
    commands = p.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("goal")
    create.add_argument("--max-iterations", type=int, default=4)
    create.add_argument("--max-model-calls", type=int, default=8)
    create.add_argument("--max-tool-calls", type=int, default=6)
    commands.add_parser("ask").add_argument("goal")
    run = commands.add_parser("run")
    run.add_argument("task_id")
    run.add_argument("--max-steps", type=int)
    for name in ("status", "logs", "result"):
        commands.add_parser(name).add_argument("task_id")
    commands.add_parser("demo")
    commands.add_parser("chat").add_argument("--resume", metavar="SESSION_ID")
    for name in ("session", "history", "session_tasks"):
        commands.add_parser(name).add_argument("session_id")
    imp = commands.add_parser("paper-import", help="register a PDF handed over by the trusted launcher (fd:N) or a test path")
    imp.add_argument("incoming")
    imp.add_argument("name_b64")
    imp.add_argument("sha256", nargs="?", default="")
    commands.add_parser("paper-list")
    return p


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and (stream.encoding or "").lower().replace("-", "") != "utf8":
            stream.reconfigure(encoding="utf-8")
    args = parser().parse_args(argv)
    try:
        require_non_root()
        if (args.visible_key or args.check_connection) and not (args.prompt_key and args.provider == 'deepseek'
                and args.profile == 'development' and args.command == 'chat'):
            raise Denied('KEY_DIAGNOSTICS_REQUIRE_PROMPTED_LIVE_CHAT')
        if args.command in {"paper-import", "paper-list"}:
            import base64
            from .contracts import parse_json
            from .paper_library import PaperLibrary
            config = parse_json(args.research_config.read_text(encoding="utf-8"))
            library = PaperLibrary(config["paper_root"])
            if args.command == "paper-list":
                print(canonical([library.public(r) | {"paper_id": r["paper_id"]} for r in library.entries()]))
                return 0
            name = base64.urlsafe_b64decode(args.name_b64.encode() + b"=" * (-len(args.name_b64) % 4)).decode("utf-8")
            incoming = Path(args.incoming)
            if args.incoming.startswith("fd:"):
                # The launcher opened the root-staged upload (no links, size checked) and passed only this descriptor.
                incoming = library.receive_fd(int(args.incoming[3:]), args.sha256)
            entry = library.import_pdf(incoming, name)
            out = {k: entry[k] for k in ("paper_id", "name", "version", "title", "pages", "bytes", "uploaded_at", "duplicate")}
            # protocol 2 (2026-10-15): a re-upload refreshes last_uploaded_at; clients warn when an older server omits this
            out.update(protocol="paper-import/2", last_uploaded_at=entry.get("last_uploaded_at") or entry["uploaded_at"])
            print(canonical(out))
            return 0
        if args.command in {"session", "history", "session_tasks"}:
            store = TaskStore(args.state_dir)
            if args.command == "session":
                result = store.session(args.session_id)
            else:
                turns = store.session_turns(args.session_id)
                result = turns if args.command == "history" else [{k: x[k] for k in
                    ("route_task_id", "research_task_id", "status", "error")} for x in turns]
            print(canonical(result))
            return 0
        if args.command in {"status", "logs", "result"}:
            store = TaskStore(args.state_dir)
            state = store.load(args.task_id)
            result = store.events(args.task_id) if args.command == "logs" else state.result if args.command == "result" else {
                k: asdict(state)[k] for k in ("id", "session_id", "goal", "status", "stage", "provider", "model", "skill_id", "execution_mode", "usage", "counters", "result", "error")}
        else:
            secrets = None
            if args.prompt_key:
                if args.provider != "deepseek" or args.profile != "development":
                    raise Denied("KEY_PROMPT_REQUIRES_LIVE_PROFILE")
                secrets = MemorySecrets({"env:QRA_DEEPSEEK_API_KEY": prompt_credential(args.visible_key)})
            if args.command == "chat" and args.provider == "deepseek":
                from .terminal import chat_loop
                app = build_chat(args.state_dir, args.provider, profile=args.profile,
                                 resources_manifest=args.resources_manifest, secrets=secrets, session_id=args.resume,research_config=args.research_config)
                if args.check_connection and not check_connection(app.provider):
                    return 2
                chat_loop(app)
                return 0
            app = build(args.state_dir, args.provider, profile=args.profile, skill_id=args.skill,
                        resources_manifest=args.resources_manifest, secrets=secrets,research_config=args.research_config)
            if args.command == "create":
                state = app.create(args.goal, Budget(args.max_iterations, args.max_model_calls, args.max_tool_calls))
                result = {"task_id": state.id, "status": state.status, "execution_mode": state.execution_mode}
            elif args.command == "run":
                state = app.run(args.task_id, max_steps=args.max_steps)
                result = {"task_id": state.id, "status": state.status, "counters": state.counters, "result": state.result, "error": state.error}
            elif args.command in {"demo", "ask"}:
                state = app.run(app.create(DEMO_GOAL if args.command == "demo" else args.goal).id)
                result = {"task_id": state.id, "status": state.status, "mode": state.result.get("mode") if state.result else None,
                          "execution_mode": state.execution_mode, "usage": state.usage, "counters": state.counters,
                          "result": state.result, "error": state.error}
            else:
                print("离线 Mock 对话：固定模拟量价研究，输入 /exit 退出。不是 DeepSeek 或真实市场研究。" if args.provider != "deepseek" else
                      "DeepSeek 研究任务对话：输入自然语言任务，/exit 退出。当前 Skill: " + args.skill)
                print("session_id=" + app.session_id)
                while True:
                    try:
                        goal = input("research> ").strip()
                    except EOFError:
                        break
                    if goal == "/exit":
                        break
                    if not goal:
                        continue
                    state = app.run(app.create(goal).id)
                    print(canonical({"task_id": state.id, "status": state.status, "execution_mode": state.execution_mode,
                                     "result": state.result, "usage": state.usage, "error": state.error}))
                return 0
        print(canonical(result))
        if args.command in {"run", "ask", "demo"} and state.status not in {"COMPLETED", "PAUSED"}:
            return 2
        return 0
    except (Denied, ContractError, LedgerError, StateConflict, ModelError) as exc:
        print(canonical({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
