> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# v0.8.0 最终测试结果



## 完整回归与最后定向修复



| 环境 | 通过 | 跳过 | 失败 | 耗时 | 证据 |

|---|---:|---:|---:|---:|---|

| Windows / Python 3.12.4 | 319 | 1 | 0 | 411.58秒 | windows_release_final.xml |

| GPUShare Linux / Python 3.11.10 / quantagent UID999 | 319 | 1 | 0 | 235.96秒 | linux_unified_final.xml、checks_console.txt |



Windows唯一跳过：操作系统拒绝创建符号链接（1314），同类权限拒绝在Linux执行。Linux唯一跳过：未安装可选pyarrow，保留Parquet测试跳过记录；本次真实发布为既有NPY，未安装新依赖来掩盖缺失。NumPy1.26.4、Pandas2.3.3、Matplotlib3.8.4、jsonschema4.19.2；完整环境/源码/wheel SHA见source_manifest.json。完整回归之后仅修复会话上下文的证据压缩（每条摘要限额2500字节，总限额5000字节不变），Windows受影响会话及综合报告33项定向回归通过（context_targeted_final.xml）；Linux对应证据为linux_context_final.xml。数值/导出/报告源码未因此再次改变。



早期失败日志保留，不能算通过：报告图从7张扩为15张时的旧数量断言，以及Test占位行出现后旧测试错误索引分区。修复的是断言适配；最终完整回归使用真实计算值和Test=N/A检查。首次真实CLI独立测试申请的输出合同失败也保留，最终修复后重验。



## 新增独立数值及拒绝测试



- HAC：独立密集Bartlett协方差二次型对照；重叠H=5标签、首尾结构缺失、内部缺失、短序列、常数序列。

- 年/月：直接从每日IC/RankIC独立求均值、样本标准差和有效日；144个真实2020—2025 IC/RankIC热力图数值对月度CSV；2026封存12格各图均N/A。

- 因子：完整1455×5427矩阵与独立NumPy；受审Gyc/Perry读取合同、日期、代码、float64、NaN和默认PKL；抽样Pearson/平均秩Spearman独立复算。

- 时间：Validation受控Train暖机，Train/Validation末H+1日无成熟标签，不用2026补尾；已有因果截断测试及19算子回归保留。

- Test评估器：未冻结、改参、错误/过期签名、任意路径、同定义重复、多次预算、失败计次、并发一次执行、真实模式缺独立身份/快照默认拒绝。

- 三阶段报告版本：初版NOT_RUN/SEALED；签名合成结果同一study_id生成第二版，原HTML字节不变；Test年度/月度数值一致；篡改、重复回执、合成Test并入真实报告拒绝；新版本manifest核验及最新报告读取。

- 真正OS拒绝：quantagent读原始PKL、staging、daily_private、audit失败；临时quantpub私有合成Test文件拒绝。未创建真实Test身份/快照，不将此证据说成真实Test物理隔离已部署。



## 真实运行证据索引



`benchmark.json`：完整真实Train/Validation阶段耗时、RSS、年度/月度复算、PKL合同、manifest。



`live_recovery_cli.txt`、`live_acceptance.json`：真实SSH PTY官方DeepSeek，普通中文五日反转→独立测试申请→逐年追问→2026调参拒绝→报告路径；账本核验因子只计算一次、申请不读取Test、全量PKL及边界标签。



`audit.json`、`production_before.json`：生产源码/配置/启动器未改变、OS权限与旧2026资源拒绝。`synthetic_isolation.json`：合成Test UID拒绝与评估协议。



图表及离线HTML人工检查、截图和PDF证据见VISUAL_QA.md；最终性能表见PERFORMANCE.md。测试从未解封真实2026目标收益或表现，正式账户回测仍BLOCKED。





## 正式入口最终验收



获批准后v0.8.0正式quant-agent chat SSH PTY验收通过。问候无Tool；完整五日反转一次计算；年度/报告追问不重算；Test只登记、2026调参拒绝。89产物SHA、独立全矩阵及IC/RankIC核验；264旧任务payload和数据库Schema未变。记录见production_acceptance.json、production_live_cli.txt；真实Test未读取，正式回测BLOCKED。

