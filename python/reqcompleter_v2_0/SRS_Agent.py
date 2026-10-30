# ReqCompleter v2.0 business methods retained; model transport uses DSH.
import ast
import json
from collections import defaultdict

class ECNUAISRSAgentWithMemory:

    def __init__(self, client, model=None):
        self.client = client
        self.memory = []
        self.data_entities = []
        self.use_cases = []
        self.introduction = ''
        self.overall_description = ''
        self.external_interface_requirement = ''
        self.nonfunctional_requirement = ''

    def add_to_memory(self, role, content):
        """添加消息到内存"""
        self.memory.append({'role': role, 'content': content})

    def generate_response(self, user_input):
        return self.client.complete('SRS_Agent', user_input)

    def get_memory(self):
        """获取当前内存内容"""
        return self.memory

    def clear_memory(self):
        """清空内存"""
        self.memory = []

    def get_data_entities(self):
        return self.data_entities

    def get_use_cases(self):
        return self.use_cases

    def set_data_entities(self, data_entities):
        self.data_entities = data_entities

    def set_use_cases(self, use_cases):
        self.use_cases = use_cases

    def generate_introduction(self, system_intro, data_entities, use_cases, er_model, use_case_simple):
        self.data_entities = data_entities
        self.use_cases = use_cases
        '\n        根据所有内容生成SRS的引言部分。\n        '
        self.memory.append({'role': 'user', 'content': f'数据实体：{data_entities}'})
        er_system_message = '\n        ·你在需求团队中负责软件需求规约说明书的撰写，现在需要你根据所给内容撰写需求规约第一章：引言部分的内容。\n        ·软件简介如下：{input}\n        ·数据实体如下：{entities}\n        ·用例如下：{usecase}\n        ·ER模型如下：{er}\n        ·用例模型如下:{uc}\n        ·思考步骤如下：\n            1.仔细理解软件简介、用例模型以及数据模型。\n            2.根据软件简介、用例模型以及数据模型分析本系统的背景。\n            3.根据简介与用例描述，明确本系统的业务目标。\n            4.根据所给内容明确定义本系统的范围。\n            5.给出需求规约说明书中所涉及到的定义、缩写和缩略语，尤其是用例描述和数据模型中涉及的内容，可以在此提前给出定义。\n            6.最后，列出本需求规约遵循的参考标准。\n        ·生成内容需要遵循以下规则：\n            1.本项目的目标和范围需要清晰阐述。\n            2.注重业务需求和高层次的系统需求，无需具体的技术实现。\n            3.遵循IEEE-830的SRS标准。\n            4.参考标准部分的内容需要真实、正确且有效。\n            5.对于用例模型和数据模型中的核心内容需要在引言部分给出相关定义、缩写和缩略语。\n        ·引言部分输出格式如下：\n            1.1 背景：介绍清楚本项目的项目背景 \n            1.2 业务目标：本文档旨在明确[软件名称]的软件需求，为开发团队提供明确的指导和方向。 \n            1.3 范围：本文档覆盖[软件名称]的所有功能需求、非功能需求以及相关的约束条件。 \n            1.4 定义、缩写与缩略语：列出文档中涉及到的相关专有名词、术语缩写和缩略语，并给出准确定义。 \n            1.5 参考标准：列出所有相关的文档、标准和其他参考资料。\n        '
        prompt = er_system_message.format(input=system_intro, entities='、'.join(data_entities), usecase='、'.join(use_cases), er=er_model, uc=use_case_simple)
        messages = [{'role': 'system', 'content': prompt}]
        for message in self.memory:
            messages.append(message)
        response = self.generate_response(prompt)
        try:
            self.introduction = response
            self.memory.append({'role': 'assistant', 'content': self.introduction})
            return self.introduction
        except AttributeError as e:
            return f'处理返回结果时出错：{str(e)}'

    def generate_overall_description(self, system_intro, data_entities, use_cases, er_model, use_case_simple):
        self.data_entities = data_entities
        self.use_cases = use_cases
        '\n        根据所有内容生成SRS的总体概述部分。\n        '
        self.memory.append({'role': 'user', 'content': f'数据实体：{data_entities}'})
        self.memory.append({'role': 'user', 'content': f'用例：{use_cases}'})
        self.memory.append({'role': 'user', 'content': f'E-R图：{er_model}'})
        er_system_message = '\n        ·你在需求团队中负责软件需求规约说明书的撰写，现在需要你根据所给内容撰写需求规约第二章：总体概述部分的内容。\n        ·数据实体如下：{ett}\n        ·用例如下：{uses}\n        ·用例模型如下:{uc}\n        ·E-R图如下：{er}\n        ·思考步骤如下：\n            1.首先，明确系统需要解决的问题是什么、目标用户是谁。\n            2.其次，根据所给内容梳理主要功能模块并列出软件需要具备的核心功能，分析各模块间的关联，理清模块间的工作逻辑。\n            3.再次，需要挖掘市场痛点，分析目前主流市场上是否有类似工具，清晰分析本产品的竞争优势，突出本软件的卖点。\n            4.最后，识别业务风险与机遇，并考虑软件设计约束。\n        ·生成内容需要遵循如下规则：\n            1.总体概述部分的输出格式需要按照IEEE 830-1998《软件需求规格说明书》模版。\n            2.需要精准把握市场痛点，减少笼统性的表述，竞品分析时，尽可能列出数据，摆事实讲道理，不能凭空编造。\n            3.设计约束部分需包含各项可能会影响开发的限制条件。\n            4.风险与机遇需要明确指出本项目可能遭遇的风险，不可泛泛而谈。\n        ·总体概述部分输出格式如下：\n            2.1 产品视角：简要描述软件产品的愿景、目标用户群体以及预期的市场定位。\n            2.2 产品功能：列出软件的主要功能模块，并说明它们之间的关联。\n            2.3 用户特征：描述目标用户特征，包括使用者的专业水平、使用习惯等。\n            2.4 竞品分析：把握市场痛点，对同类软件进行竞品分析，并突出本产品的优势。\n            2.5 业务风险与机遇：根据当前市场动向明确说明会遭遇的业务风险以及当前市场环境下本产品的业务机遇。\n            2.6 设计约束：列出可能影响软件开发的限制条件。\n            2.7 假设与依赖关系：明确文档中所做的假设以及软件与其他系统或组件之间的依赖关系。\n        '
        prompt = er_system_message.format(ett='、'.join(data_entities), uses='、'.join(use_cases), er=er_model, uc=use_case_simple)
        response = self.generate_response(prompt)
        try:
            self.overall_description = response
            self.memory.append({'role': 'assistant', 'content': self.overall_description})
            return self.overall_description
        except AttributeError as e:
            return f'处理返回结果时出错：{str(e)}'

    def generate_external_interface(self, intro, use_case_model):
        """
        根据所有内容生成SRS的总体概述部分。
        """
        self.memory.append({'role': 'user', 'content': f'系统介绍：{intro}'})
        er_system_message = '\n        · You are responsible for writing the Software Requirements Specification (SRS) in the requirements team. Your current task is to write Chapter 2: External Interfaces based on the provided content.\n        · System Introduction: {software}\n        · Functional Requirements: {uc}\n        · Follow these steps:\n            1. Carefully analyze the context, especially the inputs, outputs, and references to external data sources in each functional requirement. Extract and summarize these external data sources, such as databases, external API calls, and user interfaces.\n            2. Classify the identified external interfaces into the following categories: user interfaces, hardware interfaces, software interfaces (including third-party tools, databases, etc.), and communication interfaces (e.g., web browsing, email).\n            3. Analyze the role of each external interface and provide a clear definition and description.\n            4. Cross-check the external data sources mentioned in the functional requirements with the external interfaces to ensure every referenced external source is clearly defined here.\n        · Follow these rules when generating the output:\n            1. Ensure consistency between external data sources in the functional requirements and the descriptions in the external interfaces. All data sources mentioned must be covered in this section.\n            2. Each external interface should have a clear and unambiguous definition.\n            3. Describe the interaction method for each interface. For complex interactions, indicate relevant inputs/outputs to help developers understand correctly.\n            4. Use clear and understandable language to describe the external interfaces, making them easy to comprehend and implement, thereby reducing communication costs.\n            5. Use terminology consistent with the rest of the document.\n        · Output format for external interfaces:\n            2.1 User Interface Output: Output related to system-user interaction, such as screen displays, print content, etc.\n            2.2 Hardware Interface Output: Output related to interaction with external hardware devices, such as device communication protocols, supported device types, etc.\n            2.3 Software Interface Output: Output related to interaction with other software, such as data export formats, API response data, etc.\n            2.4 Communication Interface Output: Output via network or other means, such as email notifications, message push, etc.\n        '
        prompt = er_system_message.format(software=intro, uc=use_case_model)
        response = self.generate_response(prompt)
        try:
            self.external_interface_requirement = response
            self.memory.append({'role': 'assistant', 'content': self.external_interface_requirement})
            return self.external_interface_requirement
        except AttributeError as e:
            return f'处理返回结果时出错：{str(e)}'

    def generate_nonfunctional_requirement(self, intro, overall_description, use_case_model):
        """
        根据所有内容生成SRS的非功能需求部分。
        """
        self.memory.append({'role': 'user', 'content': f'系统介绍：{intro}'})
        er_system_message = '\n        ·系统简介如下：{software}\n        ·软件总体概述如下:{overall}\n        ·用例模型如下：{uc}\n        ·思考步骤如下：\n            1.首先，分析软件背景，明确软件的应用场景和所属领域。\n            2.其次，仔细阅读功能需求以及用例模型，分析核心功能中对于非功能特性的要求，并将其归纳整理为性能需求、安全需求以及其它软件质量需求。\n            3.接着，结合上下文中引言和总体概述内容，分析明确用户需求以及初步的系统架构，确保非功能需求与系统目标保持一致。\n            4.最后，定义并生成所需的非功能需求。\n        ·生成遵循的规则如下：\n            1.对于非功能需求的描述，需要使用明确的指标，如：响应时间小于2s，应当避免模糊不清或待定的描述。\n            2.保持功能需求与非功能需求的一致，非功能需求应当是起到支持或增强功能需求实现的作用。\n            3.非功能需求需要考虑到现实条件约束，结合硬件、软件以及其它外部外部限制，确保需求是可实现的。\n            4.避免冗余和非必要的技术细节，保持非功能需求易于理解。\n        ·非功能需求输出格式如下：\n            5.1性能需求：系统在不同功能场景下需要的性能要求，如响应时间、并发处理等要求。\n            5.2安全需求：系统使用的安全或隐私保护相关的要求或是一些在遇到危机时采取的安全措施或行动。\n            5.3其它质量需求：系统涉及的其它质量需求，如：可扩展性、可移植性等。\n\n        '
        prompt = er_system_message.format(software=intro, overall=overall_description, uc=use_case_model)
        response = self.generate_response(prompt)
        try:
            self.nonfunctional_requirement = response
            self.memory.append({'role': 'assistant', 'content': self.nonfunctional_requirement})
            return self.nonfunctional_requirement
        except AttributeError as e:
            return f'处理返回结果时出错：{str(e)}'
