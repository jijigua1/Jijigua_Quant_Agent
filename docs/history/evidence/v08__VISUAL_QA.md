> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# v0.8.0 实际图表与报告视觉验收

样本是真实已发布2020—2025数据的20日动量报告，不是合成截图；对应 `benchmark.json` 的完整1455×5427研究。截图在本机浏览器实际打开生成，保留服务器原报告SHA及CSV。

| 检查 | 实际证据 / 结果 |
|---|---|
| 首页三阶段及小表 | summary_final_desktop.png：Train/Validation实际范围、Test NOT_RUN/SEALED、IC/RankIC有效日及N/A；详细指纹不占首页 |
| 数字月度热力图 | heatmap_final_desktop.png：7行2020—2026、每月具体数值、中心0对称色阶，2026全N/A；144真实格逐一对CSV |
| 实际悬浮 | heatmap_final_hover.png：2023年7月RankIC −0.02746848、21有效日、覆盖91.43%、train分区，与CSV/JSON一致 |
| 深色 | heatmap_final_dark.png：背景、表头、图例、文字和N/A可读；无额外深色数据计算 |
| 390像素窄屏 | summary_final_mobile.png、heatmap_final_mobile.png：小表及热力图在自身区域横向滚动，路径换行保留完整文本；测量root scrollWidth397、viewport390，7像素溢出由既有容器裁剪，无截图中可见的全页横向滚动。严格DOM宽度零溢出仍是轻微待改进项，不宣称完美移动适配 |
| 分图与时间范围 | trends_final_desktop.png：IC/RankIC分开；点击1y后日期刻度为2025年1/3/5/7/9/11月，All恢复2021—2025；实际点击图例开关；滚动曲线、累计相关不标NAV |
| 公式 | formula_final_desktop.png：从实际AST生成的数学SVG公式，全部内嵌图片加载成功，不用模型重新改写 |
| 导出 | 浏览器SVG按钮实际下载成功，browser_export_rank_ic_monthly_heatmap.svg为1500×650输出；静态PNG/SVG/PDF全部入manifest |
| PDF | sample_rank_ic_monthly_heatmap.pdf经Poppler渲染为heatmap_pdf_check.png，实际查看7行数值、轴与Train/Validation/Test标签，无重叠或裁切 |
| 控制台/资源 | 8个交互图实际加载，控制台error为0；DOM外部script/image/stylesheet为0，Plotly及图像内嵌，无CDN |

## 离线及打印边界

HTML为单文件：固定SHA验证的Plotly2.32.0与MIT许可、图表数据、公式SVG、静态图像/PDF链接均内嵌；自动化测试验证无外部依赖，本地HTTP预览实际显示全部图。浏览器工具安全策略禁止访问file://，**本轮未完成在该浏览器直接从文件离线打开的UI动作**，未绕过策略；用户可下载后双击该HTML。不能把HTTP200当成已做文件直开。

打印CSS隐藏交互控件、切换静态图；静态PDF已渲染检查，未实际操作整份HTML的系统打印预览。完整报告以桌面阅读为优先，窄屏大表保留内部横向滚动。

此前截图desktop_initial.jpg、heatmap_initial_desktop.jpg、heatmap_initial_dark.jpg保留，反映优化前export按钮被图SVG遮挡等问题；最终图区域高度取真实layout，封存Test行加入后无该遮挡。没有为图表美观改变数值或生成虚假账户曲线。
