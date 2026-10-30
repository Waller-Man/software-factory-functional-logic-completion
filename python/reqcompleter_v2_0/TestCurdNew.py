# ReqCompleter v2.0 business methods retained; model transport uses DSH.
import ast
import json
from collections import defaultdict
import pandas as pd

class ECNUAICurdAgentWithMemory:

    def __init__(self, client, model=None):
        self.client = client
        self.memory = []
        self.system_intro = ''
        self.data_entities = []
        self.use_cases = []
        self.er_model = ''
        self.er_code = ''
        self.curd_matrix = None
        self.curd_modi = ''

    def add_to_memory(self, role, content):
        """添加消息到内存"""
        self.memory.append({'role': role, 'content': content})

    def generate_response(self, user_input):
        return self.client.complete('TestCurdNew', user_input)

    def set_curd(self, curd):
        self.curd_matrix = curd

    def clear_memory(self):
        self.memory = []

    def generate_curd_triples(self, data_entities, use_cases, use_case_description):
        self.memory.append({'role': 'user', 'content': f'数据实体：{data_entities}；用例：{use_cases}'})
        system_message = '\n        · The data entities are as follows: {entities}\n        · The use cases are as follows: {use_cases}\n        · The use case descriptions are as follows: {uc_description}\n        · Please output a structured list of triples (Entity, Use_case, CURD operation) based on the following rules:\n            - C (Create): When the use case involves adding new data for the entity.\n            - U (Update): When the use case involves modifying existing data for the entity.\n            - R (Read): When the use case involves querying existing data for the entity.\n            - D (Delete): When the use case involves deleting data for the entity.\n        · Each use case for each entity may correspond to multiple CURD operations, which must be listed completely.\n        · Note that if a use case only manages an entity, it includes C, R, U, and D operations.\n        · If a use case is not related to an entity, do not generate a triple for that entity.\n        · Output format should be a Python list, for example:\n        [\n            ("Task", "View Project", "R"),\n            ("Project", "Manage Project", "R"),\n            ("Project", "Manage Project", "U"),\n            ("Project", "Manage Project", "D"),\n            ("Task", "Delete Task", "D"),\n            ("Project", "Manage Project", "C"),\n        ]\n        · Please return only the list of triples without any explanations or natural language text.\n        '
        prompt = system_message.format(entities=data_entities, use_cases=use_cases, uc_description=use_case_description)
        response = self.generate_response(prompt)
        try:
            curd_triples = response.strip()
            self.memory.append({'role': 'assistant', 'content': str(curd_triples)})
            return curd_triples
        except Exception as e:
            return f'处理返回三元组时出错：{str(e)}'

    def convert_triples_to_matrix(self, triples):
        if isinstance(triples, str):
            try:
                triples = ast.literal_eval(triples)
            except Exception as e:
                raise ValueError(f'无法解析 triples 字符串: {e}')
        if not isinstance(triples, list) or not all((isinstance(t, tuple) and len(t) == 3 for t in triples)):
            raise ValueError('传入的 triples 不是有效的 (entity, use_case, operation) 列表。')
        matrix = {}
        for entity, use_case, operation in triples:
            matrix.setdefault(use_case, {}).setdefault(entity, set()).add(operation)
        all_use_cases = sorted(matrix.keys())
        all_entities = sorted({entity for uc_dict in matrix.values() for entity in uc_dict})
        df = pd.DataFrame(index=all_use_cases, columns=all_entities)
        for use_case in matrix:
            for entity in matrix[use_case]:
                ops = ','.join(sorted(matrix[use_case][entity]))
                df.at[use_case, entity] = ops
        df.fillna('', inplace=True)
        df.reset_index(inplace=True)
        df.rename(columns={'index': '用例'}, inplace=True)
        return df

    def get_curd(self):
        return self.curd_matrix

    def check_uc_ett(self, data_entities, use_cases, curd_matrix):
        """
        检查需求模型，检测 CRUD 矩阵中的缺口。
        输出格式: JSON，便于程序化解析。
        """
        self.memory.append({'role': 'user', 'content': f'CURD矩阵：{curd_matrix}'})
        class_system_message = '\n        · You are responsible for requirement checking based on the CURD matrix in the requirements team. Now, you need to detect whether there are any obviously missing CURD operations in the established CURD matrix.\n        · Be aware this step is prone to LLM hallucinations which may cause system boundaries to expand uncontrollably, so only focus on internal entities. Not all internal entities require full CURD; for example, logs or record-related entities may only require Read operations.\n        · Below is the list of current data entities in the system: {ett}\n        · Below is the list of system use cases: {uc}\n        · Below is the current CURD matrix: {curd}\n        · Please analyze according to the following requirements:\n            1. Carefully analyze the CURD matrix to determine whether there are missing use cases and entities. First identify external entities, such as third-party services or management-related data entities. These do not require full CURD operations;\n            2. Note that a "management" use case should imply C, R, U, and D operations. For internal entities, to control system boundaries, logs or record-type entities may only need Read (R);\n            3. If there are no obviously missing entities or CURD operations, set status to "complete" with empty missing list.\n            4. If there are missing operations, set status to "incomplete" and list each gap.\n\n        · CRITICAL: You MUST output your final result as a JSON object at the end of your response, wrapped in ```json code blocks.\n        · The JSON format must be:\n          {{\n            "status": "complete" or "incomplete",\n            "analysis": "brief analysis summary",\n            "missing": [\n              {{"entity": "EntityName", "operation": "C|R|U|D", "reason": "Missing create operation"}}\n            ]\n          }}\n\n        · Example when model is complete:\n          ```json\n          {{\n            "status": "complete",\n            "analysis": "All internal entities have complete CURD operations. External entities have required Read operations.",\n            "missing": []\n          }}\n          ```\n\n        · Example when model is NOT complete:\n          ```json\n          {{\n            "status": "incomplete",\n            "analysis": "Asset Type entity is missing Create, Read, Update, Delete operations. Approval entity is missing Read operation.",\n            "missing": [\n              {{"entity": "Asset Type", "operation": "C", "reason": "No use case creates Asset Type records"}},\n              {{"entity": "Asset Type", "operation": "R", "reason": "No use case reads Asset Type data"}},\n              {{"entity": "Asset Type", "operation": "U", "reason": "Asset Type cannot be updated"}},\n              {{"entity": "Asset Type", "operation": "D", "reason": "Asset Type cannot be deleted"}},\n              {{"entity": "Approval", "operation": "R", "reason": "No use case to view Approval records"}}\n            ]\n          }}\n          ```\n\n        · You may include a text analysis before the JSON, but the ```json block at the end is REQUIRED for automated parsing.\n        '
        prompt = class_system_message.format(ett='、'.join(data_entities), uc='、'.join(use_cases), curd=curd_matrix)
        messages = [{'role': 'system', 'content': prompt}]
        response = self.generate_response(prompt)
        try:
            self.curd_modi = response
            self.memory.append({'role': 'assistant', 'content': self.curd_modi})
            return self.curd_modi
        except AttributeError as e:
            return f'处理返回结果时出错：{str(e)}'

    def Complete_CRUD_Triplets(self, entities, new_uc_description, crud_triplets, missing_report):
        crud_completion_prompt = '\n            ·You are responsible for completing the system’s CRUD matrix based on recent updates to use cases and missing interaction reports.\n\n            ·Input:\n                (a) Data Entities:\n                {entities}\n\n                (b) New Use Case Descriptions:\n                {uc_description}\n\n                (c) Previous CRUD Triplets:\n                {crud_triplets}\n\n                (d) Use Case Missing Report:\n                {missing_report}\n\n            ·Task Instructions:\n                1. Read and understand the entity–use case interaction gaps mentioned in the Use Case Missing Report.\n                2. Analyze updated Use Case Descriptions to detect any new interactions (C, R, U, D) between entities and use cases.\n                3. Compare these findings with the Previous CRUD Triplets to determine what is already covered.\n                4. Construct new CRUD triplets **only** for missing interactions.\n                5. Do **not** repeat any existing triplets from the previous matrix.\n\n            ·Output Format:\n                Python list only, using the following structure:\n                [("Entity", "UseCase", "Operation")]\n\n            ·Example Output:\n                [\n                    ("Project", "Manage Project", "C"),\n                    ("Task", "Create Task", "C"),\n                    ("Team Member", "View Team Member", "R"),\n                    ("Project Progress", "Update Project Progress", "U"),\n                    ("Team Member", "Delete Team Member", "D")\n                ]\n\n            ·Rules:\n                - Ensure that every triplet reflects a valid and grounded interaction in the use case descriptions.\n                - Use consistent naming for both entities and use cases.\n                - Do not invent any operations or assumptions not supported by the use cases.\n\n            ·Begin now.\n\n            '
        prompt = crud_completion_prompt.format(entities=entities, uc_description=new_uc_description, crud_triplets=crud_triplets, missing_report=missing_report)
        response = self.generate_response(prompt)
        try:
            self.new_crud_triplets = response
            self.memory.append({'role': 'assistant', 'content': self.new_crud_triplets})
            return self.new_crud_triplets
        except AttributeError as e:
            return f'Error handling response: {str(e)}'
