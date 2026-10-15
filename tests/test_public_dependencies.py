import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('dependency_audit',Path(__file__).parents[1]/'tools/dependency_audit.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

def test_parse_only_exact_pins():
    assert mod.pins('numpy==1.26.4\ncolorama==0.4.6; platform_system == "Windows"\nfoo>=1')==[('numpy','1.26.4'),('colorama','0.4.6')]

def test_advisory_and_wrong_response_are_not_reported_safe():
    payload={'queries':[{'package':{'ecosystem':'PyPI','name':'example'},'version':'1.0'}]}
    assert mod.check(payload,lambda x:{'results':[{'vulns':[{'id':'TEST-ONLY'}]}]})['status']=='BLOCKED'
    with pytest.raises(ValueError):mod.check(payload,lambda x:{'results':[]})

def test_empty_matching_results_are_a_pass():
    payload={'queries':[{'package':{'ecosystem':'PyPI','name':'example'},'version':'1.0'}]}
    assert mod.check(payload,lambda x:{'results':[{}]})['status']=='PASS'
