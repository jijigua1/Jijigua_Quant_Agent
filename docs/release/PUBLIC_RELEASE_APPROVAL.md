# Jijigua_Quant_Agent 最终公开审阅与许可证决定

> 2026-10-15最终更新：所有者已批准公开范围、自有代码权利及AGPL-3.0-only（版权jijigua1）。下方保留审阅时的过程记录；当前决定以`provenance/OWNER_APPROVAL.json`、根LICENSE和最终manifest为准。远端CI结果需另行实际核验。
**状态：OWNER_APPROVED_AGPL_3_ONLY；最终技术门禁及远端验收随后执行。**

本轮只在独立归档副本整理，未创建远端仓库、未push、未部署生产。内部活跃研发、candidate4、v1rc和2026评价没有写入。此清单是公开前最后审阅，不是建议立即把整个内部项目上传。

## 1. 精确公开对象

- [完整公开树](FILE_TREE.md)、`provenance/PUBLIC_MANIFEST.json`、`SHA256SUMS`：全部最终相对路径、大小和SHA。
- `provenance/PUBLIC_FILE_PROVENANCE.json`：每文件来源类别、来源原SHA、归档适配及最终SHA；清单自身的递归哈希由外层manifest承担。
- 源快照初始241文件、109个Python模块；保留现有包布局。当前候选来自本地研发快照，并非P1完整生产包，未打正式稳定标签。
- 源快照、历史文件、生产/candidate4基线和公开变换均有独立清单；原私有Git历史不导入，公开历史从审过的快照新建。

## 2. 请审阅这些入口

| 内容 | 入口 |
|---|---|
| 中文/完整英文README | [中文](../../README.md)、[English](../../README_EN.md) |
| 技术和用户文档 | [文档总目录](../README.md) |
| 研发历史 | [16阶段时间线](../history/TIMELINE.md)、[33项Incident](../history/INCIDENTS.md)、[187份脱敏证据](../history/EVIDENCE_INDEX.md) |
| 架构、数据、数学与安全 | [系统](../architecture/SYSTEM.md)、[数学](../architecture/MATHEMATICS.md)、[安全](../architecture/SECURITY.md)、[可交互架构图](../architecture/system.html) |
| 实际报告 | [合成HTML和截图](../examples/README.md)；不是内部市场业绩 |
| 测试和限制 | [实际验收](TEST_RESULTS.md)、[Known Issues](../KNOWN_ISSUES.md)、[工程审计](ENGINEERING_AUDIT.md) |
| 来源/覆盖 | [资产盘点](ASSET_INVENTORY.md)、[文档覆盖](COVERAGE_MATRIX.md)、[归档变化](ARCHIVAL_CHANGES.md) |
| 分发边界 | [权利与许可](LICENSE_REVIEW.md)、[排除项](EXCLUSIONS.md)、[长期同步](SAFE_SYNC.md) |

## 3. 当前技术验收

干净Windows完整离线轮次532通过、1失败、85跳过；修复原创探针列名后定向12项全通过。最后适用用例并集534通过、85跳过，不称再次完整零失败运行。113项工具包合成测试通过。

独立因子/标签/IC/RankIC/G0–G4/HAC复算通过，另4,228项表格和热图核对无差异。安全依赖精确版本查询34项，当前0公告匹配。Windows全新venv、wheel导入和离线CLI已实测；Linux/macOS本轮无真机，三平台Actions尚未远端运行。

凭据、私有路径、二进制/大文件、语法、链接、Git字节及来源门禁均保留。最终扫描回执在`provenance/RELEASE_CHECKS.json`；模式扫描不代替人工审阅。

## 4. 明确不公开

真实行情与因子矩阵、2026私有数据/标签/权限/钥、SQLite和原始日志、私人聊天/账号/主机定位、整篇PDF/商业研报/提取全文回放、未许可Pyx和原Gyc/Perry函数、全局Skills/插件/MCP、私有运维备份。原SHA在来源/隔离清单保留，私有原件不放进Git。

部署脚本只作为审阅模板，不提供真实实例信息；2026服务代码不附私有数据、签名材料、真实授权，也不承诺外部用户可直接启用。

## 5. 需要所有者作出的一次性决定

1. **确认最终公开范围**：同意审定的文件树、历史事故记录、合成样例和状态声明进入`jijigua1/Jijigua_Quant_Agent`公共仓库。
2. **选择许可证和版权主体**：优先建议AGPL-3.0-only（当前完整PDF能力依赖PyMuPDF的AGPL/商业许可）；Apache/MIT只适用于有权许可的自有代码，不能覆盖第三方或自动消除组合许可义务。当前没有根LICENSE，不能称已授予开源许可。
3. **确认原创代码权利**：research_agent、自己/Claude辅助开发的qrtk/qrtk_skills/paper_agent/paper_research和自有绘图适配均有权按所选许可分发。对不确定项先排除，不能直接批准“所有第三方”。

确认后，加入所选真实LICENSE及版权信息、更新权利记录、重新冻结/扫描，并对许可证相关CI门禁重新验收。此操作会产生新的公开候选SHA供追溯，不覆写当前审批快照。

## 6. 获批后的GitHub执行计划（尚未执行）

- 当前认证账号已核对为`jijigua1`，初查同名仓库不存在。发布时再次只读核对冲突；存在同名内容则停止，不覆盖。
- 使用已扫描的干净本地Git历史，不带原私有历史、不添加内部稳定版标签；创建PUBLIC仓库并仅推送审定提交。
- 不上传API/SSH Secrets到Actions。公开CI只运行离线测试、三平台安装、文档/凭据扫描和构建。真实API/生产部署另行授权。
- 推送后读取远端默认分支commit、树和关键文件内容SHA，等待实际Actions结论；若失败如实报告，不以push退出0宣布验收。
- 公开披露后即可能被复制，撤仓不能保证收回。最终确认必须发生在创建PUBLIC之前。

本次没有新的生产部署、行情发布或2026 Test审批需求；只需要上述公开内容和许可决定。
