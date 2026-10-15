# 开源许可证与第三方权利审查

> 2026-10-15最终更新：所有者已批准公开范围、自有代码权利及AGPL-3.0-only（版权jijigua1）。下方保留审阅时的过程记录；当前决定以`provenance/OWNER_APPROVAL.json`、根LICENSE和最终manifest为准。远端CI结果需另行实际核验。
**状态：OWNER_APPROVED_AGPL_3_ONLY。根LICENSE已加入，自有代码权利已确认；第三方许可不被覆盖。**

## 一、建议由所有者最终选择

| 方案 | 适用情况 | 本项目影响 |
|---|---|---|
| AGPL-3.0-only（优先考虑） | 希望完整PDF能力及网络服务改动保持可获得源码 | 更符合当前PyMuPDF依赖组合的审阅方向；仍需确认自有模块权利并保留第三方许可 |
| Apache-2.0自有核心 + 明确的AGPL组件边界 | 希望自有核心宽松许可，愿意接受组合部署的额外义务或取得商业许可 | 不能因为pip单独安装就断言AGPL问题消失；需法律审查或未来替换解析实现，本轮未做 |
| MIT自有代码 | 极简宽松再利用 | 没有专利明示条款；同样不能覆盖PyMuPDF及其他第三方许可，不能标“整仓均MIT” |

这是一份工程权利清单与决策建议，不是对任何商业使用场景的法律认证。所有者选择后才加入真实LICENSE、版权主体、年份和必要通知，重新冻结和扫描。

## 二、实际发现

| 组件 | 来源/证据 | 权利状态 | 公开处理 |
|---|---|---|---|
| research_agent及原创历史文档 | 本地项目源码/阶段记录/双SHA | 所有者确认最终许可 | 归档候选保留，PUBLIC门阻断 |
| qrtk、qrtk_skills、paper_research、paper_agent | 同一用户的独立开发工具包及集成快照，无原根LICENSE | 不能自动视为第三方MIT；需确认权利及统一许可范围 | 候选保留并登记来源，PUBLIC前确认 |
| 原core_backtest绘图风格/注释逻辑 | 用户已有项目的明确改编说明 | 用户需确认可许可范围 | 仅保留现有小型适配，不复制原回测项目 |
| Pyx账本摘录 | 历史外部研究源码的fixture | 未取得再分发许可 | 已移出公开树，对应测试明确跳过 |
| Gyc/Perry消费函数原代码 | 历史消费合同fixture | 未取得再分发许可 | 原件移出；公开仅原创合同探针，不再宣称本次运行原消费者 |
| 真实论文PDF、提取全文及模型回放 | 内部测试输入 | 无完整再分发许可 | 不公开；受限测试跳过，上传测试改原创PDF |
| Plotly.js 2.32.0 | 源文件NOTICE与官方tag LICENSE | MIT | 保留LICENSE/NOTICE；离线图使用同一包 |
| Archify生成Viewer | 2.17本地工具MIT、Cocoon AI声明 | MIT | 只附生成图与对应MIT声明，不复制全局Skill |
| Viewer嵌入JetBrains Mono子集 | Archify第三方声明 | SIL OFL 1.1 | 保留OFL；未选择任何品牌Logo |
| PyMuPDF | 本机1.24.14元数据与官方说明 | AGPLv3或商业许可 | 可选依赖单独安装；整体许可决策不可略过 |
| NumPy/Pandas/Matplotlib/jsonschema等 | 锁文件与本机dist元数据 | BSD/PSF/MIT等各自条款 | 不复制其Python二进制包；保留依赖与SBOM |
| Codex/Claude全局Skills、插件、MCP、认证 | 用户全局环境 | 非项目分发资产 | 不采集进公开树，仅说明安装者自备工具 |

## 三、官方依据

- [PyMuPDF官方许可](https://pymupdf.io/licensing)：AGPL或商业方案，不存在“只要是可选依赖就自动宽松”的通用结论。
- [PyMuPDF文档FAQ](https://pymupdf.readthedocs.io/en/latest/faq/index.html)。
- [Plotly.js v2.32.0 LICENSE](https://github.com/plotly/plotly.js/blob/v2.32.0/LICENSE)：已核对MIT文本。
- [GNU许可证兼容说明](https://www.gnu.org/licenses/license-compatibility.en.html)：组合程序的适用条款需按具体组合判断。
- [JetBrains Mono源项目](https://github.com/JetBrains/JetBrainsMono)：字体OFL声明随Viewer保留。

具体版本与本机元数据见`provenance/DEPENDENCY_SBOM.json`；它是本次环境清单，不是完整依赖求解器产生的跨平台锁，也不代替逐个二进制wheel的合规审查。

## 四、公开前必须确认

1. 选择整体项目许可及版权主体。
2. 确认自己有权许可由项目/Claude辅助开发的自有模块与适配代码。
3. 接受当前明确排除的外部源码和论文输入；如未来取得许可，再独立申请纳入。
4. 不把内部真实行情授权、模型服务或商业论文的使用权附带授予GitHub用户。
5. PUBLIC发布前对最终提交、wheel内容、文档和全部新Git历史再次扫描。

## 样例嵌入字体

仅公开合成报告重渲染为Noto Sans SC，其name表明确SIL OFL1.1，官方许可原文及SHA已归档。检查嵌入PDF字体列表无MiSans，不分发机器系统字体原文件。见`provenance/SYNTHETIC_VISUAL_CHECK.json`。
