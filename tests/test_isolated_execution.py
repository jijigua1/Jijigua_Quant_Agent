"""Synthetic worker tests; Linux sandbox tests explicitly skip on Windows/root."""
import hashlib
import os
import sys

import numpy as np
import pandas as pd
import pytest

from paper_agent.isolated_execution import execute, IsolationError


def run(source, **kw):
    panel = pd.DataFrame(np.arange(20, dtype=float).reshape(10, 2),
                         index=pd.date_range("2024-01-01", periods=10), columns=["A", "B"])
    return execute(source, {"close": panel}, source_sha256=hashlib.sha256(source.encode()).hexdigest(), **kw)


def test_unsupported_platform_fails_closed():
    if sys.platform == "linux" and os.geteuid() != 0:
        pytest.skip("supported host")
    with pytest.raises(IsolationError, match="NONROOT_LINUX_REQUIRED"):
        run("def compute(panels): return panels['close']")


linux = pytest.mark.skipif(sys.platform != "linux" or getattr(os, "geteuid", lambda: 0)() == 0,
                           reason="requires real non-root Linux seccomp")


@linux
def test_vector_and_literal_code_can_run():
    source = "import numpy as np\nimport pandas as pd\ndef compute(panels):\n return panels['close'].rolling(3, min_periods=3).mean()\n"
    result = run(source)
    assert result.iloc[:2].isna().all().all()
    assert result.iloc[-1].tolist() == [16., 17.]


@linux
@pytest.mark.parametrize("payload", [
    "open('/etc/passwd').read()",
    "open('/tmp/i5_should_never_exist', 'w').write('bad')",
    "__import__('socket').socket()",
    "__import__('os').fork()",
    "__import__('os').system('true')",
    "__import__('os').kill(__import__('os').getppid(), 0)",
    "__import__('ctypes').CDLL(None).syscall(257, -100, b'/etc/passwd', 0)",
])
def test_forbidden_operations_are_killed(payload):
    with pytest.raises(IsolationError, match="WORKER_FAILED"):
        run(f"def compute(panels):\n {payload}\n return panels['close']\n")


@linux
def test_key_not_inherited(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic-canary-not-a-key")
    result = run("import os\ndef compute(panels):\n assert 'DEEPSEEK_API_KEY' not in os.environ\n return panels['close']\n")
    assert result.iloc[-1, -1] == 19


@linux
def test_loop_is_bounded():
    with pytest.raises(IsolationError, match="EXECUTION_TIMEOUT|WORKER_FAILED"):
        run("def compute(panels):\n while True: pass\n", timeout=2)


@linux
def test_source_identity():
    with pytest.raises(IsolationError, match="SOURCE_SHA_MISMATCH"):
        execute("def compute(panels): return panels['close']", {}, source_sha256="0"*64)


@linux
def test_stdout_cannot_be_arbitrary_text():
    with pytest.raises(IsolationError, match="INVALID_WORKER_OUTPUT"):
        run("def compute(panels):\n print('fake receipt')\n return panels['close']\n")


@linux
@pytest.mark.parametrize("source,expected_last", [
    ("def compute(panels):\n x=panels['close']\n return x.where(x>10, -x)\n", [18., 19.]),
    ("def compute(panels):\n x=panels['close']\n return x.rank(axis=1, pct=True)\n", [.5, 1.]),
    ("def compute(panels):\n x=panels['close']\n return x-x.ewm(span=3, adjust=False).mean()\n", [1.99609375, 1.99609375]),
])
def test_general_python_algorithms_without_operator_menu(source, expected_last):
    result = run(source)
    np.testing.assert_allclose(result.iloc[-1].to_numpy(), expected_last, rtol=1e-12)


@linux
def test_calendar_grouping_with_per_security_missing_counts():
    dates = pd.to_datetime(["2023-12-28", "2023-12-29", "2024-01-02", "2024-01-03"])
    x = pd.DataFrame([[2., 4.], [6., np.nan], [100., 200.], [300., 400.]], index=dates, columns=["A", "B"])
    source = '''import numpy as np
import pandas as pd
def compute(panels):
 x=panels['close']
 out=pd.DataFrame(np.nan,index=x.index,columns=x.columns)
 for t,date in enumerate(x.index):
  previous=x.iloc[:t+1].loc[x.index[:t+1].year==date.year-1]
  count=previous.notna().sum()
  out.iloc[t]=previous.sum()/count.replace(0,np.nan)
 return out
'''
    out = execute(source, {"close": x}, source_sha256=hashlib.sha256(source.encode()).hexdigest())
    assert out.iloc[:2].isna().all().all()
    assert out.iloc[2:].to_numpy().tolist() == [[4., 4.], [4., 4.]]


@linux
def test_untrusted_npy_header_cannot_allocate_in_parent():
    source = "import os\nimport io\nimport numpy as np\ndef compute(panels):\n b=io.BytesIO()\n np.lib.format.write_array_header_1_0(b, {'descr':'<f8','fortran_order':False,'shape':(2**40,2**40)})\n os.write(1,b.getvalue())\n os._exit(0)\n"
    with pytest.raises(IsolationError, match="INVALID_WORKER_OUTPUT"):
        run(source)


@linux
def test_inherited_resource_limit_is_never_raised(monkeypatch):
    import resource
    import subprocess
    original = subprocess.run
    def launch(*args, **kwargs):
        kwargs['preexec_fn'] = lambda: resource.setrlimit(resource.RLIMIT_FSIZE, (1024**2, 1024**2))
        return original(*args, **kwargs)
    monkeypatch.setattr(subprocess, 'run', launch)
    result = run("def compute(panels): return panels['close']")
    assert result.iloc[-1, -1] == 19


@linux
def test_pandas_groupby_annual_mean_runs_under_unchanged_seccomp():
    dates = pd.to_datetime(["2023-12-28", "2023-12-29", "2024-01-02", "2024-01-03"])
    panel = pd.DataFrame([[2., 4.], [6., np.nan], [100., 200.], [300., 400.]], index=dates, columns=["A", "B"])
    source = """import numpy as np
import pandas as pd
def compute(panels):
 x=panels['close']
 years=pd.Series(x.index.year,index=x.index)
 annual=x.groupby(years).mean()
 out=pd.DataFrame(np.nan,index=x.index,columns=x.columns)
 for year in annual.index:
  out.loc[(years==year+1).values,:]=annual.loc[year,:].values
 return out
"""
    out=execute(source, {'close':panel}, source_sha256=hashlib.sha256(source.encode()).hexdigest())
    assert out.iloc[:2].isna().all().all()
    assert out.iloc[2:].to_numpy().tolist()==[[4.,4.],[4.,4.]]
