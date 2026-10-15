# 安全说明 / Security

本候选尚未公开发布，未设立独立安全邮箱。不要在公开Issue披露漏洞利用细节、密钥或真实数据；正式仓库建立后，若启用GitHub Private Vulnerability Reporting，可通过该入口报告，否则先联系仓库所有者取得私密渠道。

## 威胁边界

- 模型内容、论文内容、用户文件及生成源码都是不可信输入。
- Schema只验证参数形状；授权由独立策略与操作者配置决定。
- 不加载未知pickle。固定自产PKL的验证例外不允许通用`read_pickle`工具。
- 可信IR是封闭语法执行器；人工批准Python注册是另一条路径，**不是操作系统沙箱**。
- root broker和独立Test身份是受信管理员组件；普通研究Agent不得获得私有行情、签名材料和独立账本权限。
- HMAC签名证明持钥组件签发，不证明数值正确；独立复算仍必需。
- 前台任务及合作式预算不保证断线后继续，也不保证恶意已批准程序可被抢占。

No real credentials or private data belong in issues or CI. AST review and human approval are not a sandbox. A signed receipt proves authenticated origin, not mathematical correctness. Use synthetic reproduction for public reports and review deployment identity/ACL boundaries independently.
