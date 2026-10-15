# 数据、实验资产与三阶段报告

## 数据来源与资格

内部数据来自既有日更源，不是本项目新抓取程序。当前公开代码支持受控发布，公开仓库不提供行情授权。内部历史批次的Train为2020-01-02—2023-12-29（970观察日），Validation为2024-01-02—2025-12-31（485观察日）；5427是固定代码轴，两列身份冲突证券整列排除，非每日5427个有效股票。

六字段为open/high/low/close/volume/amount；手和千元需在合同显式记录。上市前回填、固定股票轴、冻结状态字段、复权历史重建、缺少PIT和可获得时间等风险见历史Phase3-A证据。`PROFILED_EXPLORATORY_ONLY`不等于BACKTEST_APPROVED。

## 隔离与版本

原始PKL包含完整时间段，研究进程不能先读完整文件再切片并声称隔离。Train/Validation使用独立发布；Test文件由独立身份持有，研究只提交冻结方案，获取受控回执。文件系统拒绝和进程身份是部署验收要求，Python函数返回拒绝只是原型层证据。

数据版本绑定来源文件大小/SHA、实际日期、股票轴、字段、批次及质量检查。文件mtime不是交易日认证。原文件日更重写会修订历史；旧研究必须绑定不可变发布而不是“当前路径”。增量与历史修订需新批次，不覆盖旧版。临时数据盘并不保证永久保存，需操作者独立备份。

## 因子资产

`factor_export.py`从已计算因子值生成PKL，无新LLM调用。主消费合同为YYYYMMDD字符串索引、带交易所后缀的代码列、float64值和原NaN；兼容格式分别命名。PKL不混未来标签。原子写、独立读回值检查、文件SHA、元数据与manifest共同构成交付；失败为EXPORT_FAILED/PARTIAL。

目录采用`research_runs/YYYY-MM-DD/HH-MM-SS_factorname/`，时间来自可信系统Asia/Shanghai，冲突加唯一后缀；ID在manifest和SQLite保留。旧UUID目录不迁移。代码/表达式/参数/数据/算法语义指纹应该共同绑定，不靠目录名定义研究。

## 报告模型

`report_versions.py`追加同一study_id的revision。初版保留Train/Validation/Test，Test未运行时N/A+原因；合法签名回执到达后增加新版，不覆盖原报告。Train/Validation指标应字节或数值一致。最新指针只由受审版本管理更新，不用会话旧摘要替代读取。

`metric_system.py`从保存的Train/Validation日度IC和组收益、以及Test回执逐日行建立统一表，年/月来自同一信号日证据。`interactive_report.py`提供离线交互，静态图和CSV是同源产物。LaTeX由实际AST/IR生成，不能让模型另编一个公式。技术JSON与指纹放附录，核心表紧凑可读。

日期图跨分区连续，累计值不重置；两条竖线区分Train/Validation/Test。缺少Test分组逐日数值时该曲线停在Validation，不用IC或均值猜收益。非日期轴的预测期衰减图仍使用H作为横轴，不能机械连成时间轴。

## 最新读取与刷新

归档开发快照的`read_study(refresh=False)`应为只读，显式刷新才可能请求新快照或补回执报告。历史P1生产路径曾将读取与评价混合，详见事故记录。读报告、补已有回执、重新评价是不同操作，预算和曝光不能混算。

研究结论是证据判断：方向、HAC、跨年/月稳定、验证衰减、覆盖、组单调性及数据资格共同作用。PROMISING_EXPLORATORY不是可交易认证；REJECTED也不能代表所有未来市场普遍无效。
