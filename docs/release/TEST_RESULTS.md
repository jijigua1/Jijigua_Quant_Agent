# 公开候选验收结果 · 2026-10-15

> 2026-10-15最终更新：所有者已批准公开范围、自有代码权利及AGPL-3.0-only（版权jijigua1）。下方保留审阅时的过程记录；当前决定以`provenance/OWNER_APPROVAL.json`、根LICENSE和最终manifest为准。远端CI结果需另行实际核验。
**结论：离线工程候选可审阅；所有者已完成许可、权利和最终披露确认，远端发布仍须通过最终技术核验。当前源码不是生产稳定版承诺。**

## 实际运行的测试轮次

| 轮次 | 实际结果 | 用时/说明 |
|---|---|---|
| 初始采集探索 | 399通过、84失败、5跳过、17错误 | 1457.66秒；缺受限论文输入、Skill字节改变、Windows POSIX及旧断言均保留 |
| 公开输入适配后 | 527通过、5失败、82跳过 | 1482.14秒；剩余进度图数、原创合同探针列名、私有回放依赖 |
| 安全升级后的干净venv完整离线分片 | 532通过、1失败、85跳过 | 墙钟748.39秒；三个互不重叠文件集合，运行前后源码指纹一致 |
| 唯一失败修复及最终相关回归 | 12通过、0失败 | 原创探针保留columns.name，不放宽原索引/浮点/NaN断言；新增大文件预算测试也通过 |

最后适用用例状态合并：**{'passed': 534, 'skipped': 85}**。这是全量轮次与最终定向回归的并集，不是“再次完整运行全部测试零失败”。逐条用例、运行指纹和原始私有JUnit哈希见`provenance/TEST_RUNS.json`。113项工具包合成测试在完整轮次通过。

85项跳过包含未许可论文/PDF全文回放、外部Pyx账本和Windows无法运行的POSIX入口；未运行项不计为通过。原创PDF测试只证明上传/去重/路径和提取运输，不能代替真实论文语义验收。

## 安装、数值与报告

- 标准库`tabnanny`检查src/tests/tools/examples缩进格式，0问题；不是强制整体重排代码风格。CI也包含该无新增依赖检查。
- 全新Windows CPython3.12.4 venv安装固定依赖及构建wheel成功，11个关键模块确认从venv wheel加载，安装后Mock CLI退出0；未依赖活跃项目的PYTHONPATH。
- 安全wheel：`wty_research_agent-0.8.2-py3-none-any.whl`，SHA-256 `fc3a0dfd3eefae7e04da410470b55c434d7cdf03aa8399c0ec568edd4c5a8766`。wheel只保留在私有验收区，不上传公开仓库。
- 原创文本论文离线例：参数/定义验证通过，0警告，不声称复现任何真实论文。
- 合成五日反转完整研究：21.047秒；默认PKL、14张静态图、HTML/Markdown、manifest实际生成，未连模型/2026评价器。
- 独立因子复算：58,240个有限因子单元；NaN位置一致；IC/RankIC最大差分别3.33e-16/1.67e-16；G0–G4差9.98e-17；HAC和分区汇总通过。故意反转分组方向的负对照按预期失败。
- 第二核验器逐项检查4,228个CSV/表格/12热图数值，0差异。
- 浏览器实际打开18个交互图、14张图片，0破图；1280宽桌面和390宽窄屏无整页横向溢出。数值热力图、Test N/A和紧凑表格已肉眼检查。见[公开合成示例](../examples/README.md)。
- 结构图交付门9/9通过；实际浅/深色截图与可编辑图规格保留。

## 安全依赖与扫描

旧依赖公告记录保留。仅公开副本升级安全pins；当前OSV精确版本查询34项、0匹配公告，查询时间与锁文件SHA见`provenance/DEPENDENCY_SECURITY_CURRENT.json`。PyArrow23.0.1包含在真实干净环境测试；不是把可选依赖排除扫描。

扫描工作树、待提交内容与新Git历史；输出位置而不回显秘密。最终冻结记录见`provenance/PUBLIC_MANIFEST.json`及审批包。模式扫描不是无秘密的数学证明；人工来源、论文版权、PDF嵌入字体与权利检查是独立门禁。

## 未运行的项目

| 项目 | 本轮状态 |
|---|---|
| Windows新环境、离线CLI、合成数值、浏览器 | 实际执行 |
| Git Bash客户端安装脚本 | bash语法检查通过，不是macOS安装 |
| Linux/macOS真机回归 | NOT_RUN；容器引擎不可用，未擅自启动系统服务 |
| GitHub Actions三平台 | 已提供配置，尚未PUBLIC/push，不能声称远端通过 |
| 真实DeepSeek/SSH/生产升级/真实2026评价 | 0次；未触碰活跃研发或生产 |
| 原消费者完整程序、商业论文、完整市场行情 | 不公开/未重跑；使用边界见权利清单 |

## 可重复运行

按Windows/macOS/Linux指南建立独立环境后执行：

```bash
python -m pytest -q -p no:cacheprovider
python tools/release_audit.py --history
python tools/dependency_audit.py
python tools/publication_gate.py
python examples/offline_paper.py
python examples/offline_research.py --output demo_output/factor_run_01
```

`publication_gate.py`在未选LICENSE时必须非零退出；CI为此保持阻断是正确行为，不是通过绕过门禁发布。新环境可有额外平台失败，须保留真实结果再修复，不能沿用本次Windows结果冒充。

所有者批准后的AGPL元数据wheel已重新构建、检查License-Expression及许可文件、安装并重新通过11模块导入/Mock CLI；源码算法和依赖pins未改变，不重复宣称全量数值测试。
