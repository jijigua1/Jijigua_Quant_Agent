# 合成研究报告示例

[离线交互HTML](synthetic_report.html)由本次固定种子的原创合成行情计算，不是A股历史表现，也没有真实2026评价。数据跨度覆盖2020—2025只是测试分区和日期轴的工程设计。

- [桌面首页](report_desktop.jpg)、[RankIC热力图](report_heatmaps.jpg)、[窄屏表格](report_mobile.jpg)。
- `evaluation_daily.csv`、`evaluation_annual.csv`、`evaluation_monthly.csv`及指标JSON是同一次合成研究产物。因子矩阵/PKL由`examples/offline_research.py`本地生成，不上传Git。
- 4,228个表格与热力图数值独立核验；因子、标签、日度IC/RankIC、G0–G4和HAC均另外复算。方向反转的故意错误对照应失败，不是主核验失败。
- HTML包含离线Plotly、图片与PDF下载数据。为避免分发许可不明的系统字体，本公开样例只用本机已有Noto Sans SC（SIL OFL 1.1）重新渲染；数值表JSON逐字义相等。字体许可见`LICENSES/NotoSans-OFL.txt`，不附字体原文件。
- HTML中的`example-output`是脱敏显示，不是可以点击访问的真实路径。请运行离线示例取得自己的完整成果路径。
- Test显示NOT_EVALUATED / EVALUATOR_UNAVAILABLE，所有2026值为N/A。PDF/图表不是正式账户回测。
