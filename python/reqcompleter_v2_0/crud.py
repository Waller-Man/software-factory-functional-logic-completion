"""Original v2.0 parsing/checking semantics; host persistence lives separately."""
import ast
import json
import re
from collections import defaultdict
import pandas as pd


def name_list(value):
    """The original initial entity/use-case parsing, without extra normalization."""
    if isinstance(value, str):
        return [item.strip() for item in value.replace("、", ",").split(",") if item.strip()]
    return list(value) if value else []


def parse_crud_triplets(triples_input):
    """安全解析 CRUD 三元组，支持多种格式"""
    if triples_input is None:
        return []
    if isinstance(triples_input, list):
        result = []
        for item in triples_input:
            if isinstance(item, (tuple, list)) and len(item) == 3:
                result.append(tuple(item))
        return result
    if isinstance(triples_input, str):
        text = triples_input.strip()
        # 尝试直接 ast.literal_eval
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, list):
                return [tuple(item) for item in parsed if isinstance(item, (tuple, list)) and len(item) == 3]
        except Exception:
            pass
        # 回退: 正则匹配 ("Entity", "UseCase", "Op") 或 ('Entity', 'UseCase', 'Op')
        pattern = re.findall(
            r'\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']\s*,\s*["\']([CRUDcrud]+)["\']\s*\)',
            text
        )
        if pattern:
            return [(e.strip(), uc.strip(), op.strip().upper()) for e, uc, op in pattern]
    return []


def build_crud_matrix_df(triples):
    """从三元组列表构建 CRUD DataFrame"""
    if not triples:
        return pd.DataFrame()
    matrix = {}
    for entity, use_case, operation in triples:
        matrix.setdefault(use_case, {}).setdefault(entity, set()).add(operation.upper())
    all_use_cases = sorted(matrix.keys())
    all_entities = sorted({e for uc_dict in matrix.values() for e in uc_dict})
    df = pd.DataFrame(index=all_use_cases, columns=all_entities)
    for use_case in matrix:
        for entity in matrix[use_case]:
            ops = ','.join(sorted(matrix[use_case][entity]))
            df.at[use_case, entity] = ops
    df.fillna("", inplace=True)
    return df


def programmatic_crud_gap_detection(triples, data_entities):
    """
    程序化 CRUD 缺口检测（论文核心机制）。

    对每个 entity，检查是否拥有 C、R、U、D 四种操作。
    如果某个 entity 缺少某项操作，记录为缺口。

    返回: (is_complete: bool, gaps: list[dict])
    """
    if not triples or not data_entities:
        return False, []

    ALL_OPS = {"C", "R", "U", "D"}

    # 归一化 entity 名称 (去除空格、统一大小写)
    def normalize(s):
        return s.strip().lower()

    # 建立 entity → operations 映射
    entity_ops = defaultdict(set)
    entity_name_map = {}  # normalized → original

    for entity, use_case, operation in triples:
        norm_entity = normalize(entity)
        entity_name_map[norm_entity] = entity
        entity_ops[norm_entity].add(operation.upper().strip())

    # 归一化 data_entities
    if isinstance(data_entities, str):
        data_entities_list = [e.strip() for e in data_entities.replace("、", ",").split(",") if e.strip()]
    else:
        data_entities_list = [str(e).strip() for e in data_entities if str(e).strip()]

    gaps = []
    for entity_str in data_entities_list:
        norm_entity = normalize(entity_str)
        existing_ops = entity_ops.get(norm_entity, set())
        missing_ops = ALL_OPS - existing_ops

        # 从原始三元组中找匹配的 entity 名
        original_name = entity_name_map.get(norm_entity, entity_str)

        for op in sorted(missing_ops):
            gaps.append({
                "entity": original_name,
                "operation": op,
                "reason": f"{original_name} 缺少 {op} 操作"
            })

    is_complete = len(gaps) == 0
    return is_complete, gaps


def parse_llm_gap_response(response_text):
    """
    解析 LLM CRUD 检测的 JSON 输出。
    如果解析失败，返回 None（回退到程序化检测）。
    """
    if not response_text:
        return None

    text = response_text.strip()

    # 尝试从文本中提取 JSON 块
    json_patterns = [
        r'```json\s*([\s\S]*?)\s*```',
        r'```\s*([\s\S]*?)\s*```',
        r'\{[\s\S]*"status"[\s\S]*\}',
    ]

    json_str = None
    for pattern in json_patterns:
        match = re.search(pattern, text)
        if match:
            json_str = match.group(1) if '```' in pattern else match.group(0)
            break

    if json_str is None:
        json_str = text

    try:
        result = json.loads(json_str.strip())
        if "status" in result:
            return result
    except json.JSONDecodeError:
        pass

    return None


def combine_gap_detection(llm_result, programmatic_gaps):
    """
    结合 LLM 检测结果和程序化检测结果。
    取并集确保不遗漏。
    """
    combined_gaps = programmatic_gaps.copy()

    if llm_result and isinstance(llm_result, dict):
        llm_status = llm_result.get("status", "")
        llm_missing = llm_result.get("missing", [])

        if isinstance(llm_missing, list):
            for item in llm_missing:
                if isinstance(item, dict) and "entity" in item and "operation" in item:
                    # 检查是否已存在
                    exists = any(
                        g["entity"].strip().lower() == item["entity"].strip().lower() and
                        g["operation"].strip().upper() == item["operation"].strip().upper()
                        for g in combined_gaps
                    )
                    if not exists:
                        combined_gaps.append({
                            "entity": item["entity"],
                            "operation": item["operation"].upper(),
                            "reason": item.get("reason", f"{item['entity']} 缺少 {item['operation']} 操作")
                        })

    return combined_gaps


def main():
    """
    命令行入口。用法:
        python3 AutoReqCompleter.py "软件简介文本"

    或交互式输入:
        python3 AutoReqCompleter.py
    """
    import sys

    # API 配置
    API_KEY = ""
    MODEL = "deepseek-chat"

    if len(sys.argv) > 1:
        software_intro = sys.argv[1]
    else:
        print("=" * 60)
        print("AutoReqCompleter - 全自动需求补全流水线")
        print("=" * 60)
        print()
        print("请输入软件功能简介 (输入完成后按 Ctrl+D 或输入空行结束):")
        lines = []
        try:
            while True:
                line = input()
                if line == "" and lines and lines[-1] == "":
                    break
                lines.append(line)
        except EOFError:
            pass
        software_intro = "\n".join(lines).strip()

        if not software_intro:
            # 使用默认测试案例
            software_intro = (
                "这是一个在线商城系统，用户可以注册账号、浏览商品、搜索商品、"
                "将商品加入购物车、下单购买、查看订单状态、评价商品。"
                "管理员可以管理商品信息、管理用户、处理订单。"
            )
            print(f"使用默认测试案例: {software_intro}")

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_path = f"ReqCompleter_output_{ts}.docx"
    log_path = f"ReqCompleter_log_{ts}.log"

    completer = AutoReqCompleter(api_key=API_KEY, model=MODEL, max_iterations=5, log_file=log_path)
    result = completer.run(software_intro, output_path=output_path, log_file=log_path)

    print()
    print("=" * 60)
    print("流水线执行完毕!")
    print(f"输出文档: {output_path}")
    print(f"迭代次数: {result['iterations']}")
    print(f"收敛状态: {'已收敛' if result['converged'] else '未收敛(达上限)'}")
    print("=" * 60)


def clean_entity_name(name):
                        """清理实体名称，去除 LLM 输出的前缀标记。迭代应用多条规则直到稳定。"""
                        prev = None
                        while prev != name:
                            prev = name
                            name = re.sub(r'^[-*•]\s*', '', name).strip()
                            name = re.sub(r'^(?:Add|New|Delete|Remove)[:\s]+', '', name, flags=re.IGNORECASE).strip()
                            name = re.sub(r'^[`'']', '', name).strip()
                            name = re.sub(r'[`'']$', '', name).strip()
                        return name


def is_valid_entity_name(name):
                        if len(name) > 30:
                            return False
                        if len(name) < 2:
                            return False
                        if re.search(r'[。！？；：""''（）【】]', name):
                            return False
                        if name.count(' ') > 2:
                            return False
                        return True
