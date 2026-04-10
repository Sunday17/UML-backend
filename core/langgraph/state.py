# graph/state.py
from typing import TypedDict, List, Dict, Any

class UMLState(TypedDict):
    """LangGraph 运行时的全局状态 (升级为支持多图表)"""
    input_text: str                   # 用户的原始输入文本
    current_diagram: str        # 目标图表，例如 ["usecase"]
    
    # --- 用例图 (Use Case) 数据 ---
    entities: Dict[str, List[str]]    # {角色: [用例]}
    actors: List[str]                 # 独立的角色列表
    usecases: List[str]               # 独立的用例列表
    relationships: Dict[str, Any]     # include, extend, generalization 等关系
    
    # --- 类图 (Class) 数据 ---
    classes: List[str]                # 提取的实体类列表 (需人工确认)
    class_details: Dict[str, Any]     # 类的属性和方法，例如 {"User": {"attributes": [], "methods": []}}
    class_relationships: Dict[str, Any] # 类之间的关系 (泛化、关联、依赖等)

    sequence_data: Dict[str, Dict[str, Any]]