"""Small operator entry; delegates execution and upload to the checked production launchers."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]

def config():
    return json.loads((ROOT/'deploy/host.json').read_text())

def execute(script,args):
    os.execv('/usr/bin/python3',['/usr/bin/python3','-I','-B',str(ROOT/'deploy'/script),*args])

def main(args=None):
    args=list(sys.argv[1:] if args is None else args)
    cmd=args.pop(0) if args else 'chat'
    if cmd=='chat':return execute('launcher_v1.py',['--visible-key','chat',*args])
    if cmd=='upload':
        if args:raise SystemExit('用法：agent upload（在支持 ZMODEM 的 FinalShell 终端中选择 PDF）')
        return execute('terminal_paper_upload.py',['upload'])
    if cmd=='papers':return execute('launcher_v1.py',['paper-list'])
    if cmd=='import':
        inbox=Path(config()['paper_staging'])/'inbox'
        if len(args)>1:raise SystemExit('用法：agent import 或 agent import "论文.pdf"')
        if args:
            name=args[0]
            if Path(name).name!=name or name in ('.','..') or Path(name).suffix.lower()!='.pdf':raise SystemExit('请只填写 inbox 中的 PDF 文件名，不要填写路径。')
            files=[inbox/name]
        else:files=sorted(p for p in inbox.iterdir() if p.suffix.lower()=='.pdf')
        if not files:print('inbox 暂无 PDF。请先用文件面板或 scp 上传。');return 0
        if len(files)>30:raise SystemExit('一次最多登记 30 篇，请指定文件名分批登记。')
        failed=0
        for path in files:
            failed+=subprocess.call(['/usr/bin/python3','-I','-B',str(ROOT/'deploy/paper_transfer.py'),'import',str(path)])!=0
        return 1 if failed else 0
    if cmd in ('reports','where'):
        if args:raise SystemExit('用法：agent '+cmd)
        h=config();c=json.loads(Path(h['research_config']).read_text());runs=Path(c['workspace'])/'research_runs'
        if cmd=='where':
            for title,path in [('生产代码',ROOT),('报告入口',ROOT/'reports'),('报告实际保存',runs),('论文库',c['paper_root']),('待登记 PDF',ROOT/'inbox'),('用户指南',ROOT/'docs/Quant-Agent-ver1.0-用户指南.pdf')]:print(f'{title}：{path}')
            return 0
        rows=[]
        roots=[runs,*(Path(p)/'research_runs' for p in c.get('legacy_workspaces',()))]
        for m in (m for root in roots for m in root.glob('*/*/manifest.json')):
            try:
                data=json.loads(m.read_text());report=m.parent/'reports/report.html'
                if data.get('final_report_ready') and data.get('research_status')=='COMPLETED' and report.is_file():rows.append((m.parent.parent.name+'/'+m.parent.name,data.get('factor_name',''),report))
            except (OSError,ValueError):continue
        for _,name,p in sorted(rows,reverse=True)[:10]:print(f'{name}\n{p}\n')
        if not rows:print('暂无已完成 Train / Validation / 2026 Test 的正式报告。')
        return 0
    if cmd in ('help','--help','-h'):
        print('agent            开始聊天（Key 可见核对，回车清屏）\nagent upload     FinalShell 弹窗选择 PDF\nagent import     登记 inbox 中的 PDF\nagent papers     查看论文库\nagent reports    查看最近完成的报告\nagent where      查看保存路径\n聊天中 /exit 退出；命令请在服务器 shell 中输入。')
        return 0
    raise SystemExit('未知命令。输入 agent help 查看用法。')

if __name__=='__main__':raise SystemExit(main())
