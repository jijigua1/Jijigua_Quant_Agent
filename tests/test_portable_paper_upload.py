"""Input boundaries for the SSH byte protocol and shell-free client."""
import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import pytest

ROOT=Path(__file__).parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
client=load('portable_client',ROOT/'client/quant_paper.py')
server=load('portable_server',ROOT/'deploy/paper_transfer.py')
gate=load('portable_gate',ROOT/'deploy/paper_ssh_gate.py')

def frame(body=b'%PDF-1.4\npublic protocol fixture\n%%EOF',name='论文 $();&\'[%].pdf',**extra):
    meta={'protocol':1,'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest(),
          'name_b64':base64.urlsafe_b64encode(name.encode()).decode().rstrip('=')}
    meta.update(extra)
    return (json.dumps(meta)+'\n').encode()+body

@pytest.fixture(autouse=True)
def uid(monkeypatch,tmp_path):
    # Installed code is root-owned, while non-root test uploads belong to the
    # test worker. Simulate the receiving identity from its inbox, not the cwd.
    monkeypatch.setattr(server.check_received.__globals__['os'],'geteuid',lambda:tmp_path.stat().st_uid,raising=False)

def test_filename_characters_are_data_and_exact_hash_survives(tmp_path):
    path,sha=server.receive(io.BytesIO(frame()),tmp_path)
    assert path.name=='论文 $();&\'[%].pdf'
    assert hashlib.sha256(path.read_bytes()).hexdigest()==sha

@pytest.mark.parametrize('name',['../escape.pdf','/escape.pdf','back\\escape.pdf','bad\nname.pdf','word.docx'])
def test_remote_path_traversal_and_non_pdf_names_never_become_paths(tmp_path,name):
    with pytest.raises(SystemExit,match='UPLOAD_NAME_INVALID'):server.receive(io.BytesIO(frame(name=name)),tmp_path)
    assert not list(tmp_path.iterdir())

@pytest.mark.parametrize('changes',[{'bytes':0},{'bytes':True},{'bytes':50*1024*1024+1},{'sha256':'0'*64},{'protocol':2}])
def test_invalid_metadata_rejected(tmp_path,changes):
    with pytest.raises(SystemExit):server.receive(io.BytesIO(frame(**changes)),tmp_path)

@pytest.mark.parametrize('kind',['truncated','extra','bad_pdf'])
def test_disconnect_excess_bytes_and_fake_pdf_do_not_import(tmp_path,kind):
    data=frame()
    if kind=='truncated':data=data[:-2]
    if kind=='extra':data+=b'not allowed'
    if kind=='bad_pdf':data=frame(body=b'not pdf')
    with pytest.raises(SystemExit):server.receive(io.BytesIO(data),tmp_path)

@pytest.mark.parametrize('field,value',[('host','host;touch nope'),('host','-oProxyCommand=x'),('user','root;id'),
                                     ('server_command','/tmp/x;id'),('server_command','/tmp/../x')])
def test_ssh_destination_and_remote_command_injection_rejected(field,value):
    config={'host':'gpushare',field:value}
    with pytest.raises(ValueError):client.connection(SimpleNamespace(),config)

def test_identity_path_is_an_argv_item_not_shell_code(monkeypatch):
    monkeypatch.setattr(client.shutil,'which',lambda _: 'ssh')
    key='C:/Users/Operator/.ssh/key $();&'
    argv,command=client.connection(SimpleNamespace(),{'host':'gpushare','identity':key})
    assert argv[argv.index('-i')+1]==str(Path(key).expanduser())
    assert command=='/usr/local/bin/quant-paper' and argv[-1]=='gpushare'

def test_no_secret_keys_accepted_in_client_config():
    with pytest.raises(ValueError,match='CONFIG_KEYS'):client.connection(SimpleNamespace(),{'host':'gpushare','api_key':'never-store'})

def test_local_snapshot_preserves_bytes_when_original_changes_later(tmp_path):
    p=tmp_path/'file.pdf';p.write_bytes(b'%PDF-1.4\nvalid magic')
    snapshot,head=client.spool_pdf(p)
    try:
        p.write_bytes(b'changed')
        assert hashlib.sha256(snapshot.read()).hexdigest()==head['sha256']
    finally:snapshot.close()

def test_inbox_import_has_no_arbitrary_server_read(tmp_path):
    for name in ['/etc/passwd',str(tmp_path/'elsewhere.pdf')]:
        data=io.BytesIO((json.dumps({'protocol':1,'path':name})+'\n').encode())
        with pytest.raises(SystemExit,match='OUTSIDE_CONTROLLED_INBOX'):server.inbox_source(data,tmp_path,tmp_path)

@pytest.mark.parametrize('command',['','bash','sftp','/usr/local/bin/quant-paper receive; id',
                                  '/usr/local/bin/quant-paper import-stream','/tmp/quant-paper receive'])
def test_forced_ssh_gate_rejects_shell_sftp_and_server_read(command):
    with pytest.raises(SystemExit,match='COMMAND_DENIED'):gate.select(command)

def test_forced_gate_accepts_only_two_exact_constant_argv():
    for action in ('receive','list'):
        assert gate.select('/usr/local/bin/quant-paper '+action)==['/usr/bin/python3','-I','-B',str(gate.LAUNCHER),'paper-transfer',action]
