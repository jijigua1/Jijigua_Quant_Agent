# Skills、MCP、插件与项目配置

## 实际注册

项目Skill位于`src/research_agent/resources/skills/`，按`approved_skills.json`核验SKILL.md、skill.toml及输入输出Schema的内容指纹。Skill说明不是授权；Tool Registry和Policy决定能力交集。项目含mock_research、data_query、五个专业研究Skill及paper_research，实际可发现范围还取决于profile和资源配置。

量化工具包自己的`qrtk_skills.runtime`保留为本地合同代码，主Agent不额外启动第二套调度器。paper_research的独立Skill声明是源工具包资产；主Agent使用自身Registry中的适配声明，二者不能靠复制文件就算接入。

## 分类

| 类别 | 资产 | 处理 |
|---|---|---|
| A 自有项目 | Agent Skills、Schema、策略模板、原创建议AGENTS、测试与客户端 | 保留来源，等所有者统一许可 |
| B 可再分发第三方 | Plotly.js及生成Viewer的MIT代码、OFL字体 | 保留许可和通知 |
| C 不随项目分发 | 用户自己的模型服务、合法论文/行情、受限外部研究函数 | 安装或输入合同，不复制受限资料 |
| D 个人全局环境 | Codex/Claude全局Skills、MCP连接、Hooks、认证、SSH配置与Cookie | 完全排除 |

本次调查未发现主Agent运行必须依赖某个私人MCP服务的证据。没有把全局MCP配置当作公开“工程依赖”。本轮使用的整理工具Skill属于作者工具，不是运行时依赖，也没有整体复制到仓库。

新Tool需参数Schema、固定handler、版本、授权和结果验收；研究定义确认和代码批准不能由模型自填。运行资源配置示例见`config/README.md`，真实Linux身份与权限必须在用户自己的环境另行验收。
