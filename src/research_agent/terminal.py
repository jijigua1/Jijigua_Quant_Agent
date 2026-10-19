"""Readable foreground chat; diagnostics remain separate from natural replies."""
from contextlib import contextmanager
import re
import sys
import threading
import time
import shutil
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

from .contracts import ContractError
from .security import Denied
from .store import LedgerError, StateConflict


def safe_text(text):
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text)

def stamp():return datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%H:%M:%S')

def wrapped(text,width=None):
    width=max(24,width or shutil.get_terminal_size((100,24)).columns)
    lines=[]
    for line in safe_text(text).splitlines():
        # Paths stay intact for copying; terminals perform their own visual wrapping.
        if '/hy-tmp/' in line or '/home/' in line:lines.append(line);continue
        part='';size=0
        for ch in line:
            n=0 if unicodedata.combining(ch) else 2 if unicodedata.east_asian_width(ch) in {'W','F'} else 1
            if size+n>width:lines.append(part);part='';size=0
            part+=ch;size+=n
        lines.append(part)
    return '\n'.join(lines)


class ProgressDisplay:
    """A display heartbeat only; this thread never runs or persists research work."""
    names={'hypothesis_analysis':'研究假设分析','tool_selection':'选择已授权工具','data_quality':'数据质量检查',
        'factor_construction':'因子设计与计算','factor_evaluation':'IC / RankIC 和分组分析','evidence_review':'研究证据诊断',
        'report_export':'报告整理','chart_generation':'图表与成果生成','factor_export':'因子 PKL 导出与验证','factor_diagnostics':'稳定性与指标计算'}
    def __init__(self,labels):
        self.labels=labels;self.active=None;self.start=0;self.stop=threading.Event();self.lock=threading.Lock()
        self.tty=sys.stderr.isatty()
    def __enter__(self):
        if self.tty:
            self.thread=threading.Thread(target=self._heartbeat,daemon=True);self.thread.start()
        return self
    def _line(self):
        item=self.active;label=self.names.get(item['stage'],item['stage']);elapsed=time.monotonic()-self.start
        progress=''
        if item.get('total'):
            n,t=item['completed'],item['total'];progress=f' [{n}/{t} · {n/t:.0%}]'
        return '['+stamp()+'] '+label+progress+f' · {elapsed:.1f}s'
    def _heartbeat(self):
        while not self.stop.wait(1):
            with self.lock:
                if self.active:print('\r\x1b[2K'+self._line(),end='',file=sys.stderr,flush=True)
    def __call__(self,item):
        with self.lock:
            if isinstance(item,str):
                print('['+stamp()+'] '+self.labels.get(item,'正在执行已授权研究工具…'),file=sys.stderr);return
            state=item['status'];label=self.names.get(item['stage'],item['stage'])
            if state=='RUNNING':
                if not self.active or self.active['stage']!=item['stage']:self.start=time.monotonic()
                self.active=item
                if not self.tty:print(f'[{stamp()}] [RUNNING] {label}',file=sys.stderr)
            else:
                self.active=None
                print(('\r\x1b[2K' if self.tty else '')+f'[{stamp()}] [{state}] {label} · {item.get("elapsed_seconds",0):.1f}s',file=sys.stderr,flush=True)
    def __exit__(self,*_):
        self.stop.set()
        if self.tty:self.thread.join(timeout=1);print('\r\x1b[2K',end='',file=sys.stderr)


@contextmanager
def editing():
    saved = None
    try:
        if sys.stdin.isatty() and sys.platform != "win32":
            import termios
            import readline
            saved = termios.tcgetattr(sys.stdin.fileno())
            readline.clear_history()
            readline.set_history_length(50)
            readline.parse_and_bind('"\\C-h": backward-delete-char')
            readline.parse_and_bind('"\\C-?": backward-delete-char')
            readline.parse_and_bind("set enable-bracketed-paste on")
        yield
    finally:
        if saved is not None:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, saved)


def chat_loop(app):
    print("量化研究助手：可以聊天、讨论研究想法或查询已授权数据。/help 查看命令，/exit 退出。")
    print('前台会话已开始 · '+stamp()+' · 会话ID '+str(app.session_id)+'（/session 可再次查看）')
    print('SSH 断线不保证继续；断线后用 quant-agent chat --resume <会话ID> 恢复。Ctrl+C 取消本轮；成果按日期与因子名称保存。')
    print()
    labels = {"list_resources": "正在检查可用数据…", "describe_resource": "正在核验数据描述…",
              "read_data_slice": "正在读取只读样例…",'list_research_resources':'正在核对研究数据…',
              'qrtk_data_quality':'正在检查数据质量…','qrtk_factor_study':'正在计算因子和预测指标…',
              'qrtk_read_study':'正在读取已有实验…','qrtk_diagnose_study':'正在检查研究证据…',
              'qrtk_export_report':'正在查看研究报告…','qrtk_backtest_readiness':'正在核验回测条件…'}
    with editing():
        while True:
            try:
                text = input('['+stamp()+'] 你> ').strip()
            except EOFError:
                print("\n会话已结束。")
                break
            except KeyboardInterrupt:
                print("\n输入已取消。")
                continue
            if not text:
                continue
            if text == "/exit":
                break
            if text == "/help":
                print("/skills 当前能力；/tasks 本会话任务与诊断；/history 最近对话；/session 会话ID；/exit 退出。")
            elif text == "/session":
                print(app.session_id)
            elif text == "/skills":
                for x in app.skills:
                    print(x["id"] + " @ " + x["version"] + "：" + x["summary"])
            elif text in {"/tasks", "/history"}:
                for x in app.store.session_turns(app.session_id):
                    if text == "/history":
                        print("你：" + safe_text(x["user"]) + "\n助手：" + safe_text(x["assistant"]))
                    else:
                        print("对话 " + x["route_task_id"] + " | " + x["status"] +
                              (" | 研究 " + x["research_task_id"] if x["research_task_id"] else "") +
                              (" | " + x["error"]["code"] if x["error"] else ""))
                        if x["research_task_id"]:
                            task = app.store.load(x["research_task_id"])
                            for experiment in task.experiments:
                                print("  实验 " + str(experiment["index"]) + "：" + experiment["tool"] +
                                      " | 证据 " + experiment["result_sha256"][:12])
            elif text.startswith("/"):
                print("未知命令，输入 /help 查看可用命令。")
            else:
                try:
                    with ProgressDisplay(labels) as display:
                        reply = app.turn(text, notify=display)
                    print('\n['+stamp()+'] 助手\n'+wrapped(reply)+'\n')
                except (ContractError, Denied, LedgerError, StateConflict) as exc:
                    print("本次请求未执行：" + safe_text(str(exc)), file=sys.stderr)
