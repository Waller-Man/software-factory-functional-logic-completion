# 随包提供的本地 PlantUML

发布目录已包含 `plantuml.jar`，用户无需另行下载或复制，也无需填写 JAR 路径。
服务端仍需安装 Java 21 并加入 PATH；Python 虚拟环境按主 README 创建。

- 版本：1.2026.9，原样使用官方 JAR。
- SHA-256：`aa4a1d06f8911c4b842beff4828dd955be431692b631a312d04c0e9fab9581de`。
- 官方二进制：https://github.com/plantuml/plantuml/releases/download/v1.2026.9/plantuml.jar
- 对应源代码：https://github.com/plantuml/plantuml/archive/refs/tags/v1.2026.9.tar.gz
- 许可证：`plantuml-LICENSE.txt`；来源与第三方声明：`plantuml-NOTICE.md`、`plantuml-licenses/`。

从 Git 克隆源码时，JAR 不在 Git 中；构建发布包前将上面的官方文件保存为 `tools/plantuml.jar` 并核对 SHA-256。
打包脚本要求 JAR 和许可证存在，发布包会自动包含它们。任务不会自动下载文件。
使用本地 Smetana，无需额外安装 Graphviz。Linux 渲染中文需系统中文字体。
