# ReqCompleter v2.0 business methods retained; model transport uses DSH.
import ast
import json
from collections import defaultdict

class ECNUAIUCAgentWithMemory:

    def __init__(self, client, model=None):
        self.client = client
        self.memory = []
        self.system_intro = ''
        self.data_entities = []
        self.use_cases = []
        self.new_uc = ''
        self.curd = ''
        self.er_model = ''
        self.simple_uc = ''
        self.full_uc = ''
        self.uc_code = ''

    def add_to_memory(self, role, content):
        """Add message to memory"""
        self.memory.append({'role': role, 'content': content})

    def generate_response(self, user_input):
        return self.client.complete('UC_Agent', user_input)

    def get_new_uc(self):
        """Return the new use case"""
        return self.new_uc

    def get_memory(self):
        """Return memory"""
        return self.memory

    def clear_memory(self):
        """Clear memory"""
        self.memory = []

    def reset_system_intro(self, new_intro):
        """Reset system introduction"""
        self.system_intro = new_intro

    def set_data_entities(self, data_entities):
        self.data_entities = data_entities

    def get_data_entities(self):
        return self.data_entities

    def set_use_cases(self, use_cases):
        self.use_cases = use_cases

    def get_use_cases(self):
        return self.use_cases

    def set_er_model(self, er_model):
        self.er_model = er_model

    def get_er_model(self):
        return self.er_model

    def generate_use_case(self, system_intro, data_entities, use_cases):
        if isinstance(use_cases, str):
            use_case_list = [uc.strip() for uc in use_cases.split(',')]
        else:
            use_case_list = use_cases
        self.simple_uc = ''
        for idx, use_case in enumerate(use_case_list, 1):
            prompt = f"\n            ·You are a senior system analyst. Please generate a new use case description based on the information below:\n            ·System description: {system_intro}\n            ·Data entities: {','.join(data_entities)}\n            ·Use case: {use_case}\n            · 请用中文回答\n            ·Previously generated use case descriptions (keep consistent style and format):\n            {(self.simple_uc.strip() if self.simple_uc else 'None')}\n            ·Please generate a complete description for the current use case including: use case name, ID, actors, preconditions, postconditions, main flow, and alternative flow. You should control the length of each use case. Focus only on the core content for main and alternative flows. Format:\n                Use Case Name:\n                Use Case ID: UC-XX\n                Actors:\n                Preconditions:\n                Postconditions:\n                Main Flow:\n                1.\n                ...\n                Alternative Flow:\n                1.\n                ...\n            "
            response = self.generate_response(prompt)
            try:
                formatted_response = response.strip()
                self.simple_uc += f'\n\n{formatted_response}'
                self.memory.append({'role': 'user', 'content': prompt})
                self.memory.append({'role': 'assistant', 'content': formatted_response})
            except AttributeError as e:
                self.simple_uc += f'\n\n[{use_case}] generation failed: {str(e)}'
        return self.simple_uc

    def generate_new_use_case(self, system_intro, data_entities, new_use_cases, operation_hint=None):
        """Generate new use case descriptions for missing CRUD operations.

        Args:
            system_intro: Software introduction text
            data_entities: List of data entities
            new_use_cases: List of new use case names to generate
            operation_hint: Optional dict mapping entity->operation to guide generation,
                            e.g. {"Order": "D"} means this use case should provide Delete for Order
        """
        if isinstance(new_use_cases, str):
            use_case_list = [uc.strip() for uc in new_use_cases.split(',')]
        else:
            use_case_list = new_use_cases
        for idx, use_case in enumerate(use_case_list, 1):
            hint_text = ''
            if operation_hint and isinstance(operation_hint, dict):
                op_desc = {'C': '创建(Create)', 'R': '查看/读取(Read)', 'U': '更新/修改(Update)', 'D': '删除(Delete)'}
                hints = [f'  - {entity}: 需要实现 {op_desc.get(op, op)} 操作' for entity, op in operation_hint.items()]
                if hints:
                    hint_text = '\n·Required operation for this use case (must be reflected in main flow):\n' + '\n'.join(hints)
            prompt = f"\n            ·You are a senior system analyst. Please continue to supplement a new use case description based on the following:\n            ·请用中文回答\n            ·System description: {system_intro}\n            ·Data entities: {','.join(data_entities)}\n            ·Current use case descriptions (keep consistent style and format):\n            {(self.simple_uc.strip() if self.simple_uc else 'None')}\n            ·New use case to be added: {use_case}\n            {hint_text}\n            ·Please only generate the complete description for the new use case, including:\n                - Use Case Name\n                - Use Case ID (format: UC-XX, increment automatically)\n                - Actors\n                - Preconditions\n                - Postconditions\n                - Main Flow (must include the specific CRUD operation interaction with the target entity)\n                - Alternative Flow\n            ·Do not repeat existing content, only add the new use case.\n            "
            response = self.generate_response(prompt)
            try:
                formatted_response = response.strip()
                self.new_uc = formatted_response
                self.simple_uc += f'\n\n{formatted_response}'
                self.memory.append({'role': 'user', 'content': prompt})
                self.memory.append({'role': 'assistant', 'content': formatted_response})
            except AttributeError as e:
                self.simple_uc += f'\n\n[{use_case}] generation failed: {str(e)}'
        return self.simple_uc

    def generate_functional_requirements(self, system_intro, er_model, use_case_description):
        self.memory.append({'role': 'user', 'content': f'Simplified use case description: {use_case_description}'})
        full_use_case_message = '\n        ·You are responsible for writing the software requirement specification (SRS) of Chapter 1: Functional Requirements.\n        ·System description: {intro}\n        ·Data model: {er}\n        ·请用中文回答\n        ·Use case description: {use_case}\n        ·Steps:\n            1. Clarify the functional scope by extracting core functions from use cases and data models.\n            2. Clearly define each function, including description, input, and output.\n            3. Ensure all references (inputs/outputs) are defined in the context.\n            4. Each function must be feasible: inputs must allow transformation to outputs.\n            5. Output format must follow the example strictly.\n        ·Rules:\n            1. Each function must state input, output, and description clearly.\n            2. Content must align with use cases and data model — no invented functions.\n            3. Feasibility and completeness must be guaranteed.\n            4. All references must be defined; no undefined terms.\n            5. Strictly follow the output format.\n\n        ·Example format:\n        1.1 Data Import Function  \n            Function ID: FR-01  \n            Description: Users can upload Excel files containing contract data. Batch import must be supported.  \n            Input: Excel files (.xlsx) with fields like contract number, balance, overdue days, etc.  \n            Output: Structured data stored in DB or temp storage.\n\n        1.2 Data Cleaning Function  \n            Function ID: FR-02  \n            Description: Perform format checks, fill in missing values, and handle outliers.  \n            Input: Imported data table.  \n            Output: Cleaned data table.\n        '
        prompt = full_use_case_message.format(intro=system_intro, er=er_model, use_case=use_case_description)
        response = self.generate_response(prompt)
        try:
            self.full_uc = response
            self.memory.append({'role': 'assistant', 'content': self.full_uc})
            return self.full_uc
        except AttributeError as e:
            return f'Error handling response: {str(e)}'

    def generate_uc_diagram(self, uc_model):
        self.memory.append({'role': 'user', 'content': f'Data Entities: {uc_model}'})
        er_system_message = '\n        ·You are responsible for use case model code generation. Based on the following information, please build a complete use case model PlantUML code.\n        ·Use Case Model: {input}\n        ·Please generate a complete use case model code based on use case model.\n        ·除了PlantUML代码，不要输出其他任何内容\n        ·输出示例：\n            @startuml\n            left to right direction\n            actor 客户\n            actor 管理员\n\n            rectangle 网上书店 {{\n            客户 -- (浏览图书)\n            客户 -- (搜索图书)\n            客户 -- (下订单)\n            客户 -- (注册账号)\n\n            (下订单) ..> (支付) : <<include>>\n\n            管理员 -- (管理图书)\n            管理员 -- (处理订单)\n            }}\n            @enduml\n        '
        prompt = er_system_message.format(input=uc_model)
        response = self.generate_response(user_input=prompt)
        try:
            self.uc_code = response
            self.memory.append({'role': 'assistant', 'content': self.uc_code})
            return self.uc_code
        except AttributeError as e:
            return f'Error processing response: {str(e)}'
