# 需求功能逻辑补全

在 DSH 网页中提交软件需求，通过软件工厂 Run 执行 ReqCompleter v2.0，生成需求说明书，并保留逐轮检查材料。

| 项目 | 说明 |
|---|---|
| 插件版本 | 0.2.3 |
| 算法版本 | ReqCompleter v2.0 |
| 输入 | 自然语言软件需求 |
| 输出 | DOCX 需求说明书、检查材料 ZIP、结构化 JSON |

## 环境要求

以下环境应准备在运行 DSH 的电脑上：

- DSH 0.2.1-alpha.2，Node.js 24 或以上版本。
- 软件工厂 Runtime 0.1.0（提供 Run 任务服务）。
- Python 3.12，使用独立虚拟环境；完整依赖见 `requirements/requirements-py312.lock.txt`。
- DSH 中已配置可用模型，并有一个可写的工作区。

本插件通过 DSH 调用模型，无需单独配置 API Key。

## 新环境快速安装

以下步骤使用完整发布包。如果从 Git 克隆源码，请先完成文末“从源码构建”，再执行本节。

### 1. 准备插件文件

将 Runtime 和本插件的完整发布目录放到运行 DSH 的电脑上。例如：

```text
D:\DSH-plugins\software-factory-runtime\
D:\DSH-plugins\dsh-functional-logic-completion\
```

**两个目录可以放在不同磁盘或文件夹中，无需相邻。** 每个安装目录应直接包含 `package.json` 和 `cordis.patch.yml`。使用 TGZ 包时，先解压，再选择其中符合上述条件的目录。

本插件发布目录为 `artifacts/release/dsh-functional-logic-completion/`，安装包为 `artifacts/deepseek-ai-dsh-functional-logic-completion-0.2.3.tgz`。新电脑使用发布包即可，无需重新构建或单独安装 SDK。

### 2. 准备 Python 环境

在 PowerShell 中执行。请将以下路径替换为实际安装位置：

```powershell
Set-Location 'D:\DSH-plugins\dsh-functional-logic-completion'
node .\scripts\prepare-python.mjs 'C:\Python312\python.exe'
```

脚本会创建虚拟环境、安装锁定依赖并检查环境，需要能够访问 PyPI。检查输出包含 `"ready": true` 即表示环境就绪。新电脑应重新创建环境，不复制旧电脑的 `.venv`。

**不需要再手工执行 `pip install`，也不需要激活 venv。** 此脚本已依次执行 `python -m venv`、`python -m ensurepip --upgrade`、`python -m pip install -r requirements/requirements-py312.lock.txt` 和环境探测。依赖包括 pandas、python-docx、numpy、lxml 等；任务运行时不会临时安装依赖。

脚本默认在插件目录创建 `.venv`，插件会自动使用其中的 Python，**无需填写 `pythonPath`**。如果不知道基础 Python 路径，安装了 Windows Python Launcher 时可执行：

```powershell
py -3.12 -c "import sys; print(sys.executable)"
```

Linux 使用相同发布包，先准备 Python 3.12 的 venv/ensurepip 支持，在发布目录执行：

```bash
node scripts/prepare-python.mjs /usr/bin/python3.12
```

同样默认使用插件目录的 `.venv`，无需修改配置。基础 Python 路径按实际位置调整，不将 Windows 虚拟环境复制到 Linux。

### 3. 在 DSH 中安装

1. 打开 DSH 网页，进入侧栏 **插件 → 添加插件**。
2. 输入 Runtime 的完整目录路径，按提示安装并启用。
3. 同样安装并启用“需求功能逻辑补全”。
4. 保持默认配置，根据管理器提示重启 DSH。

两个插件应安装到同一套 DSH 运行配置中（profile），即在同一个 DSH 网页所管理的配置环境中安装。使用本地目录安装时，应保留安装目录及其位置。

如果浏览器与 DSH 分别运行在两台电脑上，安装路径指 **DSH 所在电脑** 的路径，浏览器不会上传本机目录。

### 4. 配置（默认无需修改）

按上面的步骤准备 Python 后，直接使用默认配置即可，**不需要手改 YAML，也不需要填写 `pythonPath`**。默认使用插件目录下的 `.venv`，最多检查 5 轮，同时运行 1 个任务；模型在 DSH 中选择。

仅在需要自定义时，修改当前 DSH profile 的 `cordis.patch.yml` 中对应插件条目的 `config`，保存后重启 DSH：

- 虚拟环境放在其他目录：设置 Req 的 `pythonPath` 为该环境解释器的绝对路径。
- 调整轮次或并发：设置 Req 的 `maxIterations` 或 `maxConcurrent`。
- 调整超时：设置 Runtime 的 `defaultTimeoutMs` 或 `modelTimeoutMs`。

SDK 随本插件打包，Runtime 插件仍需单独安装。插件启用且 Python 检查通过后自动登记入口，无需填写 Tool 允许名单或修改 HugeGraph。

### 5. 日常启动

**只启动 DSH，不需要手动启动 Python、worker.py 或 Gradio，也无需每次运行环境准备脚本。** 插件启用时检查 Python，每次任务自动启动自己的 Python 进程。

如果使用 DSH 源码部署，在已经完成自身依赖准备的 **DSH 主项目目录** 执行：

```powershell
Set-Location 'D:\work\DSH-Softwarefactory'
pnpm.cmd dsh web
```

路径替换为本机 DSH 主项目位置，不是在本插件目录运行。若使用已部署的 DSH 服务，沿用其正常启动方式。Windows 上使用 `pnpm.cmd` 可以避免 PowerShell 的 `.ps1` 执行策略问题。

插件安装成功、Python 环境检查通过和真实业务任务成功是三项独立检查。环境探测不证明工作区可写，下面的入口查询也不会执行完整算法。

## 使用

在 DSH 网页选择一个可写工作区，进入普通聊天。

### 检查安装

向 DSH 发送：

> 请调用 sf_runtime_get_tool_contract，参数为 {"toolId":"sf_functional_logic_completion_v2_0"}。仅检查接口，不启动任务。

返回 `supportsRun: true` 表示入口可由 Run 调用。这一步不执行补全算法。

### 启动任务

要求 DSH 调用 `sf_runtime_run_tool`，使用以下参数，并将示例需求替换为实际内容：

```json
{
  "toolId": "sf_functional_logic_completion_v2_0",
  "input": {
    "software_intro": "图书借阅系统：管理员维护图书，读者借阅和归还图书，并查询自己的借阅记录。"
  },
  "timeoutMs": 3600000
}
```

`software_intro` 为必填需求文本，不可为空，最多 100000 字符。成功受理后返回 `runId`；完整补全需要调用模型，可能耗时较长。

任务开始时显示“启动准备，0%”，随后显示实际阶段及估算百分比。启动准备占 0–2%，初始分析占 2–38%，迭代补全按配置的迭代上限分配 38–78%，需求正文占 78–92%，图文生成占 92–98%，打包登记占 98–100%。百分比不倒退；提前收敛或跳过可选步骤时会向前跳，等待单次模型响应时保持当前值。

百分比表示流程进度估算，不代表模型计算量、剩余时间或需求完整程度。100% 表示插件完成文档和材料登记；任务最终是否成功仍以 Run 的状态为准。

Python 由 DSH 作为受信任的服务端后端托管，使用 DSH 服务账户已有的权限，不额外建立文件沙箱或修改目录 ACL。每次任务都由实际 Python 子进程写入任务输入，成功后才确认启动准备完成；健康检查通过不代表任务目录可写。`probeTimeoutMs` 同时控制环境检查和 Python 启动确认超时，默认为 15000 毫秒。

默认使用发起聊天的模型。如需内部使用另一模型，在启动参数顶层增加 `model: {"provider":"实际提供方ID","model":"实际模型ID"}`。模型必须已在 DSH 中配置。任务启动后模型保持固定，主聊天模型不会被切换。

### 查看结果或取消任务

将下面参数中的 ID 替换为任务返回的实际值：

| 操作 | Tool | 参数 |
|---|---|---|
| 查看状态和结果 | `sf_runtime_get_run` | `{"runId":"任务ID"}` |
| 等待任务更新 | `sf_runtime_wait_run` | `{"runId":"任务ID","waitMs":15000}` |
| 获取文件下载链接 | `sf_runtime_get_artifact` | `{"runId":"任务ID","artifactId":"文件ID"}` |
| 取消任务 | `sf_runtime_cancel_run` | `{"runId":"任务ID"}` |

文件 ID 从任务结果的 `result.files` 中获取。所有业务执行均通过 Run 发起，不直接调用业务 Tool。

## 交付文件

| 文件 | 内容 |
|---|---|
| `requirements.docx` | 补全后的软件需求说明书 |
| `checks.zip` | 输入、实体与用例、E-R/CRUD、每轮检查和快照、PlantUML、日志等检查材料 |
| `result.json` | 结构化结果、迭代次数及收敛情况 |

文件保存在发起聊天所属工作区：

```text
<工作区>/outputs/runs/<runId>/
```

最终文件位于 `final/`，中间材料位于 `intermediate/` 和 `snapshots/`。失败或取消后保留已有材料，任务结束不会自动删除文件。

文档生成成功与算法收敛分别记录。收敛不代表需求已经完整或正确，正式使用前仍应审阅文档。

## 常见问题

| 问题 | 处理方法 |
|---|---|
| 找不到 Runtime 工具 | 确认 Runtime 已在当前 DSH 配置环境安装并加载 |
| `PROTOCOL_UNSUPPORTED` | 确认 Req 已加载、Python 检查通过，入口名填写正确且当前会话可见 |
| 旧的 `TOOL_NOT_ALLOWED` | 检查是否仍加载旧 Runtime，更新后重启 DSH；当前版本无需允许名单 |
| `WORKSPACE_REQUIRED` | 选择真实工作区后再发起任务 |
| `MODEL_REQUIRED` / `MODEL_UNAVAILABLE` | 检查 DSH 模型配置或启动参数中的模型 ID |
| Python 环境错误 | 检查 `pythonPath`，并重新运行环境准备脚本 |
| `READ_ONLY` | 将发起会话切换为具有工作区写入许可的模式 |
| `PYTHON_START_TIMEOUT` | Python 未及时确认任务目录写入；检查解释器与目录权限，必要时调整 `probeTimeoutMs` |
| 任务目录写入被拒绝 | 检查 DSH 服务账户对工作区的现有写入权限；插件不自动提权或修改 ACL |

## 从源码构建

Git 仓库不包含 `lib/`、`artifacts/`、`node_modules/`、虚拟环境、测试产物和本地 Skill。刚克隆的源码不能直接作为已构建插件安装。

需要一份兼容、已按 DSH 自身说明准备好依赖的 DSH 源码。当前构建脚本复用其构建依赖，SDK TGZ 保留在本仓库的 `vendor/`。在本插件源码目录执行：

```powershell
Set-Location 'D:\work\DSH-Functional-Logic-Completion-Plugin'
$env:DSH_SOURCE = 'D:\work\DSH-Softwarefactory'
node .\scripts\build.mjs
node .\scripts\pack.mjs
```

路径按实际位置修改；未设置 `DSH_SOURCE` 时默认寻找相邻的 `DSH-Softwarefactory` 目录。无需在本插件执行通用的 `npm install` 来代替上述构建流程。

完成后使用 `artifacts/release/dsh-functional-logic-completion/`，按前面的步骤准备 Python、安装及配置。构建和打包不会替你安装 Runtime，也不会创建 Python 环境。

## 升级

使用 DSH 插件管理器更新发布包，并按提示重启。安装包不包含虚拟环境，升级时可继续使用单独配置的 Python 环境。
