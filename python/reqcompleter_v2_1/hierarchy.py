"""Generate a bounded function tree and AI-written diagrams for each group/leaf."""
from __future__ import annotations

import json
import re

from reqcompleter_v2_0.protocol import TaskError


def validate_tree(value):
    def text(item):
        return isinstance(item, str) and bool(item.strip())

    if (not isinstance(value, dict) or not text(value.get("systemName"))
            or not isinstance(value.get("actors"), list) or not value["actors"]
            or not all(text(actor) for actor in value["actors"])
            or not isinstance(value.get("functions"), list) or not value["functions"]):
        raise TaskError("INVALID_FUNCTION_TREE", "功能树必须包含系统名称、参与者和非空功能列表。")
    seen = {"SYSTEM"}

    def visit(nodes, depth):
        if depth > 4:
            raise TaskError("INVALID_FUNCTION_TREE", "功能最多分为四层。")
        for node in nodes:
            if not isinstance(node, dict):
                raise TaskError("INVALID_FUNCTION_TREE", "功能节点必须是对象。")
            identifier = node.get("id")
            if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", identifier) or identifier in seen:
                raise TaskError("INVALID_FUNCTION_TREE", "功能编号必须唯一，且只使用字母、数字、连字符或下划线。")
            seen.add(identifier)
            if len(seen) > 161:
                raise TaskError("INVALID_FUNCTION_TREE", "本次功能节点超过 160 个。")
            if (not text(node.get("name")) or not text(node.get("description"))
                    or not isinstance(node.get("actors"), list) or not node["actors"]
                    or not all(actor in value["actors"] for actor in node["actors"])
                    or not isinstance(node.get("children"), list)):
                raise TaskError("INVALID_FUNCTION_TREE", f"功能 {identifier} 缺少名称、说明、参与者或子功能列表。")
            if node["children"]:
                visit(node["children"], depth + 1)

    visit(value["functions"], 1)
    return value


def flatten(tree):
    def visit(nodes, parent_id="SYSTEM", level=1, ancestry=()):
        for node in nodes:
            yield node, parent_id, level, ancestry
            yield from visit(node["children"], node["id"], level + 1, (*ancestry, node["name"]))
    return list(visit(tree["functions"]))


def generate_tree(client, store, result):
    client.set_step("functional_hierarchy")
    context = {key: result[key] for key in ("software_intro", "use_cases", "use_case_description", "functional_requirements")}
    prompt = """TASK:FUNCTION_TREE
根据已完成补全的需求，整理功能层次，不改变其业务含义，不添加没有依据的新业务。
商品增加、商品删除、商品修改、商品查看这样的完整业务动作应分别作为大功能，不能只输出一个笼统的“商品管理”。
在每个大功能下继续列出完成该功能需要的具体子功能。只在确有必要时继续向下细分，最多四层，总节点不超过160个。
每个节点有唯一编号、名称、功能说明、参与者、children；没有更细子功能时 children 为 []。
节点 actors 必须来自根 actors。相同内容不重复拆分，也不把功能分解关系一律当作用例 include 关系。
只输出一个 JSON 对象，不输出 Markdown 或解释。格式：
{"systemName":"系统名称","actors":["管理员"],"functions":[{"id":"F001","name":"商品增加","description":"说明","actors":["管理员"],"children":[{"id":"F001_01","name":"录入商品信息","description":"说明","actors":["管理员"],"children":[]}]}]}
已补全的需求：
""" + json.dumps(context, ensure_ascii=False)
    attempt_prompt = prompt
    for attempt in range(1, 4):
        raw = client.complete("V21Hierarchy", attempt_prompt)
        store.write_text("intermediate/v2_1/function-tree.raw.txt", raw)
        prefix = f"intermediate/v2_1/function-tree.attempt-{attempt:02d}"
        store.write_text(prefix + ".raw.txt", raw)
        try:
            tree = validate_tree(json.loads(raw))
        except (json.JSONDecodeError, TaskError) as error:
            if isinstance(error, TaskError) and error.code != "INVALID_FUNCTION_TREE":
                raise
            detail = (f"JSON 语法错误：{error.msg}；第 {error.lineno} 行第 {error.colno} 列，字符位置 {error.pos}。"
                      if isinstance(error, json.JSONDecodeError) else str(error))
            store.write_json(prefix + ".error.json", {"attempt": attempt, "code": "INVALID_FUNCTION_TREE", "message": detail})
            client.emit("artifact", path=prefix + ".error.json", kind="function_tree_error")
            if attempt == 3:
                raise TaskError("INVALID_FUNCTION_TREE", "功能树三次生成均未通过校验：" + detail) from error
            client.emit("step", step="functional_hierarchy", status="running",
                        message=f"功能树未通过校验，正在重新请求（{attempt}/2）：{detail}")
            attempt_prompt = (prompt + "\n上次功能树未通过校验，请修正以下错误，仅返回完整 JSON 对象，不要解释或代码围栏。\n"
                              + json.dumps({"error": detail, "previousResponse": raw}, ensure_ascii=False))
        else:
            break
    store.write_json("intermediate/v2_1/functional-tree.json", tree)
    client.emit("step", step="functional_hierarchy", status="completed")
    return tree


def generate_diagrams(client, store, renderer, tree, software_intro):
    nodes = flatten(tree)
    groups = [({"id": "SYSTEM", "name": tree["systemName"], "description": software_intro,
                "actors": tree["actors"], "children": tree["functions"]}, None, 0, ())]
    groups += [item for item in nodes if item[0]["children"]]
    leaves = [item for item in nodes if not item[0]["children"]]
    entries = []
    for stage, kind, selected in (("layer_use_cases", "use-case", groups), ("leaf_activities", "activity", leaves)):
        client.set_step(stage)
        for index, (node, parent_id, level, ancestry) in enumerate(selected):
            client.emit("step", step=stage, status="running", completed=index, total=len(selected), nodeName=node["name"])
            context = {"systemName": tree["systemName"], "softwareIntro": software_intro,
                       "ancestorFunctions": ancestry, "node": node}
            if kind == "use-case":
                instruction = """TASK:USE_CASE
为本分组生成一张用例图，展现所给 children 中的直属功能、真实参与者及必要关系。
系统总览展示大功能；大功能分组图展示它的下一层子功能，不混入其他分组或全部深层节点。
使用 PlantUML 用例图语法和稳定的英文别名，标签使用给定中文名称；功能分解并不自动等于 include/extend。
"""
            else:
                instruction = """TASK:ACTIVITY
为当前末级子功能生成一张活动图，只描述这个子功能内部的开始、操作、必要判断与结束。
使用 PlantUML 新版活动图语法（start、:操作;、if/else/endif、stop），不要扩展出新的业务需求。
"""
            prompt = (instruction + "只返回从 @startuml 到 @enduml 的一份完整源码，标记各自独占一行；不要解释、Markdown 代码围栏、include、图片或外部资源。\n"
                      + "采用本地 Smetana 布局，不需要 Graphviz。\nNODE_ID:" + node["id"] + "\n"
                      + json.dumps(context, ensure_ascii=False))
            folder = "use-cases" if kind == "use-case" else "activities"
            prefix = f"intermediate/v2_1/diagrams/{folder}/{node['id']}"
            entry = {"kind": kind, "nodeId": node["id"], "parentId": parent_id,
                     "level": level, "name": node["name"], "source": prefix + ".puml",
                     "status": "skipped", "attempts": []}
            attempt_prompt = prompt
            # Initial generation plus at most two model-assisted corrections.
            for attempt in range(1, 4):
                raw = client.complete("V21Diagrams", attempt_prompt)
                attempt_source = f"{prefix}.attempt-{attempt:02d}.puml"
                store.write_text(attempt_source, raw)
                store.write_text(prefix + ".puml", raw)
                record = {"attempt": attempt, "source": attempt_source}
                entry["attempts"].append(record)
                try:
                    source, image = renderer.render(raw, store, prefix)
                except TaskError as error:
                    # Model/service errors, cancellation and environment failures stay fatal.
                    if error.code not in {"INVALID_DIAGRAM", "DIAGRAM_RENDER_FAILED", "DIAGRAM_RENDER_TIMEOUT"}:
                        raise TaskError(error.code, f"{node['id']} {node['name']}：{error}") from error
                    problem = {"code": error.code, "message": str(error)}
                    error_path = f"{prefix}.attempt-{attempt:02d}.error.json"
                    record.update({"status": "failed", "error": problem, "errorPath": error_path})
                    entry["error"] = problem
                    store.write_json(error_path, {"nodeId": node["id"], "name": node["name"], **record})
                    client.emit("artifact", path=error_path, kind="diagram_error")
                    message = (f"{node['name']}：{error.code}，正在重新请求（{attempt}/2）。"
                               if attempt < 3 else f"{node['name']}：三次尝试均失败，跳过本图并保留功能文字。")
                    client.emit("step", step=stage, status="running", completed=index,
                                total=len(selected), nodeName=node["name"], message=message)
                    attempt_prompt = (prompt + "\n上次图源码校验或渲染失败，请针对下列错误修正当前图。"
                                      "只返回一份完整源码，必须以 @startuml 开始、以 @enduml 结束。\n"
                                      + json.dumps({"previousSource": raw, "error": problem}, ensure_ascii=False))
                else:
                    record["status"] = "generated"
                    entry.update({"status": "generated", "source": source, "image": image})
                    entry.pop("error", None)
                    break
            entries.append(entry)
            store.write_json("intermediate/v2_1/diagram-index.json", entries)
            client.emit("step", step=stage, status="running", completed=index + 1,
                        total=len(selected), nodeName=node["name"])
        client.emit("step", step=stage, status="completed", completed=len(selected), total=len(selected))
    return entries
