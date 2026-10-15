> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Phase 2-C 最小目录申请

只读检查：`/srv/jijigua-quant-agent/integration_tests/phase2c` 不存在。现有 quantagent UID/GID 999；父 integration_tests 由 root 管理，不能由 Agent 自行扩权。

申请仅执行：

```sh
install -d -o 999 -g 999 -m 0700 /srv/jijigua-quant-agent/integration_tests/phase2c
```

执行前确认目标不存在、各父目录不是符号链接且 integration_tests 已存在；仅创建这一个目录。后续 quantagent 在其内部新建独立 run_id 保存测试证据。

不修改父目录权限，不递归 chmod/chown，不改共享行情、原因子、其他研究员项目、生产任务或账号。研究成果继续使用已批准 research_runs。本轮不请求额外数据发布。
