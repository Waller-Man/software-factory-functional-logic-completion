# 需求功能逻辑补全 v2.1

DSH 后端插件，通过软件工厂 Run 执行需求补全，将功能拆成“大功能 → 子功能”，由 AI 生成各层用例图和末级子功能活动图，在服务端本地渲染后插入 Word 文档。

| 项目 | 值 |
|---|---|
| 插件包 | `@deepseek-ai/dsh-functional-logic-completion-v2-1`，0.3.0 |
| 插件显示名称 | 需求功能逻辑补全 v2.1 |
| 业务版本 | ReqCompleter v2.1 |
| 执行入口 | `sf_functional_logic_completion_v2_1` |
| 交付 | 图文需求说明书、功能树 JSON、图文件 ZIP、检查材料 ZIP、结果 JSON |

此包使用独立的插件 ID、服务名和 Tool，可与旧 v2.0 插件同时安装。v2.0 补全核心保持原样，新增功能在其完成后执行。

## 新环境快速启动

以下操作在 **DSH 服务端电脑** 上进行，不是在远程浏览器所在电脑上。

### 1. 准备环境

- 兼容的 DSH 0.2.1-alpha.2、Node.js 24+。
- 在同一 DSH profile 中安装并启用软件工厂 Runtime 0.1.0；SDK 已随本插件打包，Runtime 仍需单独安装。
- Python 3.12，支持 venv/pip。
- Java 21，`java` 已加入 PATH。
- **发布包已包含 PlantUML 1.2026.9，位于 `tools/plantuml.jar`，无需另行下载、复制或配置。** 许可证和来源说明一并提供。
- DSH 中配置可用模型，并从允许写入的真实工作区聊天发起任务。Linux 渲染中文还需中文字体，例如 Noto CJK。

PlantUML JAR 随包提供，Java 和 Python 需在服务端准备；任务不会将需求发送到公共画图网站，也不会临时下载 JAR 或 pip install。默认采用 Smetana，不要求单独安装 Graphviz。

### 2. 准备 Python

在本插件发布目录打开 PowerShell，替换实际路径后执行一次：

```powershell
Set-Location 'D:\DSH-plugins\dsh-functional-logic-completion-v2-1'
node .\scripts\prepare-python.mjs 'C:\Python312\python.exe'
```

脚本自动创建插件目录内的 `.venv`、执行锁定依赖的 pip install，并检查 Python、Java 和 PlantUML。出现 `"ready": true` 表示环境探测通过；不代表完整任务已经成功。无需额外手工 pip install、激活 venv 或启动 Python 服务。

Linux 使用 `node scripts/prepare-python.mjs /usr/bin/python3.12`，在目标系统重新创建环境，不复制 Windows 虚拟环境。

### 3. 安装并启动

在 DSH 网页的 **插件 → 添加插件** 中选择发布目录 `artifacts/release/dsh-functional-logic-completion-v2-1/`，安装并启用，按提示重启 DSH。选择的目录应直接包含 `package.json`。本地目录安装后不要移动或删除该目录。

**默认不用手改 YAML。** 插件使用自身 `.venv`、PATH 中的 Java 和 `tools/plantuml.jar`，最多检查 5 轮，并发为 1。

只有自定义环境时，才修改当前 profile 对应插件 `functional-logic-completion-v2-1` 的 `config`：

| 可选配置 | 用途 |
|---|---|
| `pythonPath` | 外部虚拟环境的解释器绝对路径 |
| `javaPath` | Java 可执行文件绝对路径或 PATH 名称，默认 `java` |
| `plantumlJarPath` | 外部 PlantUML JAR 的绝对路径 |
| `maxIterations` / `maxConcurrent` | 检查轮次 / 并发上限，默认 5 / 1 |

配置保存后重启。不要复制旧插件的 ID 来覆盖新版条目，无需修改 HugeGraph 或填写 Tool 允许名单。

日常只启动 DSH，不手动启动 worker.py 或 Gradio。源码部署的 DSH 在其主项目目录运行 `pnpm.cmd dsh web`，不是在本插件目录运行。

## 使用

先在普通聊天检查入口：

> 请调用 sf_runtime_get_tool_contract，参数为 {"toolId":"sf_functional_logic_completion_v2_1"}，只检查接口。

通过 `sf_runtime_run_tool` 启动：

```json
{
  "toolId": "sf_functional_logic_completion_v2_1",
  "input": {"software_intro": "商品系统：管理员增加、删除、修改、查看商品。增加商品时录入信息、校验并保存。"},
  "timeoutMs": 3600000
}
```

`software_intro` 必填，非空且不超过 100000 字符。模型默认继承发起聊天；也可在启动请求顶层传入 `model: {provider, model}`，使用 DSH 已配置的实际 ID。任务模型固定，主聊天模型不切换，Python 不持有密钥。

任务返回 `runId`；用 `sf_runtime_get_run` 查询，`sf_runtime_wait_run` 等待，`sf_runtime_cancel_run` 取消，文件通过 `sf_runtime_get_artifact` 获取下载引用。最终文件 ID 在结果的 `result.files` 中。

## 输出

| 文件 | 内容 |
|---|---|
| `requirements.docx` | 原需求内容、分层功能说明、系统总览及每个分组的用例图、每个末级子功能的活动图；图片插入对应章节 |
| `functional-tree.json` | 功能编号、名称、说明、参与者和父子结构 |
| `diagrams.zip` | PNG 图片、原始 `.puml`、功能树与图索引 |
| `checks.zip` | 输入、实体、用例、E-R/CRUD、每轮状态、模型请求响应及日志等检查材料 |
| `result.json` | 结构化结果、功能树、图文件对应关系与收敛状态 |

所有文件保存在发起聊天工作区的 `outputs/runs/<runId>/`，最终文件在 `final/`，初始和新增材料在 `intermediate/`，逐轮快照在 `snapshots/`。失败和取消时保留已完成材料。

每个非叶分组各生成一张用例图，展示直属子功能；系统总览展示顶层大功能。每个叶子节点生成一张活动图。功能树最多四层、160 个节点；图越多，模型请求和渲染工作越多。进度按阶段及已完成图片数量估算，不是剩余时间。

PlantUML 源码直接由 AI 生成并保存，不剥离代码围栏、不改写源码、不自动调用模型修图。格式错误或渲染失败明确报告对应节点，不将缺图文档登记为成功产物。原 v2.0 导出保存在中间材料中；只有全部新版步骤完成才登记最终交付。

程序完成、DOCX 生成和 CRUD 方法收敛分别记录，收敛不代表需求完整正确。Python 使用受信任的受管后端及应用层路径检查，不提供额外的操作系统级文件沙箱隔离。

## 从源码构建

需要依赖已准备好的兼容 DSH 源码，脚本复用其构建工具。SDK TGZ 已保留在 `vendor/`。

```powershell
$env:DSH_SOURCE = 'D:\work\DSH-Softwarefactory'
node scripts/build.mjs
node scripts/pack.mjs
```

从 Git 克隆源码时，如缺少 `tools/plantuml.jar`，先按 `tools/README.md` 获取对应官方文件；打包脚本会拒绝缺少 JAR 的发布包。

安装目录为 `artifacts/release/dsh-functional-logic-completion-v2-1/`，TGZ 为 `artifacts/deepseek-ai-dsh-functional-logic-completion-v2-1-0.3.0.tgz`。PlantUML JAR 及其许可证已随包提供；Java、Python 虚拟环境、Skill 和任务文件不随包发布。在实际安装目录创建虚拟环境即可，无需手动复制 JAR。

轻量检查：`node scripts/typecheck.mjs`、`node --experimental-transform-types --test tests/progress.test.ts tests/run-entry.test.ts`、`.venv\Scripts\python.exe -B tests/python_smoke.py` 和 `.venv\Scripts\python.exe -B tests/v21_output_smoke.py`。后者需要本地 Java/JAR，仅运行小型模拟输入，不运行完整补全或真实模型。

安装不等于 Python/Java 环境就绪；环境探测不等于真实任务完成。出现缺少 JAR、模型不可用、只读会话、目录写入失败或图源码错误时，按任务报告处理，不会静默跳过或提升权限。

## 修复记录

修复原补全流程生成基础文档后，在“整理原始补全结果”阶段失败的问题。修复不改变补全算法、Tool 名称、输入输出及数据库绑定；已有失败任务和材料保持原样。新增离线回归检查覆盖文档生成后的产物通知。
