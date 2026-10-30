# ReqCompleter v2.0 business methods retained; model transport uses DSH.
import ast
import json
from collections import defaultdict

class ECNUAIModelAgentWithMemory:

    def __init__(self, client, model=None):
        self.client = client
        self.memory = []
        self.system_intro = ''
        self.data_entities = []
        self.use_cases = []
        self.er_model = ''
        self.er_code = ''

    def add_to_memory(self, role, content):
        """添加消息到内存"""
        self.memory.append({'role': role, 'content': content})

    def generate_response(self, user_input):
        return self.client.complete('ERcheckAgent', user_input)

    def get_memory(self):
        """获取当前内存内容"""
        return self.memory

    def clear_memory(self):
        """清空内存"""
        self.memory = []

    def reset_system_intro(self, new_intro):
        """重置系统介绍"""
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

    def generate_er_model(self, use_cases):
        """Generate E-R model based on data entities"""
        self.use_cases = use_cases
        self.memory.append({'role': 'user', 'content': f'Data Entities: {use_cases}'})
        er_system_message = '\n        ·You are responsible for data model design and validation in a requirements team. Based on the following information, please build a complete E-R model.\n        ·Use cases: {uc}\n        ·Please generate a complete E-R model based on the relationships among data entities.\n\n        ·Thinking steps:\n            1. Identify relationships using common sense: Analyze the business scenario and apply domain knowledge to identify relationships among entities.\n            2. Supplement missing entities: Infer potentially missing entities and define their associations. E.g., for "User posts Review", add entity "ReviewRecord".\n            3. Connectivity check and optimization: Ensure the model is at least a weakly connected graph. Address isolated entities by linking or merging where necessary.\n            4. Output the complete data model: Include all entities (including added ones), their attributes, and relationships. At the end, list newly added or removed entities and corresponding use cases.\n\n        ·Rules:\n            1. Comprehensive entity recognition: Cover all extracted entities, and supplement missing ones as needed (within scope).\n            2. Use case updates: Add management use cases for new entities. Indicate removals when entities are deleted or merged.\n            3. Relationships must be logical and business-driven.\n            4. Relationship completeness: Consider all direct and indirect relations.\n            5. Model connectivity: Ensure no isolated entities.\n            6. Output rules: Newly added entities and use cases should be listed using comma delimiters only, with no additional explanation.\n            7. Please strictly control the number of entities less than 6! Please strictly control the number of entities less than 6! Please strictly control the number of entities less than 6!\n\n        ·Example Output:\n            1. Entity Relationship Recognition:\n            - **Student** and **Book**: Borrow\n            - **Admin** and **Book**: Manage\n            - **Book** and **Subject**: Belongs to\n\n            2. Inferred Missing Entities:\n            - **BorrowRecord**: Tracks book borrowing by students\n\n            3. Final ER Model:\n            Entities and Attributes:\n            1. **Student**: StudentID, Name, Age, Class\n            2. **Book**: BookID, Title, Author, SubjectID, Status\n            3. **Admin**: AdminID, Name, Role\n            4. **Subject**: SubjectID, Name\n            5. **BorrowRecord**: RecordID, StudentID, BookID, BorrowDate, ReturnDate\n\n            Relationships:\n            - Student "1" --> "0..*" BorrowRecord : borrows\n            - Admin "1" --> "0..*" Book : manages\n            - Book "1" --> "1" Subject : belongs to\n            - Book o--* BorrowRecord : is borrowed\n\n            New Entities: ReviewRecord, ApplicationResult, Post\n            New Use Cases: Manage ReviewRecord, Manage ApplicationResult, Manage Post\n        '
        prompt = er_system_message.format(uc=use_cases)
        response = self.generate_response(user_input=prompt)
        try:
            self.er_model = response
            self.memory.append({'role': 'assistant', 'content': self.er_model})
            return self.er_model
        except AttributeError as e:
            return f'Error processing response: {str(e)}'

    def check_generate_er_model(self, system_intro, data_entities, use_cases, er_model):
        """Validate and complete ER model"""
        self.system_intro = system_intro
        self.use_cases = use_cases
        self.data_entities = data_entities
        self.memory.append({'role': 'user', 'content': f'Data Entities: {data_entities}'})
        er_system_message = '\n        ·System Introduction: {input}\n        ·Data Entities: {entities}\n        ·Use Cases: {usecase}\n        ·Current ER Model: {erm}\n        ·Please validate and complete the E-R model based on the relationships among data entities.\n\n        ·Validation Points:\n            1. Are there any missing entities?\n            2. Are there missing relationships or isolated entities?\n\n        ·Step-by-step reasoning:\n            1. Verify model completeness: All business-relevant and inferred entities should be included.\n            2. Check the accuracy of entity and relationship definitions based on business logic.\n            3. Ensure connectivity: The model must be at least a weakly connected graph.\n            4. Remove redundancy: Merge or delete duplicated or unnecessary entities/relationships.\n            5. Check consistency: Ensure naming and relationships align with business rules.\n\n        ·Rules:\n            1. Completeness: Cover all essential entities, relationships, and attributes.\n            2. Accuracy: All definitions must be correct and logical.\n            3. Connectivity: No isolated entities; weak connectivity required.\n            4. Redundancy: No unnecessary duplication.\n            5. Consistency: Naming, data types, and logic must align.\n            6. Use Case Update: Add use cases for managing new entities.\n\n        ·Important: For newly added entities and use cases, just list them with commas, no explanation.\n        ·请用中文回答\n        ·Example Output:\n            Entities:\n            1. User: UserID, Name, Gender, Age, Email, Password, RegisterTime\n            2. Agency: AgencyID, Name, Country, Quality, Fee, Contact\n            3. Review: ReviewID, UserID, AgencyID, Content, Rating, PublishTime\n            4. ReviewRecord: RecordID, ReviewID, UserID, Feedback, Date\n            5. Project: ProjectID, Country, City, Major, Institution, Requirements, Duration\n            6. Post: PostID, UserID, Title, Content, Keywords, Category, PublishTime\n            7. ApplicationResult: ResultID, UserID, ProjectID, Status, Background, Time\n            8. Admin: AdminID, Name, Role, Password, LastLoginTime\n\n            Relationships:\n            User "1" --> "0..*" Review : posts\n            Agency "1" --> "0..*" Review : posts\n            User "1" --> "0..*" Post : posts\n            Project "1" --> "0..*" Post : posts\n            User "1" --> "0..*" ApplicationResult : applies\n            Project "1" --> "0..*" ApplicationResult : contains\n            Review "1" --> "0..*" ReviewRecord : contains\n            User "1" --> "0..*" ReviewRecord : provides feedback\n\n            New Entities: ReviewRecord, ApplicationResult, Post\n            New Use Cases: Manage ReviewRecord, Manage ApplicationResult, Manage Post\n        '
        prompt = er_system_message.format(input=system_intro, entities=','.join(data_entities), usecase=','.join(use_cases), erm=er_model)
        response = self.generate_response(user_input=prompt)
        try:
            self.er_model = response
            self.memory.append({'role': 'assistant', 'content': self.er_model})
            return self.er_model
        except AttributeError as e:
            return f'Error processing response: {str(e)}'

    def Complete_ER_Diagram(self, old_er_diagram, use_case_model):
        er_completion_prompt = '\n        ·You are responsible for completing and correcting the system\'s E-R diagram based on new use case information.  \n\n        ·Input:\n            (a) Old E-R Diagram:\n            {er_diagram}\n\n            (b) New Use Case Model:\n            {use_case_model}\n\n        ·Task Instructions:\n            1. Identify any **new data entities** introduced or implied by the use case model.\n            2. Define **relationships**:\n                - Between new entities\n                - Between new entities and existing entities\n                (Use context from use case descriptions)\n            3. Detect **isolated entities** (i.e., entities not connected to any other).\n            4. Delete isolated entities and remove any associated use cases from the model.\n        ·请用中文回答\n        ·Output Format:\n            Entities:\n            1. User: UserID, Name, Gender, Age, Email, Password, RegisterTime\n            2. Agency: AgencyID, Name, Country, Quality, Fee, Contact\n            3. Review: ReviewID, UserID, AgencyID, Content, Rating, PublishTime\n            4. ReviewRecord: RecordID, ReviewID, UserID, Feedback, Date\n            5. Project: ProjectID, Country, City, Major, Institution, Requirements, Duration\n            6. Post: PostID, UserID, Title, Content, Keywords, Category, PublishTime\n            7. ApplicationResult: ResultID, UserID, ProjectID, Status, Background, Time\n            8. Admin: AdminID, Name, Role, Password, LastLoginTime\n\n            Relationships:\n            User "1" --> "0..*" Review : posts\n            Agency "1" --> "0..*" Review : posts\n            User "1" --> "0..*" Post : posts\n            Project "1" --> "0..*" Post : posts\n            User "1" --> "0..*" ApplicationResult : applies\n            Project "1" --> "0..*" ApplicationResult : contains\n            Review "1" --> "0..*" ReviewRecord : contains\n            User "1" --> "0..*" ReviewRecord : provides feedback\n\n            Changes:\n            - New Entities: Add: ReviewRecord, ApplicationResult\n            - New Use Cases: Manage ReviewRecord, Manage ApplicationResult\n            - Deleted Entities: Post\n            - Deleted Use Cases: Manage Post\n\n        ·Rules:\n            - Do not invent entities not grounded in the use cases.\n            - Ensure all use cases refer to entities that exist in the updated E-R diagram.\n            - Relationships should be meaningful and based on real data interactions implied by the use cases.\n            - Use clear naming and structure.\n\n        ·Begin the update now using the provided content.\n        '
        prompt = er_completion_prompt.format(er_diagram=old_er_diagram, use_case_model=use_case_model)
        response = self.generate_response(prompt)
        try:
            self.updated_er_and_usecase = response
            self.memory.append({'role': 'assistant', 'content': self.updated_er_and_usecase})
            return self.updated_er_and_usecase
        except AttributeError as e:
            return f'Error handling response: {str(e)}'

    def generate_er_code(self, er_model):
        self.er_model = er_model
        'Generate PlantUML E-R diagram code from conceptual ER model.'
        self.memory.append({'role': 'user', 'content': f'Conceptual E-R Model: {er_model}'})
        class_system_message = '\n        ·You are a tool that helps developers generate PlantUML E-R diagram code based on conceptual E-R model descriptions.\n        ·Generate PlantUML code from the following E-R model.\n        ·E-R Model: {model}\n        ·Do not include methods (operations).\n        ·Do not indicate primary or foreign keys in the E-R diagram.\n        ·Be sure to add cardinality and relationship names, e.g.:\n            User "1" --> "0..*" BorrowRecord : borrows\n            Book "1" --> "0..1" Subject : belongs to\n        ·Return only valid PlantUML code representing the E-R diagram (no explanations).\n        '
        prompt = class_system_message.format(model=er_model)
        response = self.generate_response(prompt)
        try:
            self.er_code = response
            self.memory.append({'role': 'assistant', 'content': self.er_code})
            return self.er_code
        except AttributeError as e:
            return f'Error processing response: {str(e)}'
