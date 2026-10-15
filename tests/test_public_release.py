"""The public scanner must detect planted credentials without echoing their values."""
import importlib.util
from pathlib import Path

PATH=Path(__file__).parents[1]/'tools/release_audit.py'
SPEC=importlib.util.spec_from_file_location('public_release_audit',PATH)
AUDIT=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)

def test_plant_secrets_and_keep_output_safe():
    key=b'sk-'+b'ExampleSecretValueForTestOnly12345'
    findings=AUDIT.inspect_bytes('example.py',key)
    assert findings and findings[0]['rule']=='api-secret'
    assert key.decode() not in str(findings)

def test_reject_restricted_artifacts():
    assert AUDIT.inspect_bytes('market.pkl',b'not actually pickle')[0]['rule']=='private-or-binary-artifact'

def test_no_secret_in_placeholders():
    assert not AUDIT.inspect_bytes('.env.example',b'QRA_DEEPSEEK_API_KEY=\nHOST=gpu.example.org\n')

def test_only_named_synthetic_report_has_a_larger_explicit_budget():
    sample=b'x'*5_000_001
    assert not AUDIT.inspect_bytes('docs/examples/synthetic_report.html',sample)
    assert AUDIT.inspect_bytes('unexpected.html',sample)==[{'file':'unexpected.html','rule':'large-file'}]

def test_link_is_rejected_before_reading(tmp_path,monkeypatch):
    import os
    original=tmp_path/'original.txt'
    original.write_text('synthetic',encoding='utf-8')
    os.link(original,tmp_path/'linked.txt')
    monkeypatch.setattr(AUDIT,'ROOT',tmp_path)
    result=AUDIT.audit()
    assert result['status']=='FAIL' and all(x['rule']=='linked-file' for x in result['findings'])
