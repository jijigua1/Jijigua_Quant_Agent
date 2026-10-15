> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 3-B1 测试结果

执行日 2026-10-12，Windows 本地 Python 3.12.4、pandas 2.3.3、NumPy 1.26.4；精确 Python 补丁版本和执行源码 SHA 见 manifest.json（原内部附件未公开）。没有 GPUShare Linux 运行、真实行情读取、DeepSeek 调用或服务器部署。

## 可复现命令

在 PowerShell 中执行：

```powershell
python -X utf8 <ARCHIVE_ROOT>\phase3b_backtest\synthetic_acceptance.py --core-root <LOCAL_RESEARCH_ROOT> --phase3a-root <ARCHIVE_ROOT>\phase3a_data
python -X utf8 <LOCAL_RESEARCH_ROOT>\test_backtest_final.py
```

测试程序仅加载经审的本地 `core_backtest` Python 模块并将合成 DataFrame 直接传入 `run_final_backtest`；**不调用** `load_final_data`、`pd.read_pickle` 或 notebook 最后 cell 的主执行分支。生成新证据时需指定尚不存在的 `--output <独立目录>`，程序拒绝覆盖已有目录。

## 结果

| 测试组 | 本轮结果 | 证据 |
|---|---|---|
| 独立手录 oracle | 10 组成功案例的每日现金/股数/市值/NAV、成交价/费及公司行动全部吻合；另 1 组未知缺价按合同失败 | acceptance_tests.txt（原内部附件未公开）、expected.json（原内部附件未公开）、逐案 CSV（原内部附件未公开） |
| 日期/未来函数 | 周五 T 信号最早周一开盘成交；改变最后一日价格不影响先前 NAV 或成交；合成分区边缘只保留成熟标签，Holdout 与越界拒绝 | 同上 |
| 故障注入 | 对执行输出副本注入同日成交、错误股数单位、漏卖出费、NAV 不平衡、公司行动股数错误，5/5 被手录 oracle 检测；并未修改引擎源码 | `test_mutation_detection` |
| 已知准入缺口检测 | 最低佣金 + 卖出税率不能正确相加；拒单事件无委托股数；非整数公司行动股数被外层验收拒绝 | `test_confirmed_fee_and_action_gaps` |
| 本轮专项程序 | 7 个 `unittest` 方法全部 PASS（其中 oracle 含 10 组子案例） | acceptance_tests.txt（原内部附件未公开） |
| GeorgeResearch 原有回归 | 76 项合成检查 PASS，历史 cell 未改 | george_existing_regression.txt（原内部附件未公开） |

有一个预期的合成 Universe EW 警告：停牌缺价案例的次级等权研究基准保留 NaN；独立注入的固定主基准与账户账本不受影响。这不是被静默填零。未出现测试失败项。

## 不能由上述测试推出的结论

真实 Train/Validation 快照未独立发布、Holdout 未实现服务器物理隔离；真实上市/退市、停牌/ST/涨跌停、公司行动及复权口径未被认证。因此这些测试**不能证明真实交易收益、账户净值或策略有效性**，不能解除正式回测 BLOCKED。Linux、Pyx/Perry/Gyc 当前服务器版本也未复验。


