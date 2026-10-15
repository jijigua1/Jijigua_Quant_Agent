> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# Quant-Agent macOS 中文使用指南



适用于 macOS（Apple Silicon M 系列；Intel 芯片同样适用但尚未实机验证）。本指南中的命令都在 **终端（Terminal）或 iTerm2** 中输入，默认 shell 为 zsh。**Windows 用户请看 `docs/quant-paper中文使用指南.md`**，两边命令不同，不要混用。



> 验证状态（2026-10-15）：`MACOS_IMPLEMENTED / MACOS_NATIVE_E2E_NOT_VERIFIED`。代码已按 macOS 规则实现，并在 Linux（POSIX）与 Windows 上通过自动化测试；尚未在真实 Mac 上端到端运行。第 11 节是请你在 Mac 上执行的验收清单。



---



## 0. 先理解：本机和服务器分别做什么



| 位置 | 做什么 | 保存什么 |

| --- | --- | --- |

| 你的 Mac | 运行两个小命令：`quant-paper`（上传论文）和 `quant-agent`（连接研究会话、下载报告） | 只有一份连接配置（`~/.config/quant-paper/config.json`，不含密码和私钥内容）和你下载的报告副本 |

| GPUShare 服务器 | 论文库、因子计算、Train/Validation 研究、2026 受控评价、HTML 报告 | 所有研究成果 |



Windows 和 Mac 连接的是**同一台服务器、同一个论文库**。在哪个系统上操作，都不会改变论文的数学定义、研究参数或评价合同。



---



## 1. 环境准备（只做一次）



### 1.1 检查 Python 和 SSH



```bash

python3 --version

```



需要 3.9 或更新版本。如果提示找不到 python3，运行下面的命令安装 Apple 命令行工具（自带 python3），完成后重新打开终端：



```bash

xcode-select --install

```



macOS 自带 OpenSSH，不需要安装任何 Windows 软件、Anaconda 或 PowerShell：



```bash

ssh -V

```



客户端只用 Python 标准库，**不需要 pip 安装任何依赖**。



### 1.2 获取客户端文件



把仓库中的整个文件夹 `agent_v1beta/tools/quant_paper/` 复制到 Mac 上，例如 `~/QuantAgent/quant_paper/`。需要的文件：`quant_paper.py`、`quant_agent.py`、`install_macos.sh`。



### 1.3 安装命令



```bash

sh ~/QuantAgent/quant_paper/install_macos.sh --add-path

```



```bash

source ~/.zshrc

```



预期输出类似：



```

已安装：/Users/<你>/.local/bin/quant-paper、/Users/<你>/.local/bin/quant-agent（python3：Python 3.9.6，arm64）

已把 PATH 设置写入 ~/.zshrc。请运行：source ~/.zshrc（或重新打开终端）。

```



安装脚本不需要 sudo，只在 `~/.local/bin` 写两个小启动文件；加了 `--add-path` 时还会在 `~/.zshrc` 末尾追加一行 PATH 设置，重复运行也不会重复追加。验证：



```bash

quant-paper version

```



```bash

quant-agent version

```



---



## 2. SSH 配置



### 2.1 私钥



把管理员给你的私钥放到 `~/.ssh/`，并把权限设为只有自己可读（权限过宽时 ssh 会拒绝使用）：



```bash

chmod 600 ~/.ssh/id_ed25519_gpushare

```



### 2.2 首次连接：核对服务器指纹



为防止连到冒充的服务器，工具**不会**自动接受未知的主机密钥。第一次请手动连接一次：



```bash

ssh -p 2222 -i ~/.ssh/id_ed25519_gpushare root@gpu.example.org

```



屏幕会显示服务器指纹，与管理员提供的指纹核对一致后输入 `yes`，再输入 `exit` 退出。



### 2.3 保存连接配置



```bash

quant-paper setup --host gpu.example.org --port 2222 --user root --identity ~/.ssh/id_ed25519_gpushare

```



成功时显示 `连接检查：成功。`。只保存主机、端口、用户名和私钥**所在位置**，配置文件权限自动设为 600。



---



## 3. 上传论文



### 3.1 单篇



```bash

quant-paper upload ~/Documents/Papers/paper.pdf

```



路径含空格或中文时，用英文双引号括起来。**引号里请用 `$HOME`**（`~` 在引号里不会被 zsh 展开；本工具也会自己展开 `~`，两种写法都能用）：



```bash

quant-paper upload "$HOME/Documents/论文资料/动量因子.pdf"

```



### 3.2 多篇、整个文件夹、通配符



```bash

quant-paper upload ~/Documents/Papers/a.pdf ~/Documents/Papers/b.pdf

```



```bash

quant-paper upload ~/Documents/Papers/

```



```bash

quant-paper upload ~/Documents/Papers/*.pdf

```



- 文件夹：上传其中全部 PDF，不含子文件夹。以 `.` 开头的隐藏文件（包括 macOS 在移动硬盘、网络盘上生成的 `._xxx.pdf`）会自动跳过。

- 通配符：不加引号时由 zsh 展开；如果一个都没匹配到，zsh 会直接报 `no matches found`，并不会运行本工具。路径里有空格或中文时，可以把整个路径（连同 `*`）放进引号，由本工具展开：`quant-paper upload "$HOME/Documents/论文资料/*.pdf"`；也可以直接写文件夹。

- 先检查后上传：任何一个文件不合格（不存在、不是 PDF、超过 50 MB），就列出原因、一个都不上传。

- 按内容（SHA-256）去重：同一批里内容相同的只上传一次；服务器已有的不重复保存，但会记为最近上传。

- 每篇显示 `[2/5]` 这样的进度；单篇网络失败不影响其它篇，最后汇总成功和失败数。



上传结束时会写明“研究我刚上传的论文”指哪一篇：



```

运行 quant-agent chat 后说“研究我刚上传的论文。”，指的是：动量因子.pdf（第1版）。

```



**中文文件名**：macOS 经常用“分解形式”（NFD）保存中文、日文等文件名。工具会先统一为标准形式（NFC）再登记，所以服务器上看到的名字和 Windows 上传的一致，按名字查找也不受影响。



### 3.3 查看论文库



```bash

quant-paper list

```



```bash

quant-paper status

```



`list` 会在“研究我刚上传的论文”所指的那一行末尾标出 `← “刚上传的论文”指这篇`。



---



## 4. 开始研究



```bash

quant-agent chat

```



- 工具先做一次连接检查；有问题会直接用中文说明原因（见第 9 节），不会进入半连接状态。

- 连接后，**服务器**会提示 `DeepSeek Key (not echoed):`。在这里输入 Key：经加密的 SSH 会话直接送到服务器，不出现在本机命令行、环境变量或日志里，也不会写进上传的 PDF。

- 会话开始时会显示 **会话ID**，请记下来，断线后要靠它恢复。



然后像平常说话一样输入，例如：



- `列出我上传的论文。`

- `研究我刚上传的论文。`

- `研究Amihud那篇论文，提取非流动性因子并做完整研究。`

- `给我看Train、Validation、Test结果。`

- `刷新这项研究的2026结果。`（查看已有报告是只读的；只有明确要求刷新时才会重新做受控 2026 评价）



需要替代口径或需要运行新代码时，Agent 会先问你，回复 `同意` 才会执行。



会话中常用命令：`/session`（会话ID）、`/tasks`（本会话任务与进度）、`/history`、`/help`。



## 5. 查看进度



会话里输入 `/tasks`。也可以在另一个终端窗口只读查询，不需要 Key：



```bash

quant-agent session_tasks <会话ID>

```



```bash

quant-agent status <任务ID>

```



## 6. 查看 HTML 报告



研究完成后，Agent 会给出服务器上的报告路径（例如 `/srv/jijigua-quant-agent/v1beta/research_runs/2026-10-15/…/reports/report.html`）。把它下载到本机并用默认浏览器打开：



```bash

quant-agent report /srv/jijigua-quant-agent/v1beta/research_runs/2026-10-15/10-30-00_momentum_20d/reports/report.html

```



也可以只给**研究目录**，工具会自动下载最新一版成功的报告。规则和服务器上的 `reports/LATEST_REPORT.html` 相同：2026 刷新失败的版本不会遮住之前成功的版本。



```bash

quant-agent report /srv/jijigua-quant-agent/v1beta/research_runs/2026-10-15/10-30-00_momentum_20d

```



报告保存在 `~/Downloads/QuantAgentReports/`，这只是本地副本。只能下载服务器研究目录里的文件，其它路径会被拒绝。报告是单个 HTML 文件，图表可离线交互，也可在报告里导出 PNG/SVG/PDF。



## 7. 恢复会话



断线、合上笔记本或关闭终端后：



```bash

quant-agent chat --resume <会话ID>

```



不记得 ID 时，可以先查看某个会话（只读）：



```bash

quant-agent session <会话ID>

```



研究结果按会话隔离：新会话不能直接读取其它会话的研究。要找回，可以：



- 用 `--resume` 回到原会话；

- 或用 `quant-agent report <研究目录>` 直接下载报告。



## 8. 安全退出



在会话中输入 `/exit` 或按 `Ctrl+D`。`Ctrl+C` 只取消当前这一轮，不会退出会话。



---



## 9. 常见错误



| 屏幕提示 | 原因 | 处理 |

| --- | --- | --- |

| `zsh: command not found: quant-paper` | `~/.local/bin` 不在 PATH | 运行 `source ~/.zshrc`，或重新运行 `install_macos.sh --add-path` |

| `找不到 python3` | 未安装命令行工具 | 运行 `xcode-select --install` |

| `服务器主机密钥未被信任或已变化…` | 首次连接未核对指纹，或服务器密钥变了 | 按 2.2 手动连接并核对；密钥**意外变化**时先联系管理员，不要直接删除 `~/.ssh/known_hosts` 里的记录 |

| `SSH 认证失败…（私钥权限应为 600）` | 私钥路径错误、未授权或权限过宽 | 运行 `chmod 600 ~/.ssh/<私钥>`，并检查 `--identity` |

| `私钥文件权限过宽，ssh 拒绝使用` | 私钥权限过宽 | 运行 `chmod 600 <私钥路径>` |

| `无法连接服务器…` | 主机或端口错误，或网络不通 | 用 `quant-paper status` 复查，端口为 2222 |

| `网络连接中断：服务器没有登记本次内容` | 上传途中断网 | 重新上传；按内容去重，不会重复登记 |

| `SSH 连接中断（退出码 255）` | 会话途中断线 | 用 `quant-agent chat --resume <会话ID>` 恢复 |

| `zsh: no matches found: …*.pdf` | 通配符没匹配到文件（zsh 在运行工具前就报错） | 检查路径，或改为上传文件夹 |

| `没有匹配的 PDF 文件` / `文件夹里没有 PDF` | 引号里的通配符或文件夹中没有 PDF | 检查路径 |

| `注意：服务器端版本较旧…` | 服务器尚未升级，重复上传不会更新“最近上传” | 在 chat 里用文件名指定论文，或请管理员升级服务器 |

| `只能下载服务器研究目录…里的报告` | 报告路径不在研究目录下 | 复制 Agent 给出的完整路径 |



## 10. 存储与备份风险



服务器的论文库、研究成果和报告都在 `/hy-tmp`（GPUShare 实例的本地 NVMe 数据盘）上。实例释放、迁移或数据盘重置后**不保证保留**。



- 始终在 Mac 上保留论文原件。丢失后重新上传即可，不会重复。

- 重要报告请及时用 `quant-agent report` 下载备份。



## 11. Mac 实机验收清单（请在真实 Mac 上执行）



依次执行，并把每一步的输出发给开发方。“预期”一栏是通过标准。



| # | 命令 | 预期 |

| --- | --- | --- |

| 1 | `uname -m; python3 --version; ssh -V` | `arm64`（M 系列）或 `x86_64`（Intel）；Python ≥ 3.9 |

| 2 | `sh ~/QuantAgent/quant_paper/install_macos.sh --add-path && source ~/.zshrc && quant-paper version && quant-agent version` | 两个命令都显示版本 1.1.0 |

| 3 | `quant-paper setup --host gpu.example.org --port 2222 --user root --identity ~/.ssh/id_ed25519_gpushare` | `连接检查：成功。`；`ls -l ~/.config/quant-paper/config.json` 显示 `-rw-------` |

| 4 | `mkdir -p "$HOME/Documents/论文 测试" && cp <任意两篇PDF> "$HOME/Documents/论文 测试/"`，再复制其中一篇改名为 `副本.pdf` | 准备好 3 个文件，其中 2 个内容相同 |

| 5 | `quant-paper upload "$HOME/Documents/论文 测试/"` | 一行“跳过：…内容相同”；`[1/2]`、`[2/2]` 进度；“成功 2 篇，失败 0 篇”；写明“刚上传的论文”指哪一篇 |

| 6 | `quant-paper upload "~/Documents/论文 测试/*.pdf"` | 整个路径加引号时，`~` 和 `*` 都由工具展开，结果同上（服务器已有的显示“已记为最近上传”） |

| 7 | `quant-paper list` | 第 5、6 步的论文出现在列表中，最后一行有“刚上传的论文”标记 |

| 8 | 关闭 Wi-Fi 后运行 `quant-paper status`，再打开 Wi-Fi | 显示中文的“无法连接服务器…”，没有 Python 报错堆栈 |

| 9 | `quant-paper setup --identity ~/.ssh/不存在的私钥` | 显示 `私钥文件不存在`；之后用正确私钥重新 setup |

| 10 | `quant-agent chat`，输入 Key，再输入 `研究我刚上传的论文。` | 显示会话ID；Agent 定位到第 7 步标记的那篇；最终完成研究，或给出准确的阻断原因 |

| 11 | 会话中输入 `/tasks`，然后输入 `/exit` | 显示任务进度；正常退出 |

| 12 | `quant-agent chat --resume <第10步的会话ID>`，输入 `给我看Train、Validation、Test结果。` | 回到原会话，给出结果和报告路径 |

| 13 | `quant-agent report <第12步给出的研究目录>` | 报告下载到 `~/Downloads/QuantAgentReports/`，并在默认浏览器中打开，图表可交互 |



全部通过后，状态可改为 `MACOS_NATIVE_E2E_VERIFIED`（标注芯片类型）。Intel Mac 需要单独执行一遍。

