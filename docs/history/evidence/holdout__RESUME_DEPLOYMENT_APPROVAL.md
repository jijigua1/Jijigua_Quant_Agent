> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase3C 中断恢复：最终 v0.8.2 精确部署申请



状态：READY_FOR_DEPLOYMENT_APPROVAL。生产当前为获批的v0.8.1/revision3。此前批准已执行；本申请只针对其后必要的样本数修复、新会话报告读取和真实缺口显示。



## 文件与SHA



| 文件 | 生产现值 | 候选值 |

|---|---|---|

| src/research_agent/__init__.py | 227c9de2de3bb054026242b6c557f5e633788bd9ae3e7fe40a5daa04d59749d3 | c22c6a90a72feac65dcd44a75f9ad13788ff07c3df1a1f48b7e81aa85411f5dc |

| src/research_agent/conversation.py | 6f37f0c0868ad39751bc04e421290af7a4e285dcc31d79867d0097e456662ba0 | eef2f669e42ceff3a3a8c010faf4d7d2463f56702b42f5c1ddac6e09402f905a |

| src/research_agent/evidence.py | 6945baed9da8c54745513a09a935c104e7606fec79156f92173c741032ee81ac | 7933b657c45d3c3db6d1b26d0b7e1d6c8fb8a50c512de71353e8daa55e3bff22 |

| src/research_agent/interactive_report.py | 83b4419e9719b7aa5b195a47df3dfa7b60f7fabd43fe1db8971506c275acf6f5 | 21d9a0a2c9a022a60e1d9da63510dea170df012956109986b92b8cca3fd2120a |

| src/research_agent/quant.py | fe09c7d2440a2ed330246526302dc44300b3f36bb2e138d3ee97ed62f9317111 | 7ea3200a0866519c7c0cb2768f466b0e20ae1ab0650c4c0b06881349ebcdebf2 |



wheel：wty_research_agent-0.8.2-py3-none-any.whl；SHA：aad21f2d2b538635cd6413b378ff1b25e8af5f7d42fdec13c4b85912f5c32715。仅更新这5个模块、对应wheel及pyproject.toml/README.md/CHANGELOG.md和本轮交付文档。其他87份源码/资源不变。



## 新增配置的准确授权范围



新增 `/opt/jijigua-quant-agent/research_agent/config/report_catalog.json`，root:quantagent，0640；父目录权限不改。SHA：39448e8e5df166ad2450c659eb3f2ab1fa9eb5412aeed625290a4832f269d0c3。仅共享已经公开的五日反转study_id `INTERNAL_RUN_ID_REDACTED:1339576f3486425d`，固定原研究路径及analysis SHA。新会话仍通过原qrtk_read_study读取；未登记研究和封存数据拒绝。不存在普通2026行情Resource，不导入其他SSH会话聊天记录。原resources.json/research.json不改。



## 新报告登记



同一study_id及同一evaluation_id，登记公开聚合重渲染revision4：



`/srv/jijigua-quant-agent/research_runs/2026-10-13/12-07-19_report_revision_4/`



manifest SHA：ab469a42d196727b294c97b8ce45ca0c082c62fc2e0126689b4fdc96c298ede5。源revision3 SHA：5d7ef4309e542a3373e4671a4bdfef62b21b6a7b72c3110353032ef9db48c88a。



只更新原研究report_versions.json及运行manifest的索引登记；先保存两者原字节到reports/report_versions_before_revision4.json及reports/manifest_before_revision4.json，并在受保护部署备份保留相同SHA。revision1/2/3、因子PKL、统计CSV和签名回执均不改。真实NaN保留为图形缺口；累计值不归零；缺少Test分组收益不画Test线段。



## 前置条件与执行



核对生产v0.8.1、94个源码/配置指纹、启动器SHA、原索引及manifest、活动会话；偏差或busy即停止。建立release_backups/v081_before_v082_<服务器时间>，保存旧5模块、v0.8.1 wheel、项目元数据、索引/manifest、原会话绑定、SQLite一致性快照。



quantagent在原venv离线pip --no-index --no-deps --force-reinstall安装已核验wheel；原子替换批准文件并维持既有所有者/权限。新catalog为root管理只读配置。登记revision4后，使用正式quant-agent chat恢复历史会话首问，再用新会话执行8条短中文及旧SEALED/私有数据拒绝问题。无内部ID作为用户提问参数。预计安装与核对30秒以内；CLI验收约2—4分钟，受API延迟影响。单会话原100调用/300000 tokens预算不提高，超额即停；不会重算任何因子或Test。



## 已有验证



复用Windows/Linux完整324通过1跳过证据。新增样本数/报告共享/会话/版本定向回归Windows40通过、Linux40通过；真实缺口和报告再渲染Windows8通过，Linux实际重渲染的逐日/年度/月度统计、热力图、累计曲线及旧文件SHA自检通过。真实官方DeepSeek新会话2问自主只读查询，959/479/177有效日、10月2观察日0成熟标签正确。已有生产首次5问数值解释失败证据保留，不能作为最终语义通过。



## 回滚



恢复备份5模块、v0.8.1 wheel及项目元数据、原最新索引和运行manifest。新增catalog移至本次备份隔离，不删除证据；不恢复整库覆盖SQLite，不删除新增查询记录。只有配置仍一致且不busy的升级会话才能恢复旧绑定，并追加回滚记录。新revision4及历史报告、失败证据保留。



不修改数据/ACL、原生产行情、Train/Validation发布版本、私有Test、评估账本/签名/预算、官方API/Key、root启动器、Claude或GeorgeResearch项目；正式账户回测继续BLOCKED。新增Test评价次数0。/hy-tmp仍需备份。

