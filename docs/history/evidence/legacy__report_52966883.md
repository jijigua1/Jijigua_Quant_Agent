> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# 因子研究报告：reversal

状态：**incomplete / exploratory**。计算已完成；正式回测和独立盲测未通过准入。

## 研究问题与假设

研究五日反转因子：在已批准的历史日频研究样本上，计算反转因子（factor_id 为反转类，lookback=5），检验其 IC/RankIC 与分组毛收益，并生成完整分析报告（含图表与 Markdown/HTML 报告）。若需先确认可用资源，先查询已批准研究样本清单与口径。

假设：在已批准的历史日频研究样本 gpushare:daily65 上，五日反转因子（reversal=-(close[T]/close[T-5]-1)）与未来5日收益存在负向预测关系：前期涨幅越大，后续收益越低，因此因子值越高（前期跌得越多）对应未来收益越高，预期 Pearson IC 与同秩 RankIC 为正，且等权分组毛收益随因子分组单调递增。

## 因子定义与时间约束

```json
{
  "factor_id": "reversal",
  "lookback": 5,
  "standardization": "raw",
  "hypothesis": "在已批准的历史日频研究样本 gpushare:daily65 上，五日反转因子（reversal=-(close[T]/close[T-5]-1)）与未来5日收益存在负向预测关系：前期涨幅越大，后续收益越低，因此因子值越高（前期跌得越多）对应未来收益越高，预期 Pearson IC 与同秩 RankIC 为正，且等权分组毛收益随因子分组单调递增。",
  "generation_reason": "已确认唯一可用资源为 gpushare:daily65（2026-07-03 至 2026-10-09，仅65个观测交易日，未复权、固定50只代码、非时点全市场universe）。该资源限制提示每个训练/验证分段可能不足60个成熟标签，因此下一步用 qrtk_factor_study 以固定构造 lookback=5、horizon=5、n_groups=5、standardization=raw 计算 IC/RankIC 与分组毛收益，并据实际有效日数判断证据是否充分。"
}
```

输入截至 T 收盘。只允许历史偏移；零分母与缺失输出 NaN，不填成零收益。
标签：open[T+1+H] / open[T+1] − 1；T 表示已观察日期序号。
该数据未证明正式交易日历或历史发布时间，故不得将该标签当可执行交易收益。
方向 +1 预先固定，G0 分数最高；ICIR 未年化，重叠标签不独立。

## 数据合同与研究划分

资源：gpushare:daily65；65 观察日、50 只股票。
来源：GPUShare published recent_days TRD_Dalyr.csv; reviewed production Tushare field conversion, some mixed-source publication。
复权：none；成交量单位：shares；日历：observed_union。
可获得时间：after T close; historical per-row fetched_at not fully verified; trade date is not availability time；股票池：fixed first fifty codes sorted from 2026-07-03 source rows; not a point-in-time market universe。

```json
{
  "factor_name": "reversal",
  "direction": 1,
  "horizon": 5,
  "lag": 1,
  "n_groups": 5,
  "min_obs": 10,
  "train": [
    "2026-07-03",
    "2026-08-26"
  ],
  "valid": [
    "2026-08-27",
    "2026-09-17"
  ],
  "test": [
    "2026-09-18",
    "2026-10-09"
  ],
  "universe_name": "fixed first fifty codes sorted from 2026-07-03 source rows; not a point-in-time market universe",
  "execution_rule": "next_observed_open",
  "min_dates_per_split": 60
}
```

每个分段剔除出场日在段外的标签。验证段用于探索，看到结果后改参数不能称独立样本外。
IC时序、分布和分组CSV使用同一套按分段剔除的成熟标签；图中空白不插值，分布样本数等于训练及验证有效日期之和。
test=sealed 仅隐藏本工具统计输出；daily65 原始数据已有其他授权读取路径，**不是全系统盲测**。
真正独立测试应单独发布、阻断所有原始价格/标签/绩效通路并冻结假设后验收。

## 实际计算结果

| Split | Mature dates | IC mean | RankIC mean | RankIC positive share | G0−G last gross |
|---|---|---|---|---|---|
| train | 28 | 0.0497717 | 0.0257145 | 0.571429 | 0.014202 |
| valid | 10 | 0.156835 | 0.149846 | 0.7 | 0.0209782 |

分组为等权、未扣成本的 H 观察日毛收益；不是净值、Sharpe 或可交易收益。

## 稳健性、证据与回测准入

截断测试：True；证据等级：insufficient。
正式回测：BLOCKED_DATA_CONTRACT / BLOCKED_ENGINE_QUALIFICATION，无账户绩效和账户图表。
尚需复权与公司行动、独立买卖状态、退市、费用历史、合格引擎逐日账本与独立样本外验证。

## 研究局限

- only 65 observed dates, each train/validation segment may have fewer than 60 mature labels
- unadjusted prices: corporate actions can distort returns; no strategy efficacy claim
- observed date union is not independently verified exchange calendar
- historical availability, suspension, limits, delisting and full universe not fully verified
- labels overlap (h=5): ICIR not annualised; effective independent dates ~ n/5
- train: only 28 valid RankIC dates (< 60)
- valid: only 10 valid RankIC dates (< 60)
- test is sealed; no independent test claim
- IC is for the stated raw factor; direction +1 fixed before results; group 0 has highest scores
- group returns are gross, equal weight, missing labels excluded; not account returns
- no industry/size neutralisation, HAC or multiple-testing adjustment
- positive observed volume is sample eligibility, not permission to buy/sell
- all parameter changes after seeing validation are exploratory; no certified out-of-sample performance

## 图表（由实际 CSV 生成）

!ic_rankic（原内部附件未公开）

!ic_distribution（原内部附件未公开）

!group_returns_gross（原内部附件未公开）

!factor_coverage（原内部附件未公开）

!factor_distribution（原内部附件未公开）

## 复现与成果

数据 SHA-256：`d2853cd903a7eea6df717b8c367c4ee8e1ee72f5c39c547c577e888ddcaf08a8`

参数指纹：`0183d32c9a443549a6858d78d3d04fa75512a1e1bdba774e90af936ad22750b3`。完整代码、依赖、调用版本及文件 SHA-256 见 manifest.json。

受控复现入口：`python code/reproduce.py`（同版本依赖；只读本成果 data/input_slice.csv）。

/hy-tmp 为临时存储，请自行备份；前台 SSH 断开不保证任务继续。
