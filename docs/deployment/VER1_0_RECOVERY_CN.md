# Quant-Agent ver1.0 恢复部署手册

## 范围与版本

此包来自 2026-10-20 已部署 ver1.0 的只读副本。生产声明清单 SHA256 为 `dff173f90c610cc84bda862f56f7465408e5399415541eea787254d1260ea25b`；它与公开包清单不同，不能互换。公开路径统一改为 `/opt/jijigua-quant-agent` 与 `/var/lib/jijigua-quant-agent`。逐项来源和变换记录在 `provenance/VER1_0_SOURCE.json`。服务器原始 README 和旧安装器有历史文字，产品状态以本手册和来源记录为准。

本次不部署服务器、不修改业务代码语义、不运行真实模型或真实 2026 评价。933 项为部署方历史记录，后续本机复制/打包验收单独记录，不冒充重新执行的独立全量验收。

## 必须准备的四部分

| 部分 | 来源 | 缺少时的影响 |
|---|---|---|
| 代码、上传器、审定配置模板、依赖锁 | 本 Git 仓库 | 无法启动程序 |
| host / research / resources / broker / evaluator 实际配置，UID/GID 与权限 | 操作者私有备份 | 路径、身份、数据或评价器无法绑定 |
| PDF、registry、缓存、会话/审批/预算 SQLite、全部研究、2026 ledger/回执/audit及原签名密钥 | 操作者一致性备份 | 无法恢复原论文、历史任务或验证旧回执 |
| Train / Validation 发布、manifest、数据轴及受控 Test 数据源 | 有权使用的私有数据备份 | 源码不能替代行情，不能产生完整研究 |

**GitHub 单独不能重建私有行情、历史论文及签名身份。** 私有配置和数据不得提交到公开仓库。API Key 由用户启动时输入，不写入源码、命令参数或备份。

## 1. 核验并暂存代码

```bash
git clone https://github.com/jijigua1/Jijigua_Quant_Agent.git
cd Jijigua_Quant_Agent
python tools/recovery_bundle.py verify
python tools/recovery_bundle.py stage --output ../quant-agent-ver1.0-stage
```

输出必须是不存在且位于 checkout 外的目录。工具先核验清单；失败就停止。不会覆盖旧程序、创建空论文库或切换命令。

拥有原始私有快照时，可恢复逐字节原始代码和配置：

```bash
python tools/recovery_bundle.py stage --output ../quant-agent-exact-stage \
  --private-archive /secure/production_code.tar.gz \
  --archive-sha256 bbf2e6ebbe3fc7480cee1d02f7367ead0fc550973f13c777e73f206cce1a920c \
  --private-manifest /secure/production_manifest.json
```

该模式先逐项核验路径、大小、SHA，拒绝链接、重复成员、越界及现有目标。私有快照包含真实配置，必须保存在非公开位置；本次代码快照不包含论文、研究状态或行情。

## 2. 准备 Linux 与 Python

生产采集环境为 CPython 3.11.10。公开锁文件延续此前审查后的安全版本；精确生产依赖另见 `provenance/VER1_0_DEPENDENCIES.json`，不可将二者混称为完全相同环境。使用独立虚拟环境：

```bash
python3.11 -m venv /absolute/new-code-root/.venv
/absolute/new-code-root/.venv/bin/python -m pip install -r requirements.lock -r requirements-research.lock -r requirements-paper.lock
/absolute/new-code-root/.venv/bin/python -m compileall -q src
```

把代码放在 Linux 本地文件系统而非 Windows 共享盘上，保留权限。系统需 `libseccomp.so.2`、OpenSSH；FinalShell ZMODEM 还需 lrzsz，中文图表需可用 CJK 字体。Windows/macOS 是上传客户端；Linux 才是自主算法隔离执行环境。不得把 Windows skip 写成 Linux PASS。

## 3. 恢复数据和可信配置

优先恢复既有专用用户及**原 UID/GID**，不要把历史文件统一 chown 给 root 或让 Agent 运行于 root。生产边界为 `quantagent`、`quanteval`、`quantpub` 及 `quantdata`。

模板位于 `deploy/restore_templates/`；它们是参考，不会自动生效。原生产运行配置有以下关系：

- 代码与 launcher、broker、evaluator 的 Python 必须全部指向同一 ver1.0，避免导入 v1beta/v1rc 旧代码。
- 研究输出位于 ver1.0 的 research_runs；`legacy_workspaces` 保留旧研究入口。
- 原论文库、state 与预算 campaign 沿用旧 v1beta 数据路径；不能创建同名空库代替恢复。
- 代码目录中的 `reports`、`papers`、`inbox`、`state` 是便利符号链接，分别指向研究输出、旧论文库、受控 staging/inbox 和旧 state。源代码归档刻意不解包符号链接；数据恢复并校验后，依据私有布局记录重新创建这四个链接，不允许链接指向未验证位置。
- 签名回执、评价账本和密钥沿用原 rolling 可信域。恢复旧回执必须恢复原密钥，不能重新生成后宣称旧回执有效。
- host.json、broker.json、入口及代码由 root 控制、Agent 不可写。评价快照/requests 为 root:quanteval 0750；receipts 为 root:quantagent 0750，回执文件 0440；签名密钥及 evaluator.json 为 root:quanteval 0440；评价 ledger 仅评价身份可写。论文/state/研究数据由 quantagent 管理。
- 所有配置内资源 manifest、发布 SHA、输入轴和路径必须校验。恢复已有预算 DB 和 campaign，保留已消费请求和单位，不重置。

**一致性备份必须在维护窗口完成。** 活跃 SQLite 不能只复制主文件忽略 WAL；使用 SQLite backup API 或在正常退出写入者后打包。此次只读采集未停止生产，不是业务数据一致性备份。

## 4. 健康检查、切换和回滚

先在新目录完成依赖导入、来源指纹、Skill 哈希、quant_source 哈希及合成回归；使用独立数据目录，不能以生产库作安装测试。核对三个入口 agent / quant-agent / quant-paper 都使用同一新代码根。

历史 `deploy/selftest_rolling.py`、`regression_v1.py` 也带有旧布局常量，不能直接当 ver1.0 新机验收入口。当前源码的公开离线测试可用 `python tools/run_public_tests.py --shard all`，需非 root 身份和独立临时目录；这些测试不包含私有论文重放。

安装依赖后，先用真实 CLI 做不连接模型、也不读取行情的健康检查。下面的检查目录必须预先确认不存在；用新目录运行，不能填写生产 state：

```bash
install -d -o quantagent -g quantagent -m 0700 /var/tmp/quant-agent-recovery-check
runuser -u quantagent -- /absolute/new-code-root/.venv/bin/python -I \
  /absolute/new-code-root/deploy/run_v1.py \
  --state-dir /var/tmp/quant-agent-recovery-check/state \
  --provider mock --profile offline demo
```

预期状态是 `COMPLETED`、`execution_mode=offline_mock`。它只验证安装、Skill 哈希和离线工作流，不代表真实模型、行情或 2026 评价通过。论文 registry、数据 manifest、签名身份与现有报告必须另行只读核对；确认这些数据已恢复，才执行 `quant-paper list`，防止错误指向不存在的论文库。

切换前正常结束空闲会话；正在研究的进程先等待完成。保存旧入口内容、配置、代码清单和业务备份。只有检查通过，才由操作者原子更新入口到新目录；不要运行历史 `deploy/install_v1.sh`、`configure_v1.py` 或 `release_tool.py apply --production`，这些脚本绑定旧布局。

启动检查无需调用模型：`quant-paper list`、`agent where`，只读打开已完成报告并核对三阶段及回执。真实 API 与真实 Test 是独立操作，不能作为恢复脚本隐式步骤。

回滚时先正常结束新版本空闲会话，原子恢复旧入口及对应配置；恢复与其匹配的代码、Skill/工具绑定、数据和签名域。若新版本已写业务数据，必须评估格式兼容，不能仅换 Python 文件。保留切换前后 SHA、操作记录与备份，禁止抹掉新研究来制造回滚成功。

## 5. 终端操作

服务端：`quant-paper list`、`quant-agent chat`；FinalShell 可使用 `quant-paper upload --mode zmodem`。其他 SSH 终端先上传到受控 staging，再调用服务端登记，不得直接丢进 PDF 库绕过登记。

客户端：复制 `client/`，按 `client/quant_paper.py --help` 使用 SSH 身份认证和本地 PDF 路径；macOS/Linux 用 `./quant-paper`，PowerShell 用 `.\quant-paper.ps1`。主机、端口和身份使用个人配置，不能把本机文件路径输入远程 shell。客户端不保存 API Key。平台测试证据与真实桌面终端测试须分别标注。

## 验收状态

本次服务器操作仅只读复制；本机验证证据见 `provenance/VER1_0_PACKAGING_CHECKS.json`。公开自动化只使用合成数据，不带私有论文 fixture。未执行的真实恢复、真实模型及目标 GPUShare 生产切换不能记为 PASS。
