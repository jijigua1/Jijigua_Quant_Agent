# 安全复现与验证

## 四个复现层次

| 层次 | 输入 | 公开仓库是否提供 | 能证明什么 |
|---|---|---|---|
| 完全离线工程 | 固定随机种子合成行情、原创样例文本 | 是 | 程序、权限分支、数值及报告合同 |
| 模型协议 | 用户自己的官方DeepSeek Key | 否 | 特定模型/版本/输入下的实际调用 |
| 真实行情研究 | 用户合法数据及受审发布合同 | 否 | 数据口径下的探索性统计 |
| 独立Test | 独立权限服务、批准、冻结定义与次数账本 | 否 | 获准范围内的受控评估，不自动等于盲测 |

## 环境与安装

先按README创建Python3.11/3.12独立venv，安装core/research锁文件与项目。PDF场景再按许可证决定安装`requirements-paper.lock`。不要把真实Key写进`.env.example`。`pip install -e .`只安装代码，不创建数据用户或连接任何服务器。

## 最小离线运行

```bash
python -m research_agent --state-dir demo_output/mock demo
python examples/offline_paper.py --output demo_output/paper_run_01
python examples/offline_research.py --output demo_output/factor_run_01
```

演示复用`tests/v1beta_fixtures.py`的固定随机种子市场及受控发布fixture，实际执行可信研究Tool后端；不是自然语言LLM验收。它不连接broker，因此Test保持未评价。生成的合成2026文件只用于fixture工程检查，不得宣传为真实市场Test或OS物理隔离。

成功后标准输出给出真实PKL与HTML路径，`demo_result.json`保留对应结果。报告run中应有`data/`、`figures/`、`reports/`、`code/`、`manifest.json`。至少核对PKL、因子定义、日度评价、`metric_system.json`和`report_consistency.json`。输出已存在则停止，不清理未知目录。

## 独立复算

```bash
python tools/numcheck_metrics.py PATH_TO_RUN
python tools/numcheck_study.py PATH_TO_RUN independent_values.json --formula reversal5
```

这里的`reversal5`仅适合本例五日反转；其他研究必须选择与冻结定义完全相同的受审公式（工具另支持alpha12/cmi21/gh52），不能随意套用。数值复算工具是操作者离线脚本，读取自己刚生成的受信PKL及合成发布，不能对下载的未知pickle使用；它会写入指定的独立结果JSON，不修改研究原件。`numcheck_metrics.py`不导入主评价函数，独立重算日度汇总、HAC、分组单调性及热力图。因子数值需要独立公式或手算基准，不能以文件SHA相同证明公式正确。

## 回归和发布门禁

```bash
python -m pytest -q -p no:cacheprovider
python tools/release_audit.py
python tools/release_audit.py --history
```

第一条全量回归可能包含已记录的遗留失败，真实结果见TEST_RESULTS。`--history`只在本地公开Git仓库初始化后有意义；无提交要记录0个，而不是宣称旧内部历史安全。新增Git提交后必须重新扫。默认CI不执行真实API、数据发布、sudo或root脚本。

所有本次执行证据见[测试报告](../release/TEST_RESULTS.md)。命令在未被实际运行的平台只能称安装说明或待CI验证，不能称已真机验收。
