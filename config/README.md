# 配置模板与真实配置边界

- `src/research_agent/resources/agent.toml`：原Provider模板，默认Mock；官方模型与凭据环境引用明确，未包含Key。
- `src/research_agent/resources/policy.toml`：离线默认拒绝策略，不自动开放真实资源。
- `client.example.json`：只说明客户端字段；实际使用`quant-paper setup`生成当前用户配置。
- 研究数据配置不要从内部生产复制。运行`examples/offline_research.py`会生成与实际读取器相符的`resources.json`、`research.json`和合成发布manifest，可作为合法自有数据适配的结构参考。
- 生产真实资源须由操作者核对日期/字段/单位/可得时间/SHA/权限并审批。不能将SHA全0或示例路径填进去便声称可用。
- 独立Test的身份、私有数据、Key、回执注册及预算配置不提供可直接启用的真实实例模板。`deploy/configure_v1.py`仅是需管理员审阅的布局示例，默认关闭授权。
- 不从`.env.example`自动载入秘密。优先隐藏输入，不用命令行参数传Key。

客户端路径与研究资源路径分别管理；本机路径不会自动成为服务器可读文件。
