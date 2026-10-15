> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 2-B 数据准入（只读复核）

## 当前可用合同

仍只发布已批准的 `gpushare:daily65`：2026-07-03—2026-10-09，65观察日、50个固定代码、3163行。
CSV九字段；代码六位字符串、日期 Asia/Shanghai，OHLC为原始价格、volume为股数、amount为人民币。
来源是服务器日频更新管线的小样本；源代码解释 volume ×100、amount ×1000，但逐行历史发布时间未全面验证。
样本的日历是 observed union，不是正式交易日历；缺少87/3250面板记录，不能将缺失直接当停牌。
输入 SHA-256：`d2853cd903a7eea6df717b8c367c4ee8e1ee72f5c39c547c577e888ddcaf08a8`。

准入：探索性因子计算、IC/RankIC、未扣费分组毛收益；无公司行动、退市、逐日独立可买可卖或正式净值结论。

## 更长历史候选

限定位置复核记录在 remote-inspection.json；没有扫描或复制88GiB因子矩阵，也没有执行任何 pickle。

- `/hy-tmp/data/daily_update`：open_adj/close_adj/adj_factor/volume/各交易状态等 pickle 文件确实存在，价格字段每个约81.8MB，root:root 0600。文件名不是覆盖、复权或发布时间的证明，quantagent 无读取授权。
- 对trading_date/open_adj/close_adj/volume各读取最多64KiB前缀，用pickletools解析操作码（不执行或反序列化）。前缀显示pandas DataFrame/numpy数组；trading_date列名包含exch_market/trade_days，旧pandas numeric索引与新numpy模块路径共存，转换需核验兼容性。操作码流均被前缀截断，所以不据此认证日期覆盖。
- 两个既有 eod 文件在 `/srv/auxiliary-data/EOD_Columns/eod`、`/hy-tmp/research_perry/eod` 确实存在。未反序列化，不能认证覆盖或转换安全性。
- `/srv/auxiliary-data/TRD_Dalyr.csv` 当前不存在；`TRD_Co.csv` 存在，含上市日期/行业/公司描述，但不是价格历史，不能替代退市及公司行动数据库。
- `/hy-tmp/backtest_data` 有 industry/index_weights 子目录；尚未确立其时点口径和许可，不登记成研究价格资源。

因此本轮没有扩大数据发布。需要可信数据生产者明确 pickle 的生成代码与内容类型，并通过其已有受审导出程序发布非执行格式，先核对日期/轴/单位/复权/可获得时间/日历/交易状态/公司行动。

补充对626,087字节 trading_date.pkl 的完整静态 opcode 检查（不反序列化、不执行REDUCE）：包含SSE/SZSE及24,518个日期字符串，12,275个不同日期，字面范围1990-12-03—2040-12-31。未来日期说明它含预设日历；**不能把这个范围当实际行情历史**，价格轴及日历有效性仍未认证。SHA-256与检查记录见calendar-static.json。

## 最小后续发布边界（需另批，不在本轮执行）

建议可信生产者输出最多50个已授权代码、1000交易日、OHLCV及独立can_buy/can_sell/suspended、公司行动和交易日历合同；约50,000行，需同时调整当前10000行/4MiB的受控读取上限并做内存与压缩膨胀测试。
先冻结代码池、研究截止与独立测试起点，正式提出准确的原文件/日期/字段/行数/输出指纹申请。**当前未证明来源，因此这不是一份已经批准的转换命令。**
不改原始文件权限，不给quantagent访问整个生产数据目录，不自动加载未知pickle。

## 独立样本外

daily65 的 test=sealed 只隐藏统计；data_query 可以读同一价格，且历史会话已有曝光。它不是盲测，不能通过改名重新认证。
新 ResourceCatalog 支持可信清单全局 withheld_from：所有资源、别名的发布日期和实际内容必须早于该日期；任何晚期记录被拒绝，不由模型解封。
它覆盖所有现有数据/量化Tools共同使用的读取入口，但不是OS沙箱，也不能抹去旧暴露。真正独立测试必须单独保管、不可向普通Agent身份发布，并在冻结假设后由另行验收的评测器揭示；该评测器尚未启用。

## 存储

`/hy-tmp` 当前为XFS，空闲约73.8GiB。平台官方文档明确关机24小时后及实例迁移可能删除；不自动上传或清理。重要成果请另行备份。
来源：https://gpushare.com/docs/data/storage/ （本轮在线复核）
