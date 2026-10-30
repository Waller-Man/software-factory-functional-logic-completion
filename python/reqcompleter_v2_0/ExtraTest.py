# ReqCompleter v2.0 business methods retained; model transport uses DSH.
import ast
import json
from collections import defaultdict

class DataEntityAgentWithMemory:

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
        return self.client.complete('ExtraTest', user_input)

    def get_data_entities(self):
        return self.data_entities

    def get_use_cases(self):
        return self.use_cases

    def change_data_entities(self, data_entities):
        self.data_entities = data_entities

    def change_use_cases(self, use_cases):
        self.use_cases = use_cases

    def extract_data_entities(self, software_intro):
        self.memory.append({'role': 'user', 'content': software_intro})
        system_message = '\n        · The software description is as follows: {input}\n        · 请用中文回答\n        · Definition of data entities: Data entities refer to entities with independent existence and specific attributes in a software system. They are usually used to describe various data or objects involved in the system. Data entities can be physical objects, concepts, events in the real world, or data structures that need to be operated, stored, and managed in the system. In software engineering, data entities are usually described through data models to facilitate processing and management within the software system.\n        · Steps to identify data entities:\n        [1. Deeply analyze the software description to extract core data entities in the system and activity diagram.\n        2. Identify key terms, especially nouns that describe data or objects.\n        3. Focus on major entities in business processes, such as customer, project, order, etc.]\n        · Only extract the most core data entities which should be all mentioned in user inputs or the activity diagram. Do not include entities unrelated to core business logic.You should control the initial entities.\n        · For information systems, you need to consider the system including an administrator entity.\n        · Please Control the amounts of initial entities less than 8.Output should only contain the final data entities, separated by ideographic commas (,), without any reasoning or explanation.\n        · Output format example:\n        Project, Task, Team Member, Project Manager, Progress, Administrator\n        '
        prompt = system_message.format(input=software_intro)
        response = self.generate_response(prompt)
        try:
            content = response.strip()
            entities = content.split('、')
            self.data_entities = entities
            self.memory.append({'role': 'assistant', 'content': content})
            return content
        except AttributeError as e:
            return f'处理返回结果时出错：{str(e)}'

    def generate_use_cases(self, software_intro, data_entities):
        self.memory.append({'role': 'user', 'content': f'数据实体：{data_entities}'})
        use_case_system_message = '\n            · 软件描述如下：{input}\n            · 数据实体有：{entities}\n            · 请用中文回答\n            · 生成用例的步骤如下：\n            [\n                1. 根据软件系统及活动图中每个数据实体的角色和功能，生成对应的业务用例。\n                2. 每个数据实体可能具有以下用例类型：创建、删除、读取、更新。\n                · 对于每个实体，可能的用例应合理涵盖该实体整个生命周期的操作，包括创建、管理和删除。\n                · 管理操作可能包括更新、读取和删除操作。\n                · 注意：用例名称不必一定是“创建”“删除”或“管理”，只要能清晰反映操作，像“注册”“添加”“修改”等词也是可以接受的。\n                · 并非每个实体都必须有创建、删除、读取操作，请合理提取用例，控制用例数量。\n                3. 请将用例数量控制在15个以内。根据业务场景生成用例，确保每个实体都有明确的操作场景。\n            ]\n            · 根据给定要求，列出相关用例。用例可以涵盖整个业务场景。\n            · 输出内容仅包含最终用例，用英文逗号（,）隔开，不包含任何推理或解释。\n            · 输出格式示例：\n            管理项目,创建任务,管理任务,查看项目进度,删除团队成员,更新团队成员\n        '
        prompt = use_case_system_message.format(input=software_intro, entities=','.join(data_entities))
        messages = [{'role': 'system', 'content': prompt}]
        for message in self.memory:
            messages.append(message)
        response = self.generate_response(prompt)
        try:
            content = response.strip()
            use_cases = content.split(',')
            self.use_cases = use_cases
            self.memory.append({'role': 'assistant', 'content': content})
            return content
        except AttributeError as e:
            return f'处理返回结果时出错：{str(e)}'
