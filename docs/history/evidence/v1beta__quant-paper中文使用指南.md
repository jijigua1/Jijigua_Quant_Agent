> **历史证据文档，非当前功能承诺。** 原文件的事实与当时状态按原文保留；私人路径和运行标识已脱敏。测试数字是历史记录，不代表本次归档重新运行。

# quant-paper 中文使用指南

`quant-paper` 是一个 Windows 小工具：把你电脑上的论文 PDF 上传到研究服务器，登记后就可以在 `quant-agent chat` 里用自然语言让 Agent 研究这篇论文。全程不需要输入论文编号、文件哈希或服务器路径。

> 本指南中的命令均在 2026-10-13 于本机实测通过（Windows 11，PowerShell 5.1）。

---

## 1. 准备工作（只做一次）

### 1.1 需要的软件

| 软件 | 检查方法（在 PowerShell 中输入） | 说明 |
| --- | --- | --- |
| Python 3 | `python --version` | 本机已有 `D:\anaconda\python.exe`，无需另装依赖（工具只用标准库） |
| OpenSSH 客户端 | `ssh -V` | Windows 自带。若提示找不到，打开“设置 → 应用 → 可选功能 → 添加功能 → OpenSSH 客户端” |

工具文件位于：

```
<SOURCE_ROOT>\tools\quant_paper\
```

### 1.2 让命令在任何目录都能直接使用（可选，推荐）

目前 `quant-paper` **不在**系统 PATH 中，直接输入 `quant-paper` 会提示“无法识别”。有两种用法，任选其一：

**方式 A：把工具目录加入你自己的 PATH（只影响当前 Windows 用户）**。在 PowerShell 中运行下面一行，然后**关闭并重新打开** PowerShell：

```powershell
[Environment]::SetEnvironmentVariable('Path', [Environment]::GetEnvironmentVariable('Path','User') + ';<SOURCE_ROOT>\tools\quant_paper', 'User')
```

之后就可以直接输入 `quant-paper ...`。

**方式 B：不改 PATH，每次写完整路径**：

```powershell
& '<SOURCE_ROOT>\tools\quant_paper\quant-paper.cmd' help
```

下文命令都按方式 A 书写；如果你选择方式 B，把开头的 `quant-paper` 换成 `& '<SOURCE_ROOT>\tools\quant_paper\quant-paper.cmd'` 即可。

### 1.3 信任服务器主机密钥（首次连接时）

为了防止连接到冒充的服务器，工具**不会**自动接受未知的主机密钥。第一次使用前，请在 PowerShell 手动连接一次：

```powershell
ssh -p 2222 -i "/home/example-user\.ssh\id_ed25519_gpushare" root@gpu.example.org
```

屏幕会显示服务器指纹并询问是否继续。请与服务器管理员提供的指纹核对一致后输入 `yes`，然后输入 `exit` 退出。（本机已完成过这一步，可以跳过。）

### 1.4 保存连接配置

```powershell
quant-paper setup --host gpu.example.org --port 2222 --user root --identity "/home/example-user\.ssh\id_ed25519_gpushare" --remote-command "/usr/bin/python3 -I /opt/jijigua-quant-agent/v1beta/deploy/launcher_v1.py" --staging-dir /srv/jijigua-quant-agent/v1beta_staging
```

成功时会显示：

```
已保存配置：/home/example-user\AppData\Roaming\quant-paper\config.json（不保存密码或密钥内容）
连接检查：成功。
```

配置文件只记录主机、端口、用户名和私钥**所在位置**，不保存密码或私钥内容。（本机已配置好，可以跳过。）

---

## 2. 日常使用

### 2.1 上传一篇论文

```powershell
quant-paper upload "D:\Papers\Amihud 2002 非流动性.pdf"
```

- 路径中有**空格或中文**时，请用英文双引号把整个路径括起来。
- 只接受 PDF，单个文件不超过 50 MB。

实测输出（中文文件名、含空格的路径）：

```
正在上传：技术指标 策略（1110.3383）.pdf（334 KB，SHA-256 d39ec37941b6…）
已上传并登记：技术指标 策略（1110.3383）.pdf（第1版，5页）。
在服务器运行 quant-agent chat 后说：“研究我刚上传的论文。”
```

上传速度取决于网络，实测 334 KB 约 47 秒，4.6 MB 约 4 分钟（228 秒）。网络不稳定时偶尔会出现“连接被重置”，此时服务器不会登记任何内容，直接重新上传即可。

### 2.2 一次上传多篇（2026-10-15 新增）

```powershell
quant-paper upload "D:\Papers\Amihud 2002.pdf" "D:\Papers\动量 论文.pdf"
quant-paper upload "D:\Papers\待读"
quant-paper upload "D:\Papers\*.pdf"
```

- 可以写多个文件、一个文件夹（上传其中全部 PDF，不含子文件夹），或带 `*` 的通配符。PowerShell 和 cmd 都不会替你展开 `*`，由工具展开。
- **先检查后上传**：所有文件先在本地检查（是否存在、是否 PDF、大小）。任何一个不合格，就列出原因、一个都不上传，改好后重新运行即可。
- 同一批里内容相同的文件只上传一次，会显示“跳过：……内容相同”。
- 每篇显示 `[2/5]` 这样的进度；某一篇网络失败不影响其它篇，最后汇总“成功 N 篇，失败 M 篇”。失败的那篇服务器没有登记，单独重新上传即可。

上传结束时工具会明确告诉你，“研究我刚上传的论文”指的是哪一篇：

```
在服务器运行 quant-agent chat 后说“研究我刚上传的论文。”，指的是：动量 论文.pdf（第1版）。
研究本批其它论文时，请说出文件名或标题里的词，例如“研究 Amihud 2002 那篇论文”。
```

一次上传多篇时，“刚上传的论文”只指**最后登记的一篇**；其余几篇请用文件名、作者或标题里的词来指定。

### 2.3 查看已上传的论文

```powershell
quant-paper list
```

每行一篇：最近上传时间、文件名、版本、页数、PDF 首页标题。“刚上传的论文”所指的那篇会在行尾标出 `← “刚上传的论文”指这篇`。

### 2.4 检查连接是否正常

```powershell
quant-paper status
```

正常时显示 `连接正常；已登记论文 N 篇。`

### 2.5 查看帮助

```powershell
quant-paper help
```

---

## 3. 如何确认上传成功

满足以下任一条即说明论文已在服务器登记，Agent 可以使用：

1. `upload` 最后显示 `已上传并登记：……（第N版，M页）`；
2. `quant-paper list` 的列表中出现这篇论文；
3. 在 `quant-agent chat` 里说“列出我上传的论文。”，回答中出现这篇论文。

如果上传中途失败，工具会显示“上传失败，服务器没有登记任何内容”，服务器上不会留下半个文件，直接重新上传即可。

---

## 4. 重复上传和新版本

| 情况 | 结果 |
| --- | --- |
| 同一份文件再次上传（即使换了文件名） | `内容与已登记论文相同，未重复保存：……（第1版），已记为最近上传。` 不占用额外空间；之后“研究我刚上传的论文”指的就是这篇（2026-10-15 修复：此前重复上传不会更新“最近上传”，会指向另一篇） |
| 文件名相同、内容不同（例如论文修订版） | 登记为新版本（第2版），旧版本保留 |

工具按文件内容（SHA-256）判断是否重复，与文件名无关。

---

## 5. 在 quant-agent chat 中使用刚上传的论文

2026-10-15 起可以直接在本机 PowerShell 里运行（`quant-agent.cmd` 与 `quant-paper.cmd` 在同一文件夹，按 1.2 加入 PATH 后可直接输入）：

```powershell
quant-agent chat
```

- 工具先检查连接，然后通过加密的 SSH 会话打开服务器上的研究会话。服务器会提示 `DeepSeek Key (not echoed):`，在这里输入 Key：不回显，不出现在本机命令行或日志里。
- 会话开始时会显示**会话ID**，请记下。断线后运行 `quant-agent chat --resume <会话ID>` 恢复。
- 只读查询不需要 Key：`quant-agent session_tasks <会话ID>`（任务进度）、`quant-agent status <任务ID>`。
- 下载并打开 HTML 报告：`quant-agent report <Agent给出的研究目录或报告路径>`。报告保存到 `%USERPROFILE%\Downloads\QuantAgentReports\`；给研究目录时会自动选最新一版成功的报告。
- 退出：输入 `/exit`，或按 `Ctrl+D`（会话运行在服务器的 Linux 终端里）。`Ctrl+C` 只取消当前这一轮。

也可以像以前一样先 SSH 到服务器，再在服务器上运行 `quant-agent chat`。

**macOS 用户**请看 `docs/Quant-Agent macOS中文使用指南.md`，命令与本指南不同。

然后像平常说话一样输入，例如：

- `列出我上传的论文。`
- `研究我刚上传的论文。`
- `研究Amihud那篇论文，提取非流动性因子并做完整研究。`（用作者名、标题关键词或文件名中的词都可以）
- `继续刚刚中断的论文研究。`
- `给我看Train、Validation、Test结果。`

如果论文需要替代口径（例如论文用周频、我们只有日频数据），Agent 会先用一句话问你“是否继续？”，回复 `同意` 才会执行；如果需要新写一段计算代码，Agent 会展示完整源码请你审核，回复 `同意` 才会运行。“继续”“还行吧”等说法**不会**被当作同意。

---

## 6. 常见错误与处理

| 屏幕提示 | 原因 | 处理 |
| --- | --- | --- |
| `无法将“quant-paper”项识别为 cmdlet…` | 工具目录不在 PATH | 按 1.2 方式 A 设置，或用完整路径（方式 B） |
| 上传或 `list` 报 `C:/Program Files/Git/...` 或 `C:/Program: No such file` | 曾在 Git Bash 里运行 `setup`，Git Bash 把 `/hy-tmp/...`、`/usr/bin/python3` 改写成了 Windows 路径并存进了配置 | 在 PowerShell 中重新运行一次 1.4 的 `setup`。2026-10-15 起工具优先使用 Windows 自带的 OpenSSH，但 `setup` 的参数仍建议在 PowerShell 中输入 |
| `服务器主机密钥未被信任或已变化…` | 首次连接未信任，或服务器密钥变了 | 按 1.3 手动连接并核对指纹；密钥**意外变化**时先联系管理员，不要直接覆盖 |
| `SSH 认证失败：请检查 --identity 指定的私钥及服务器授权。` | 私钥路径错误或该私钥未被服务器授权 | 检查 `--identity` 指向的私钥文件 |
| `无法连接服务器：请检查主机、端口和网络。` | 主机/端口错误或网络不通 | 用 `quant-paper status` 复查；确认端口为 2222 |
| `文件不存在：…` | 路径写错 | 在资源管理器中按住 Shift 右键文件 →“复制文件地址”，粘贴到双引号中 |
| `文件内容不是 PDF（缺少 %PDF- 文件头）。` | 文件不是真正的 PDF | 用 PDF 阅读器另存为 PDF 后再上传 |
| `文件过大（… MB），上限 50 MB。` | 超过大小限制 | 压缩 PDF 或只上传正文 |
| `连接超时：…未登记任何内容。` | 网络慢或中断 | 稍后重试；大文件可能需要几分钟 |

---

## 7. 安全说明

- 工具不保存密码或私钥内容，只记录私钥文件的位置。
- 工具始终校验服务器主机密钥（`StrictHostKeyChecking=yes`），不会自动接受陌生或变化的密钥。
- 服务器把论文当作**数据**解析，不会执行 PDF 中的任何指令、脚本或代码；损坏、加密或超大的 PDF 会被拒绝。
- 论文只存放在服务器的 Agent 论文库中，不会出现在 2026 私有评价数据或其他用户的目录里。

## 8. 存储风险：请保留本地原件

服务器论文库位于 `/srv/jijigua-quant-agent/v1beta/papers`，`/hy-tmp` 是 GPUShare 实例的本地数据盘（NVMe）。实例释放、迁移或数据盘重置后，其中的论文、研究结果和报告**不保证保留**。因此：

- 始终在你自己的电脑上保留论文原件；丢失后重新 `quant-paper upload` 即可，按内容判断，不会产生重复。
- 重要的研究报告请及时下载或备份（报告页脚也有同样提示）。
- `upload`、`list`、`status` 结束时都会显示一行提示，提醒这一点。
