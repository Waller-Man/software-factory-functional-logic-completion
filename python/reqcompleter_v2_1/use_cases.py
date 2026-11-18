"""Describe function-tree nodes before drawing them; identity is owned by code."""
from __future__ import annotations

import json

from reqcompleter_v2_0.protocol import TaskError
from .hierarchy import flatten


def validate_flows(value):
    if not isinstance(value, dict):
        raise TaskError("INVALID_FUNCTION_USE_CASE", "子功能用例描述必须是 JSON 对象。")
    fields = ("preconditions", "postconditions", "mainFlow", "alternativeFlows")
    for field in fields:
        items = value.get(field)
        if (not isinstance(items, list) or (field != "alternativeFlows" and not items)
                or not all(isinstance(item, str) and item.strip() for item in items)):
            raise TaskError("INVALID_FUNCTION_USE_CASE", f"{field} 必须为文字列表；前后置条件和主流程不能为空。")
    return {field: [item.strip() for item in value[field]] for field in fields}


def generate_function_use_cases(client, store, tree, result):
    nodes = flatten(tree)
    by_node = {node["id"]: node for node, *_ in nodes}
    descriptions = {}
    stage = "function_use_case_descriptions"
    client.set_step(stage)
    for index, (node, parent_id, level, ancestry) in enumerate(nodes):
        client.emit("step", step=stage, status="running", completed=index, total=len(nodes), nodeName=node["name"])
        context = {
            "softwareIntro": result["software_intro"],
            "existingUseCaseDescriptions": result["use_case_description"],
            "functionalRequirements": result["functional_requirements"],
            "nonfunctionalRequirements": result["nonfunctional_requirements"],
            "ancestorFunctions": ancestry, "node": node,
            "parentFunction": by_node.get(parent_id),
            "parentUseCase": descriptions.get(parent_id),
        }
        prompt = """TASK:FUNCTION_USE_CASE_DESCRIPTION
为当前功能补齐用例描述，用于需求文档及后续活动图。当前功能的编号、名称和参与者已确定，不得另起名称或改变功能树。
依据原始需求、现有用例、功能说明及相关规则细化已有业务，不扩大本次范围，不新增功能。
大功能说明完整业务；子功能只细化它在所属大功能中的操作，不重复承担其他子功能的职责。
子功能应与父级用例保持一致，明确输入来源、处理结果以及返回或交接位置。
主流程写成功路径；备选与异常流程写触发条件、处理及返回位置。原依据要求重新输入、回滚或提示失败时必须保留；不要擅自增加取消或退出分支。
只采用与当前功能相关的非功能约束；没有依据的业务规则不要猜测。不存在备选流程时 alternativeFlows 为 []。
只输出一个 JSON 对象，不输出 Markdown 或解释；每个字段都是文字数组：
{"preconditions":["前置条件"],"postconditions":["后置条件"],"mainFlow":["步骤1","步骤2"],"alternativeFlows":["条件：处理，并返回指定步骤或交接环节"]}
上下文：
""" + "NODE_ID:" + node["id"] + "\n" + json.dumps(context, ensure_ascii=False)
        prefix = f"intermediate/v2_1/use-cases/{node['id']}"
        attempt_prompt = prompt
        for attempt in range(1, 4):
            raw = client.complete("V21FunctionUseCases", attempt_prompt)
            attempt_prefix = f"{prefix}.attempt-{attempt:02d}"
            store.write_text(attempt_prefix + ".raw.txt", raw)
            try:
                flows = validate_flows(json.loads(raw))
            except (json.JSONDecodeError, TaskError) as error:
                detail = str(error)
                store.write_json(attempt_prefix + ".error.json", {"attempt": attempt, "code": "INVALID_FUNCTION_USE_CASE", "message": detail})
                if attempt == 3:
                    raise TaskError("INVALID_FUNCTION_USE_CASE", f"{node['id']} {node['name']} 用例描述三次生成均未通过校验：{detail}") from error
                client.emit("step", step=stage, status="running", completed=index, total=len(nodes), nodeName=node["name"],
                            message=f"用例描述未通过校验，正在重新请求（{attempt}/2）：{detail}")
                attempt_prompt = prompt + "\n请修正上次响应，仅返回完整 JSON：\n" + json.dumps({"error": detail, "previousResponse": raw}, ensure_ascii=False)
            else:
                break
        # Do not ask the model to invent another ID, name, actor or parent mapping.
        record = {"id": node["id"], "name": node["name"], "actors": node["actors"],
                  "parentId": parent_id, "level": level, "ancestorFunctions": list(ancestry),
                  "description": node["description"], **flows}
        descriptions[node["id"]] = record
        store.write_json(prefix + ".json", record)
        store.write_json("intermediate/v2_1/function-use-cases.json", list(descriptions.values()))
        client.emit("step", step=stage, status="running", completed=index + 1, total=len(nodes), nodeName=node["name"])
    client.emit("step", step=stage, status="completed", completed=len(nodes), total=len(nodes))
    return list(descriptions.values())
