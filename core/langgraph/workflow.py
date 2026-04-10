"""LangGraph workflow builder for UML generation with HITL (Human-in-the-Loop)."""

from langgraph.graph import StateGraph
from langgraph.constants import START, END
from langgraph.checkpoint.memory import MemorySaver

from core.langgraph.state import UMLState
from core.langgraph.agents.usecase_agents import (
    extract_entities_node,
    extract_relationships_node,
)
from core.langgraph.agents.class_agents import (
    extract_classes_node,
    extract_class_details_node,
    extract_class_rels_node,
)
from core.langgraph.agents.sequence_agents import (
    extract_seq_participants_node,
    extract_seq_messages_node,
)


def route_start(state: UMLState) -> str:
    """根据 current_diagram 路由到对应的提取流水线。"""
    diagram = state.get("current_diagram", "").strip().lower()
    if diagram == "usecase":
        return "entity_agent"
    if diagram == "class":
        return "class_entity_agent"
    if diagram == "sequence":
        return "seq_participant_agent"
    # 未指定 diagram 时直接结束（不阻塞）
    return "__end__"


def build_graph():
    """构建并编译支持 HITL 的多图类型 LangGraph 工作流。"""
    workflow = StateGraph(UMLState)

    # --- 1. 用例图节点 ---
    workflow.add_node("entity_agent", extract_entities_node)
    workflow.add_node("relationship_agent", extract_relationships_node)

    # --- 2. 类图节点 ---
    workflow.add_node("class_entity_agent", extract_classes_node)
    workflow.add_node("class_attr_method_agent", extract_class_details_node)
    workflow.add_node("class_rel_agent", extract_class_rels_node)

    # --- 3. 时序图节点 ---
    workflow.add_node("seq_participant_agent", extract_seq_participants_node)
    workflow.add_node("seq_message_agent", extract_seq_messages_node)

    # --- 4. 从 START 路由到指定流水线 ---
    workflow.add_conditional_edges(
        START,
        route_start,
        {
            "entity_agent": "entity_agent",
            "class_entity_agent": "class_entity_agent",
            "seq_participant_agent": "seq_participant_agent",
            "__end__": END,
        },
    )

    # --- 5. 用例图内部流转 ---
    workflow.add_edge("entity_agent", "relationship_agent")
    workflow.add_edge("relationship_agent", END)

    # --- 6. 类图内部流转 ---
    workflow.add_edge("class_entity_agent", "class_attr_method_agent")
    workflow.add_edge("class_attr_method_agent", "class_rel_agent")
    workflow.add_edge("class_rel_agent", END)

    # --- 7. 时序图内部流转 ---
    workflow.add_edge("seq_participant_agent", "seq_message_agent")
    workflow.add_edge("seq_message_agent", END)

    # --- 8. 编译：启用内存断点存储 + 设置拦截点 ---
    memory = MemorySaver()
    app = workflow.compile(
        checkpointer=memory,
        interrupt_before=["relationship_agent", "class_attr_method_agent"],
    )

    return app


# 模块级单例：编译好的 LangGraph 应用（供 services/uml_service.py 等模块直接引用）
app_graph = build_graph()
