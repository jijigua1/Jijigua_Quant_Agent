# 贡献与维护 / Contributing

1. 从公开候选或正式发布标签建立自己的分支，不把内部工作树自动同步到公开仓库。
2. 先写最小复现；数学改动需要独立期望值，不以同一函数调用两次作为复算。
3. 保留Schema、授权、时间信息及缺失语义。新Tool需要封闭参数、固定handler、版本与验收。
4. 参数、IR数值语义、标签或分组规则变化必须生成新定义/合同版本；不能静默复用旧缓存。
5. 新增第三方代码、字体、JS或样例时附来源、版本与许可证。不要附论文全文或真实行情。
6. 本地运行受影响pytest、`python tools/release_audit.py`和文档链接检查。完整CI结果未运行时写明。
7. 同步README/CHANGELOG与技术文档；PR必须区分离线、真实API、真实数据、预发布和生产证据。
8. 不在Issue上传Key、真实会话、私有地址或未脱敏日志。安全问题见SECURITY.md。

English: submit a focused change with a reproduction, independent numerical expectations and affected regression tests. Preserve authorization and temporal contracts. Include provenance/licence information for third-party content. Never contribute credentials, private datasets, complete copyrighted papers or raw user conversations. Changing computation semantics requires a versioned definition and cache boundary. Report exactly which environments and tests were run.
