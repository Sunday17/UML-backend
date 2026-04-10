from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from core.langgraph.state import UMLState
from core.langgraph.agents.usecase_agents import extract_entities_node, extract_relationships_node
from core.langgraph.agents.class_agents import extract_classes_node, extract_class_details_node, extract_class_rels_node
from core.langgraph.agents.sequence_agents import extract_seq_participants_node, extract_seq_messages_node

def route_start(state: UMLState):
    diagram = state.get("current_diagram")
    if diagram == "usecase": return "entity_agent"
    elif diagram == "class": return "class_entity_agent"
    elif diagram == "sequence": return "seq_participant_agent" 
    return END

def build_graph():
    """构建并编译 Multi-Agent 并行工作流"""
    workflow = StateGraph(UMLState)
    
    # --- 1. 注册用例图节点 ---
    workflow.add_node("entity_agent", extract_entities_node)
    workflow.add_node("relationship_agent", extract_relationships_node)
    
    # --- 2. 注册类图节点 ---
    workflow.add_node("class_entity_agent", extract_classes_node)
    workflow.add_node("class_attr_method_agent", extract_class_details_node)
    workflow.add_node("class_rel_agent", extract_class_rels_node)

    # 注册时序图节点
    workflow.add_node("seq_participant_agent", extract_seq_participants_node)
    workflow.add_node("seq_message_agent", extract_seq_messages_node)
    
    # 3. 从 START 路由到指定的流水线
    workflow.add_conditional_edges(
        START,
        route_start,
        {
            "entity_agent": "entity_agent",
            "class_entity_agent": "class_entity_agent",
            "seq_participant_agent": "seq_participant_agent",
            END: END
        }
    )
    
    # --- 4. 编排用例图内部边 ---
    workflow.add_edge("entity_agent", "relationship_agent")
    workflow.add_edge("relationship_agent", END)
    
    # --- 5. 编排类图内部边 ---
    workflow.add_edge("class_entity_agent", "class_attr_method_agent")
    workflow.add_edge("class_attr_method_agent", "class_rel_agent")
    workflow.add_edge("class_rel_agent", END)

    # 时序图内部流转
    workflow.add_edge("seq_participant_agent", "seq_message_agent")
    workflow.add_edge("seq_message_agent", END)
    
    # --- 6. 开启记忆存储 (用于支持 Human-in-the-loop) ---
    memory = MemorySaver()
    app = workflow.compile(
        checkpointer=memory,
        # 拦截点：
        # 1. relationship_agent 前 (确认用例实体)
        # 2. class_attr_method_agent 前 (确认类实体)
        interrupt_before=["relationship_agent", "class_attr_method_agent"] 
    )
    
    return app