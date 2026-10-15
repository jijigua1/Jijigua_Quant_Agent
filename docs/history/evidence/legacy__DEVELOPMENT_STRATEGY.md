> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# 当前开发策略与范围

更新日期：2026-10-12（Asia/Shanghai）。沿用已审核的 Phase 0 v2 与 Model-Agnostic Architecture，采用 Development First, Production Hardening Later。

## 当前 Phase 2-A

在既有 Phase 1-F 自然语言框架内接入受审 Claude quant_toolkit 0.2.0 固定计算，不另建调度系统。五个专业 Skills 经主 Registry/Policy 审核；真实回测 Skill 只开放准入检查。用户已批准成果子目录与固定50只、65日只读日频样本，范围见 phase2a 两份批准申请。成果根目录为 `/srv/jijigua-quant-agent/`，原账本原位保留。原始未复权样本只支持探索性因子统计，独立测试段封存。

## 已完成的交互基础

沿用 <ARCHIVE_ROOT>，完成真实 DeepSeek 原生工具循环、可信 development profile、自然语言 CLI、受审 Skills、资源白名单及小样本只读数据工具。用户明确批准的最小 GPUShare 部署已经完成：quantagent、独立新项目/venv/var、20行只读日频快照、root 管理的 quant-agent 启动器。

目标目录为 `/opt/jijigua-quant-agent/research_agent/`。使用者仍通过 root SSH 登录；启动器先清空无关环境、去除附加组并切为 quantagent，随后导入 Agent。当前迭代为模型驱动的回复/澄清/Skill路由、单前台会话记忆、中文交互和HTTP错误诊断，复用既有研究/授权调度；不新增另一套执行系统。完整证据见 [本轮报告](legacy__REPORT_1e9c4b54.md)。

## 后续优先顺序

1. 审阅 Claude quant_toolkit v0.2 的固定计算合同，接入少量 Tools 和专业 Skills，不重复实现因子评价。
2. 确认真实数据的来源、复权、单位、可获得时间及交易日口径，发布适合首个研究任务的小切片。
3. 完成固定计算与数值基准、小规模真实研究端到端验收；合格回测引擎经过独立规则审查后再接入。
4. 增加累计 token/费用预算、任务租约、后台 Worker、取消和重启恢复，再逐步建设实验记忆与专业闭环。
5. 正式长期自主运行或生产使用前完成安全沙箱、作业树资源硬限制、凭据/身份隔离和部署验收。

## 保留边界

完整生产沙箱不作为当前固定受审功能的前置条件，不要求购买 CPU VM。但未知代码、生成代码执行、不可信 pickle、通用 Shell、交易和高风险维护并未获得许可。通用 Runner 保持 BLOCKED_SECURITY；这不阻止当前受控 API 和只读数据 Tools。

未修改旧 Agent、GeorgeResearch、Quanttrade、其他研究员项目或共享数据权限；未修改生产服务、定时任务或交易系统。后续新增账号、权限、生产配置及超出获批数据发布范围的变更仍需单独批准。

非 root、venv、调用次数预算、请求超时和白名单属于开发保护，不能称为正式沙箱。共享 quantagent 可以读取其他 world-readable 文件，安装环境及账本也不具备生产级防篡改；模型没有直接文件或代码工具。当前 CLI 为前台任务，SSH 断开不保证继续研究；同一会话关联多个研究任务并保留有界上下文，尚无跨会话长期记忆。
