"""Local PlantUML rendering. Model output is saved verbatim, never repaired."""
from __future__ import annotations

from pathlib import Path
import shutil
import struct
import subprocess

from reqcompleter_v2_0.protocol import TaskError


class PlantUML:
    def __init__(self, java_path="java", jar_path=None, timeout=60):
        self.java = shutil.which(java_path)
        self.jar = Path(jar_path or Path(__file__).resolve().parents[2] / "tools/plantuml.jar")
        self.timeout = timeout

    def command(self, *args):
        if not self.java:
            raise TaskError("JAVA_NOT_READY", "找不到 Java；请安装 Java 21 并加入 PATH，或配置 javaPath。")
        if not self.jar.is_file():
            raise TaskError("PLANTUML_NOT_READY", f"找不到 PlantUML JAR：{self.jar}")
        return [self.java, "-Djava.awt.headless=true", "-DPLANTUML_SECURITY_PROFILE=SECURE",
                "-jar", str(self.jar), *args]

    def execute(self, args, content=None):
        process = None
        try:
            process = subprocess.Popen(self.command(*args), stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            output, errors = process.communicate(content, timeout=self.timeout)
            if process.returncode != 0:
                raise TaskError("DIAGRAM_RENDER_FAILED", errors.decode("utf-8", errors="replace")[:3000]
                                or f"PlantUML 退出码 {process.returncode}")
            return output
        except subprocess.TimeoutExpired as error:
            raise TaskError("DIAGRAM_RENDER_TIMEOUT", "PlantUML 本地图像渲染超时。") from error
        except OSError as error:
            raise TaskError("PLANTUML_NOT_READY", f"无法启动本地 PlantUML：{error}") from error
        finally:
            # KeyboardInterrupt/host cancellation must also release the renderer.
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.communicate()

    def probe(self):
        output = self.execute(["-version"])
        return {"java": self.java, "jar": str(self.jar),
                "version": output.decode("utf-8", errors="replace").splitlines()[0]}

    def render(self, source, store, prefix):
        source_path = prefix + ".puml"
        image_path = prefix + ".png"
        store.write_text(source_path, source)
        # No fence stripping, code rewriting, template diagram or model repair loop.
        lines = source.strip().splitlines()
        if (not lines or lines[0].strip() != "@startuml" or lines[-1].strip() != "@enduml"
                or sum(line.strip().startswith("@start") for line in lines) != 1
                or sum(line.strip().startswith("@end") for line in lines) != 1):
            raise TaskError("INVALID_DIAGRAM", f"{source_path} 必须只包含一份完整 PlantUML 源码。")
        output = self.execute(["-charset", "UTF-8", "-tpng", "-pipe", "-failfast2", "-noerror",
                               "-Playout=smetana"], source.encode("utf-8"))
        if len(output) < 24 or output[:8] != b"\x89PNG\r\n\x1a\n" or not all(struct.unpack(">II", output[16:24])):
            raise TaskError("DIAGRAM_RENDER_FAILED", f"{source_path} 未生成有效 PNG。")
        store.write_bytes(image_path, output)
        return source_path, image_path
