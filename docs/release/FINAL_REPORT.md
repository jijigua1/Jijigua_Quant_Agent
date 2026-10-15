# Jijigua_Quant_Agent 正式工程归档与公开交付

## 发布结果

- 公开仓库：[jijigua1/Jijigua_Quant_Agent](https://github.com/jijigua1/Jijigua_Quant_Agent)，可见性PUBLIC。
- 许可证：AGPL-3.0-only；原创代码版权jijigua1，2026年；第三方许可和字体通知分别保留。
- 经过所有者审阅批准的独立归档：570文件，109个核心Python模块，16阶段时间线、33项Incident、187份脱敏工程证据。
- 已推送并重新从GitHub clone的代码提交：`140a0fd154af8e9d0f6b06ee08fd22e0d8b117ff`。570文件逐字节相同；40个Skill内容指纹、manifest和SHA256SUMS全部通过；远端副本Mock入口退出0。
- 最终公开文档补记提交不改变研究代码、测试、依赖或配置。当前具体提交以仓库`git rev-parse HEAD`为准，避免manifest自引用。

## 实际工程交付

双语README；Windows/macOS/Linux使用边界；论文上传/参数/资产确认；Tool/DSL/IR与统计合同；安全和数据隔离；逐模块文档及覆盖矩阵；完整来源双SHA；合成报告及桌面/窄屏截图；开源凭据/大文件/路径/许可/历史扫描；离线三平台Actions及Issue/PR模板。

没有导入私有Git历史、真实行情、2026私有数据/标签/身份密钥、原始聊天/日志、受限论文全文或未许可研究者实现。排除项和原SHA可追溯，没有把缺失历史补写成事实。

## 已运行的验收

- Windows干净venv完整离线轮次532通过、1失败、85跳过；原创格式探针列名修复后定向12项通过；最后适用用例并集534通过、85跳过，不冒充再次完整零失败运行。
- 工具包113项合成测试通过；因子、标签、IC/RankIC、G0–G4及HAC独立复算通过，另4,228项表格/12热图数值0差异。
- wheel重新构建、AGPL元数据/许可检查、11模块导入、离线Mock CLI和原创文本论文例均执行。
- 18个交互图、14张内嵌图片实际浏览器检查，无破图；桌面及390像素窄屏无整页溢出；公开PDF字体子集为核实许可的Noto。
- 当前34项依赖精确版本OSV查询无已知公告匹配；模式扫描、全部准备公开Git历史、暂存字节、链接和Python语法通过。扫描不构成绝对无秘密/无漏洞证明。

## GitHub Actions实际状态

[本次完整运行](https://github.com/jijigua1/Jijigua_Quant_Agent/actions/runs/38706709199)，以下是观察时状态，仍运行的项目后续以GitHub实际结果为准：

| 作业 | 观察时结果 |
|---|---|
| publication-policy | success |
| offline (macos-latest) | failure |
| offline (windows-latest) | in_progress |
| offline (ubuntu-latest) | in_progress |

macOS实际为538通过、79跳过、2失败（1375.96秒），不是通过：launcher合成测试未模拟quantdata组；服务器PDF导入子进程返回PDF_UNREADABLE，具体子进程错误仍未确定。所有者明确表示本轮macOS不作为公开发布阻断，不追加适配或重跑。失败保留，没有放宽断言、删除平台或伪造绿色CI。

最后补记只有文档/来源清单，使用`[skip ci]`避免再次运行昂贵全套；本地重新运行完整历史/文件/链接/许可门禁，并核对运行文件与上述代码提交完全一致。不是将完整CI失败伪装为成功。

## 完整入口

[中文README](../../README.md) · [English](../../README_EN.md) · [文档总目录](../README.md) · [时间线](../history/TIMELINE.md) · [Incident](../history/INCIDENTS.md) · [合成HTML与截图](../examples/README.md) · [测试细节](TEST_RESULTS.md) · [来源状态](SNAPSHOT_STATUS.md) · [许可](LICENSE_REVIEW.md) · [排除项](EXCLUSIONS.md) · [安全同步](SAFE_SYNC.md)

## 未改变的边界

活跃Claude研发、candidate4、v1rc与生产系统未修改；本轮真实API调用、SSH研究和2026新增评价均为0。公开的是可追溯研发归档，不是新的生产稳定版或合格交易回测系统。无私有市场数据的下载者只能直接复现合成工程例；真实论文、数据和受控Test需自行获得合法输入及独立部署授权。
