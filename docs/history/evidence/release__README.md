> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 3-B2-A 独立数据发布原型

本目录独立代码仅以受审核对的一次性 `/tmp` 包在 GPUShare 运行，没有部署到或注册给主 Agent v0.6.8。用户已批准并完成一次真实六字段探索性 Train/Validation 发布；主 Agent 功能仍冻结。早期阶段报告见 [`PHASE3B2A_FINAL_REPORT.md`](release__PHASE3B2A_FINAL_REPORT.md)。

Phase 3-B2 最新交付入口：[上市日期与首次真实发布报告](release__PHASE3B2_LISTING_RELEASE_REPORT.md)；[首次发布审批范围](release__REAL_RELEASE_APPROVAL_20261012.md)。当前状态是 **PUBLISHED_EXPLORATORY_VERIFIED**；正式回测与主 Agent 全量资源集成仍未获准。

后续收尾：[`PHASE3B2A_SECURITY_CLOSEOUT.md`](release__PHASE3B2A_SECURITY_CLOSEOUT.md) 记录 Linux 合成权限验收，[`LISTING_DATE_AUDIT.md`](release__LISTING_DATE_AUDIT.md) 记录真实发布阻塞项；[`NEW_API_COMPATIBILITY_REPORT.md`](release__NEW_API_COMPATIBILITY_REPORT.md) 仅保留已终止的第三方网关历史测试证据。主 Agent 与生产 Provider 均未切换；官方接口冒烟记录见 `official_deepseek_smoke_evidence.json`（原内部附件未公开）。

本地 Windows 验证（Python 3.12、NumPy 1.26、pytest 7.4）：

```powershell
$env:PYTHONPATH='<ARCHIVE_ROOT>\phase3a_data;<ARCHIVE_ROOT>\phase3b_data_release'
python -m pytest -q <ARCHIVE_ROOT>\phase3a_data\tests <ARCHIVE_ROOT>\phase3b_data_release\tests
```

在日后获批、隔离的 Linux 发布环境中，已有固定 manifest 的**只读**源指纹检查命令为：

```bash
PYTHONPATH=/path/to/phase3a_data python /path/to/phase3b_data_release/release.py \
  /hy-tmp/data/daily_update /path/to/approved/daily_update_manifest.v2.json
```

`publish()` 接收受审静态解码后的 `Panel`、候选上市日期屏蔽规则及源指纹；不能把原始完整 PKL 交给研究进程，也不能以 root 执行不可信解码。本轮通过受审 `linux_publisher.py` 做了一次性真实发布，没有建立生产自动调度。
