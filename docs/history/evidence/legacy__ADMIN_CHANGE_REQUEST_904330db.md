> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# 最小部署变更申请（已批准并执行）

用户明确回复“批准该最小部署范围”。2026-10-12 已完成：quantagent UID/GID 999、独立新项目和 venv、20行7字段只读快照、root 所有的 quant-agent 启动器。实际记录见 deployment.json、runtime-audit.json 和 REPORT.md；下面保留获批范围。账号和启动器位于现有实例容器中，实例重建后的持久性尚未验证。

2026-10-11。服务器只读预检确认没有可用研究账号；目标新目录不存在；原父目录为 root:root 0755。`useradd`、`groupadd`、`install`、`runuser` 已安装。现有 Docker 实例可以使用自身的 Linux UID/GID；账号与文件属于实例容器，不等于宿主机账号。实例重建后的保留机制尚需平台确认。

## 申请批准的精确范围

1. 新建专用系统账号/组 `quantagent`，不设登录密码、不开放 SSH、不加入管理员/其他共享组：

```sh
useradd --system --user-group --no-create-home \
  --home-dir /opt/jijigua-quant-agent/research_agent/var \
  --shell /usr/sbin/nologin quantagent
```

2. 只新建以下目录；不更改现有父目录、旧 Agent 或其他项目权限：

```sh
install -d -m 0750 -o root -g quantagent /opt/jijigua-quant-agent/research_agent
install -d -m 0750 -o root -g quantagent /opt/jijigua-quant-agent/research_agent/config
install -d -m 0750 -o root -g quantagent /opt/jijigua-quant-agent/research_agent/data_readonly
install -d -m 0750 -o quantagent -g quantagent /opt/jijigua-quant-agent/research_agent/.venv
install -d -m 0750 -o quantagent -g quantagent /opt/jijigua-quant-agent/research_agent/var
```

代码、可信配置和发布数据由 root 管理，组 quantagent 只读；venv 与 var 由 quantagent 写入。新文件上传到这个新目录后只对新文件设定 root:quantagent / 0640，目录 0750；不执行针对旧项目的递归 chmod/chown。已存在目标目录时先核对，不覆盖。

3. 用 quantagent 创建独立 Python 3.11 venv、安装本项目 wheel/依赖和运行测试；root 仅管理安装文件，不运行 Agent：

```sh
runuser -u quantagent -- /usr/local/bin/python3 -m venv --without-pip /opt/jijigua-quant-agent/research_agent/.venv
```

后续 pip、pytest 与 CLI 均通过 `runuser -u quantagent -- <本项目固定命令>` 执行；不安装系统运行时、不修改 cron、服务或交易程序。基础 Python 缺少 ensurepip，实际使用基础 pip 的 [--python 选项](https://pip.pypa.io/en/stable/topics/python-option/) 给无 pip 的 venv 安装依赖。依赖只装进这个 venv。

4. 从已经只读核对、root 所有且 0644 的 `/hy-tmp/update_data/today/TRD_Dalyr.csv` 发布最多20行、7个字段的小快照（Stkcd、Trddt、Opnprc、Hiprc、Loprc、Clsprc、Dnshrtrd），写入本项目 `data_readonly/`。源约2.1 MiB，日期样本为2026-10-09；不读大型因子矩阵、不读 pickle。记录源和快照 SHA-256；前后核对源指纹。复权和可获得时间标记 unknown，限数据描述。发布目录 root:quantagent 0750，快照/清单 0640；不改源文件权限。

5. 安装 root:root 管理的启动入口 `/usr/local/bin/quant-agent`（0755），内容仅调用项目 root 管理的 `deploy/launcher.py`。入口在导入 Agent 前清空无关环境、去掉附加组并切为 quantagent。

最终你们仍执行 root SSH，然后：

```sh
quant-agent chat
quant-agent ask '描述已授权日频数据的日期、字段和缺失情况，并读取5行样例。'
quant-agent status <task_id>
quant-agent logs <task_id>
```

Key 只通过隐藏输入或已明确设置的 `QRA_DEEPSEEK_API_KEY` 注入进程；不会写入服务器文件、命令参数或 Agent 日志。默认首次启动提示 Key，不需要手动切换用户。共用 SQLite 账本使用独立 task UUID、版本冲突校验；没有把共用账号称为使用者之间的隐私隔离。

## 限制与回退

非 root 与目录权限不能禁止读取服务器上所有 world-readable 文件；当前 Agent 的实际入口仍是只读资源白名单。没有任意文件/代码/Shell Tool，不宣称正式沙箱。权限完全隔绝任意未知代码需要后续加固。

未创建后台服务、未修改生产任务；测试按单任务、小样本和请求超时执行。停止使用新入口即可回退；不自动删除账号、数据或已有文件。未购买 VM。实际变更限于上述用户批准范围，没有改变现有父目录或共享原始数据权限。
