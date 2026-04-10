"""services/uml_service.py — UML 生成服务（Human-in-the-Loop）。

工作流：
1. run_extract()       启动 LangGraph，在断点处自动暂停，返回中间态 JSON
2. resume_and_generate() 合并用户确认数据，续跑图，渲染 PUML，返回代码和图片
3. sync_from_puml()    接收 PUML 代码，逆向解析为 JSON，重新渲染
"""

from typing import Any
import os

from jinja2 import Environment, FileSystemLoader

from core.langgraph.workflow import build_graph
from utils.puml_renderer import render_puml_to_base64
from core.langgraph.tools.puml_parser import sync_puml_to_state

# Jinja2 模板目录（core/templates/puml/）
_TEMPLATE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "core", "templates", "puml"
)
_puml_env = Environment(loader=FileSystemLoader(_TEMPLATE_DIR)) if os.path.isdir(_TEMPLATE_DIR) else None


def _render_puml_from_state(model_type: str, state: dict) -> str:
    """根据 model_type 和当前 State 数据，使用 Jinja2 模板渲染 PUML 代码。"""
    if _puml_env is None:
        return _render_fallback_puml(model_type, state)

    template_map = {
        "usecase": "usecase.puml.j2",
        "class": "class.puml.j2",
        "sequence": "sequence.puml.j2",
    }
    tmpl_name = template_map.get(model_type)
    if not tmpl_name:
        return ""

    try:
        tmpl = _puml_env.get_template(tmpl_name)
        return tmpl.render(**_build_context(model_type, state))
    except Exception as e:
        print(f"⚠️ PUML 模板渲染失败 [{model_type}]: {e}")
        return _render_fallback_puml(model_type, state)


def _build_context(model_type: str, state: dict) -> dict:
    """为每种图类型构建 Jinja2 模板上下文。"""
    if model_type == "usecase":
        rels = state.get("relationships", {})
        entities = state.get("entities", {})
        return {
            "actors": state.get("actors", []),
            "usecases": state.get("usecases", []),
            "entities": entities,
            "relationships": {
                "inclusion": _pairs_to_dict(rels.get("include", [])),
                "extension": _pairs_to_dict(rels.get("extend", [])),
                "uc_gen": _pairs_to_dict(rels.get("uc_generalization", [])),
                "act_gen": _pairs_to_dict(rels.get("actor_generalization", [])),
                "association": entities,
            },
        }

    if model_type == "class":
        return {
            "classes": state.get("classes", []),
            "class_details": state.get("class_details", {}),
            "class_relationships": state.get("class_relationships", {}),
        }

    if model_type == "sequence":
        return {
            "sequence_data": state.get("sequence_data", {}),
        }

    return {}


def _pairs_to_dict(pairs: list) -> dict:
    d = {}
    for p, c in pairs:
        d.setdefault(p, []).append(c)
    return d


def _render_fallback_puml(model_type: str, state: dict) -> str:
    """模板不存在时，用纯 Python 字符串拼接生成 PUML。"""
    if model_type == "usecase":
        lines = ["@startuml"]
        for actor in state.get("actors", []):
            lines.append(f":{actor}:")
        for uc in state.get("usecases", []):
            lines.append(f"({uc})")
        lines.append("@enduml")
        return "\n".join(lines)

    if model_type == "class":
        lines = ["@startuml", "skinparam classAttributeIconSize 0"]
        for cls in state.get("classes", []):
            lines.append(f"class {cls} {{")
            details = state.get("class_details", {}).get(cls, {})
            for attr in details.get("attributes", []):
                lines.append(f"  {attr}")
            for method in details.get("methods", []):
                lines.append(f"  {method}()")
            lines.append("}")
        lines.append("@enduml")
        return "\n".join(lines)

    if model_type == "sequence":
        lines = ["@startuml"]
        seq_data = state.get("sequence_data", {})
        all_parts = []
        for data in seq_data.values():
            all_parts.extend(data.get("participants", []))
        all_parts = list(dict.fromkeys(all_parts))
        for p in all_parts:
            lines.append(f"participant {p}")
        lines.append("@enduml")
        return "\n".join(lines)

    return "@startuml\n@enduml"


def _extract_return_data(model_type: str, state: dict) -> dict:
    """从 LangGraph 运行结果中提取返回给前端的数据。"""
    if model_type == "usecase":
        return {
            "actors": state.get("actors", []),
            "usecases": state.get("usecases", []),
            "entities": state.get("entities", {}),
            "relationships": state.get("relationships", {}),
        }
    if model_type == "class":
        return {
            "classes": state.get("classes", []),
            "class_details": state.get("class_details", {}),
            "class_relationships": state.get("class_relationships", {}),
        }
    if model_type == "sequence":
        return {
            "sequence_data": state.get("sequence_data", {}),
        }
    return {}


class UMLService:
    """UML 生成服务，封装 LangGraph HITL 工作流调用。"""

    def __init__(self):
        # 延迟构建：避免在模块导入时触发（此时 dotenv 尚未加载）
        self._graph = None

    @property
    def app_graph(self):
        """懒加载编译好的 LangGraph 应用。"""
        if self._graph is None:
            self._graph = build_graph()
        return self._graph

    async def run_extract(
        self, model_type: str, requirement_text: str, thread_id: str
    ) -> dict:
        """启动 LangGraph，运行到断点暂停，返回中间态 JSON。

        Args:
            model_type: usecase / class / sequence
            requirement_text: 用户原始需求文本
            thread_id: LangGraph 会话 ID（项目创建时生成）

        Returns:
            提取出的结构化 JSON 数据（供前端表格展示）
        """
        config = {"configurable": {"thread_id": thread_id}}
        initial_state = {
            "input_text": requirement_text,
            "current_diagram": model_type,
            # 清空各图类型的字段，避免状态污染
            "entities": {},
            "actors": [],
            "usecases": [],
            "relationships": {},
            "classes": [],
            "class_details": {},
            "class_relationships": {},
            "sequence_data": {},
        }

        # ainvoke 执行图，在 interrupt_before 设定的节点处自动挂起：
        #   usecase  -> 断点在 relationship_agent
        #   class    -> 断点在 class_attr_method_agent
        #   sequence -> 无断点（完整执行）
        result = await self.app_graph.ainvoke(initial_state, config)
        return _extract_return_data(model_type, result)

    async def resume_and_generate(
        self, model_type: str, thread_id: str, confirmed_data: dict
    ) -> dict:
        """接收用户确认的数据，合并到 checkpoint 状态，续跑图，生成 PUML。

        Args:
            model_type: usecase / class / sequence
            thread_id: LangGraph 会话 ID
            confirmed_data: 用户在表格中修改/确认的数据

        Returns:
            {"puml_code": "...", "image_base64": "data:image/png;base64,..."}
        """
        config = {"configurable": {"thread_id": thread_id}}

        # 1. 获取 checkpoint 中已有的状态（保留 run_extract 的提取结果）
        current_state = self.app_graph.get_state(config).values

        # 2. 合并：原有状态 + 用户确认的数据（后者优先级更高）
        merged_state = {**current_state, **confirmed_data}

        # 3. 将合并后的状态写入 checkpoint（避免覆盖已提取的字段）
        self.app_graph.update_state(config, merged_state)

        # 4. 传入 None 恢复执行，从断点继续直到图结束
        result = await self.app_graph.ainvoke(None, config)

        # 5. 用 Jinja2 模板渲染 PUML 代码
        puml_code = _render_puml_from_state(model_type, result)

        # 6. 调用远程 PlantUML 服务渲染图片
        image_base64 = await render_puml_to_base64(puml_code)

        return {
            "puml_code": puml_code,
            "image_base64": image_base64,
        }

    async def sync_from_puml(
        self, model_type: str, puml_code: str, current_state: dict
    ) -> dict:
        """接收 PUML 代码，逆向解析为 JSON 并重新渲染图片。

        Args:
            model_type: usecase / class / sequence
            puml_code: 用户修改后的 PUML 代码
            current_state: 当前图的内存状态（参考上下文）

        Returns:
            {"new_json_data": {...}, "image_base64": "..."}
        """
        new_data = sync_puml_to_state(model_type, puml_code, current_state)
        image_base64 = await render_puml_to_base64(puml_code)
        return {
            "new_json_data": new_data,
            "image_base64": image_base64,
        }


# 模块级单例，供路由层直接引入使用
uml_service = UMLService()
