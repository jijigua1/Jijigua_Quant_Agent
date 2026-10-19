"""Operator entry wiring; no HTTP, real key, library or production command is used."""
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest

def load(name,file,monkeypatch):
    for unix in ('pwd','grp'):
        if sys.platform=='win32':monkeypatch.setitem(sys.modules,unix,SimpleNamespace(getpwnam=lambda _: None,getgrnam=lambda _: None))
    spec=importlib.util.spec_from_file_location(name,Path(__file__).parents[1]/'deploy'/file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def test_global_paper_wrapper_forwards_to_sibling_agent():
    wrapper=(Path(__file__).parents[1]/'deploy/quant-paper').read_text(encoding='utf-8')
    wrapper='\n'.join(line for line in wrapper.splitlines() if not line.lstrip().startswith('#'))
    assert '${0%/*}/quant-agent' in wrapper
    assert 'paper-upload' in wrapper and 'paper-list' in wrapper
    assert '/v1beta' not in wrapper and '/v1rc' not in wrapper and 'host.json' not in wrapper

def test_uploader_and_importer_share_the_same_deployment(tmp_path,monkeypatch):
    u=load('upload_adapter','terminal_paper_upload.py',monkeypatch)
    root=tmp_path/'candidate';deploy=root/'deploy';deploy.mkdir(parents=True)
    staging=tmp_path/'private';staging.mkdir(mode=0o700)
    host=deploy/'host.json'
    config=dict(root=str(root),runner=str(deploy/'run_v1.py'),research_config=str(root/'config/research.json'),paper_staging=str(staging))
    host.write_text(json.dumps(config))
    monkeypatch.setattr(u.os,'geteuid',lambda:0,raising=False)
    if sys.platform!='win32' and host.lstat().st_uid!=0:
        # The suite runs as quantagent. Its real temporary host is correctly
        # refused; only the following unit fixture simulates operator metadata.
        with pytest.raises(SystemExit,match='root 管理'):u.private_staging(host)
    original=Path.lstat
    def controlled(p,*a,**k):
        if p in (host,staging):
            return SimpleNamespace(st_mode=0o40700 if p==staging else 0o100600,st_uid=0)
        return original(p,*a,**k)
    monkeypatch.setattr(Path,'lstat',controlled)
    assert u.private_staging(host)==staging
    config['research_config']=str(tmp_path/'old-beta/config/research.json')
    host.write_text(json.dumps(config))
    with pytest.raises(SystemExit,match='同一部署'):u.private_staging(host)

def test_chat_budget_is_explicit_and_shared_across_sessions(tmp_path,monkeypatch):
    launcher=load('final_launcher','launcher_v1.py',monkeypatch)
    with pytest.raises(SystemExit,match='budget'):launcher.budget_environment({})
    h={'api_budget':{'db':str(tmp_path/'operator_budget.sqlite'),'campaign':'approved-synthetic-test'}}
    one=launcher.budget_environment(h);two=launcher.budget_environment(h)
    assert one==two and one['QRA_API_BUDGET_CAMPAIGN']=='approved-synthetic-test'
    assert not (tmp_path/'operator_budget.sqlite').exists() # never creates a campaign
    monkeypatch.setenv('QRA_API_BUDGET_CAMPAIGN','user-environment-bypass')
    assert launcher.budget_environment(h)==one


@pytest.mark.parametrize('rolling',[False,True])
def test_visible_key_entry_drops_identity_before_prompt_and_never_exports_secret(tmp_path,monkeypatch,rolling):
    if rolling and sys.platform == 'win32':
        pytest.skip('Unix fork/socketpair boundary requires Linux; Windows socketpair uses TCP')
    launcher=load('visible_launcher','launcher_v1.py',monkeypatch)
    h=dict(root=str(tmp_path),agent_python='/python',runner='/runner',state_dir='/state',
           resources_manifest='/resources',research_config='/research',agent_home=str(tmp_path),
           api_budget=dict(db=str(tmp_path/'budget.sqlite'),campaign='existing-campaign'))
    if rolling:h['rolling']=dict(receipt_dir='/receipts')
    monkeypatch.setattr(launcher,'host_config',lambda:h)
    monkeypatch.setattr(launcher.pwd,'getpwnam',lambda _:SimpleNamespace(pw_uid=1234))
    monkeypatch.setattr(launcher.os,'geteuid',lambda:0,raising=False)
    monkeypatch.setattr(launcher.os,'umask',lambda _:None)
    monkeypatch.setattr(launcher.os,'chdir',lambda _:None)
    monkeypatch.setattr(launcher.sys,'argv',['quant-agent','--visible-key','chat','--resume','session123'])
    monkeypatch.setenv('QRA_DEEPSEEK_API_KEY','synthetic-do-not-inherit')
    monkeypatch.setattr(launcher.getpass,'getpass',lambda *_:pytest.fail('root must not prompt'))
    order=[];monkeypatch.setattr(launcher,'drop',lambda *_:order.append('dropped'))
    sockets=[]
    if rolling:
        original=launcher.socket.socketpair
        def pair():
            sockets.extend(original());return tuple(sockets)
        monkeypatch.setattr(launcher.socket,'socketpair',pair)
        monkeypatch.setattr(launcher.os,'fork',lambda:0,raising=False)
    class Replaced(Exception):pass
    def execute(path,args,env):
        assert order==['dropped']
        assert args[-6:]==['--prompt-key','--visible-key','--check-connection','chat','--resume','session123']
        assert 'QRA_DEEPSEEK_API_KEY' not in env
        assert env['QRA_API_BUDGET_CAMPAIGN']=='existing-campaign'
        assert ('QRA_ROLLING_FD' in env)==rolling
        raise Replaced
    monkeypatch.setattr(launcher.os,'execve',execute)
    try:
        with pytest.raises(Replaced):launcher.main()
    finally:
        for sock in sockets:sock.close()
