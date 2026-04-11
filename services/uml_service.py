"""services/uml_service.py — UML 生成服务（Human-in-the-Loop）。

工作流：
1. run_extract()       启动 LangGraph，在断点处自动暂停，返回中间态 JSON
2. resume_and_generate() 合并用户确认数据，续跑图，渲染 PUML，返回代码和图片
3. sync_from_puml()    接收 PUML 代码，逆向解析为 JSON，重新渲染
4. get_missing_dependencies() 序列图专用：检查 usecase/class 是否已生成
"""

from typing import Any, Optional
import os

from jinja2 import Environment, FileSystemLoader

from core.langgraph.workflow import build_graph
from utils.puml_renderer import render_puml_to_url
from core.langgraph.tools.puml_parser import sync_puml_to_state
from services.database import database_service

# Jinja2 模板目录（core/templates/puml/）
_TEMPLATE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "core", "templates", "puml"
)
_puml_env = Environment(loader=FileSystemLoader(_TEMPLATE_DIR)) if os.path.isdir(_TEMPLATE_DIR) else None


def _render_puml_from_state(model_type: str, state: dict) -> str:
    """根据 model_type 和当前 State 数据，使用 Jinja2 模板渲染 PUML 代码。

    注意：时序图不走此函数，由 _render_single_sequence_diagram 按每个用例单独渲染。
    """
    if model_type == "sequence":
        return ""  # sequence 由 generate_multi_sequence 单独处理
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
        print(f"[WARN] PUML template render failed [{model_type}]: {e}")
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


def _render_single_sequence_diagram(usecase_name: str, seq_data: dict) -> str:
    """渲染单个用例的时序图 PUML 代码。"""
    if _puml_env is None:
        return _render_seq_fallback(usecase_name, seq_data)

    try:
        tmpl = _puml_env.get_template("sequence.puml.j2")
        return tmpl.render(
            usecase_name=usecase_name,
            participants=seq_data.get("participants", []),
            interactions=seq_data.get("interactions", []),
            messages=seq_data.get("messages", []),
        )
    except Exception as e:
        print(f"[WARN] sequence template render failed for [{usecase_name}]: {e}")
        return _render_seq_fallback(usecase_name, seq_data)


def _render_seq_fallback(usecase_name: str, seq_data: dict) -> str:
    """sequence 模板不存在时的兜底渲染。"""
    lines = ["@startuml", f"title 时序图：{usecase_name}"]
    participants = seq_data.get("participants", [])
    all_parts = []
    for p in participants:
        if isinstance(p, dict):
            all_parts.append(p.get("name", str(p)))
        else:
            all_parts.append(str(p))
    for p in all_parts:
        lines.append(f"participant {p}")
    lines.append("@enduml")
    return "\n".join(lines)


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
        self, model_type: str, requirement_text: str, thread_id: str, project_id: int = None, db=None, selected_usecases: list = None
    ) -> dict:
        """启动 LangGraph，运行到断点暂停，返回中间态 JSON。

        时序图特殊处理：从数据库读取已确认的 usecase/class 数据填充状态。

        Args:
            model_type: usecase / class / sequence
            requirement_text: 用户原始需求文本
            thread_id: LangGraph 会话 ID（项目创建时生成）
            project_id: 项目 ID（时序图回填时需要）
            db: 数据库会话（时序图回填时需要传入）
            selected_usecases: 时序图专用，前端选择的用例列表

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
            "selected_usecases": selected_usecases or [],
            "sequence_data": {},
        }

        # 时序图：从数据库读取 usecase/class 完整数据填充状态
        if model_type == "sequence" and db and project_id:
            db_filled = await self._fill_state_from_db(db, project_id)
            if db_filled:
                print(f"[Sequence Extract] 从数据库回填状态: {list(db_filled.keys())}")
                initial_state = {**initial_state, **db_filled}
            else:
                print("[Sequence Extract] 警告：数据库中未找到 usecase/class 数据")

        # ainvoke 执行图，在 interrupt_before 设定的节点处自动挂起：
        #   usecase  -> 断点在 relationship_agent
        #   class    -> 断点在 class_attr_method_agent
        #   sequence -> 无断点（完整执行）
        result = await self.app_graph.ainvoke(initial_state, config)
        return _extract_return_data(model_type, result)

    async def get_missing_dependencies(
        self, db, project_id: int
    ) -> list[str]:
        """时序图专用：检查 usecase / class 是否都已生成并确认，返回缺失的类型列表。"""
        missing = []
        for dep in ("usecase", "class"):
            model = await database_service.get_latest_confirmed_model(db, project_id, dep)
            if not model:
                missing.append(dep)
        return missing

    async def _fill_state_from_db(self, db, project_id: int) -> dict:
        """时序图专用：从数据库读取已确认的 usecase/class JSON，填充到状态中。

        读取完整的 usecase 和 class 数据（actors, usecases, entities, relationships, classes,
        class_details, class_relationships），写入 checkpoint 状态供时序图生成使用。
        """
        filled = {}

        # 读取 usecase 数据（要求已确认；路由层已有前置依赖检查确保此处有值）
        usecase_model = await database_service.get_latest_confirmed_model(db, project_id, "usecase")
        if usecase_model and usecase_model.data_json:
            filled["actors"] = usecase_model.data_json.get("actors", [])
            filled["usecases"] = usecase_model.data_json.get("usecases", [])
            filled["entities"] = usecase_model.data_json.get("entities", {})
            filled["relationships"] = usecase_model.data_json.get("relationships", {})

        # 读取 class 数据（要求已确认；路由层已有前置依赖检查确保此处有值）
        class_model = await database_service.get_latest_confirmed_model(db, project_id, "class")
        if class_model and class_model.data_json:
            filled["classes"] = class_model.data_json.get("classes", [])
            filled["class_details"] = class_model.data_json.get("class_details", {})
            filled["class_relationships"] = class_model.data_json.get("class_relationships", {})

        return filled

    async def resume_and_generate(
        self, model_type: str, thread_id: str, confirmed_data: dict, project_id: int = None, db=None
    ) -> dict:
        """接收用户确认的数据，合并到 checkpoint 状态，续跑图，生成 PUML。

        时序图特殊处理：必须从数据库读取已确认的 usecase/class JSON 数据填充状态，
        再续跑（即使 checkpoint 中有数据也会覆盖，确保数据一致性）。

        Args:
            model_type: usecase / class / sequence
            thread_id: LangGraph 会话 ID
            confirmed_data: 用户在表格中修改/确认的数据
            project_id: 项目 ID（时序图回填时需要）
            db: 数据库会话（时序图回填时需要传入）

        Returns:
            {"puml_code": "...", "image_url": "http://www.plantuml.com/plantuml/png/..."}
        """
        config = {"configurable": {"thread_id": thread_id}}

        # 1. 获取 checkpoint 中已有的状态
        current_state = self.app_graph.get_state(config).values

        # 2. 时序图：强制从数据库回填 usecase/class 完整数据
        if model_type == "sequence" and db and project_id:
            db_filled = await self._fill_state_from_db(db, project_id)
            if db_filled:
                print(f"[Sequence] 从数据库回填状态: {list(db_filled.keys())}")
                current_state = {**current_state, **db_filled}
            else:
                print("[Sequence] 警告：数据库中未找到 usecase/class 数据")

        # 3. 合并：原有状态 + 用户确认的数据（后者优先级更高）
        merged_state = {**current_state, **confirmed_data}

        # 4. 将合并后的状态写入 checkpoint（避免覆盖已提取的字段）
        self.app_graph.update_state(config, merged_state)

        # 5. 传入 None 恢复执行，从断点继续直到图结束
        result = await self.app_graph.ainvoke(None, config)

        # 6. 时序图：按每个用例单独渲染 PUML 和图片
        if model_type == "sequence":
            return await self.generate_multi_sequence(result)

        # 7. 用 Jinja2 模板渲染 PUML 代码
        puml_code = _render_puml_from_state(model_type, result)

        # 8. 调用远程 PlantUML 服务渲染图片
        image_url = await render_puml_to_url(puml_code)

        return {
            "puml_code": puml_code,
            "image_url": image_url,
        }

    async def generate_multi_sequence(self, result_state: dict) -> dict:
        """时序图专用：为每个用例单独生成一张 PUML 图和图片。

        Args:
            result_state: LangGraph 运行结束后的完整状态（含 sequence_data）

        Returns:
            {
                "diagrams": [
                    {"usecase_name": "用例A", "puml_code": "...", "image_url": "..."},
                    {"usecase_name": "用例B", "puml_code": "...", "image_url": "..."},
                ]
            }
        """
        sequence_data = result_state.get("sequence_data", {})
        diagrams = await self._render_sequence_diagrams(sequence_data)
        print(f"[Sequence] 共生成 {len(diagrams)} 张时序图")
        return {"diagrams": diagrams}

    async def _render_sequence_diagrams(self, sequence_data: dict) -> list:
        """渲染每个用例的时序图，返回 PUML + 图片列表。"""
        diagrams = []
        for usecase_name, seq_data in sequence_data.items():
            puml_code = _render_single_sequence_diagram(usecase_name, seq_data)
            image_url = await render_puml_to_url(puml_code)
            diagrams.append({
                "usecase_name": usecase_name,
                "puml_code": puml_code,
                "image_url": image_url,
            })
            print(f"[Sequence] 渲染完成: {usecase_name} ({len(puml_code)} chars)")
        return diagrams

    async def sync_from_puml(
        self, model_type: str, puml_code: str, current_state: dict, usecase_name: str = None
    ) -> dict:
        """接收 PUML 代码，逆向解析为 JSON，重新渲染图片，并更新数据库。

        时序图支持：传入 usecase_name 则只同步该用例的图。

        Args:
            model_type: usecase / class / sequence
            puml_code: 用户修改后的 PUML 代码
            current_state: 当前图的内存状态（参考上下文）
            usecase_name: 时序图专用，指定要同步的用例名称

        Returns:
            {"image_url": "..."} 或 {"diagrams": [...]}（时序图）
        """
        if model_type == "sequence":
            new_json_data = sync_puml_to_state(model_type, puml_code, current_state)
            if usecase_name:
                seq_data = new_json_data.get(usecase_name, {})
                puml = _render_single_sequence_diagram(usecase_name, seq_data)
                image_url = await render_puml_to_url(puml)
                return {"usecase_name": usecase_name, "new_json_data": new_json_data, "image_url": image_url, "puml_code": puml}
            diagrams = []
            for uc_name, seq_data in new_json_data.items():
                puml = _render_single_sequence_diagram(uc_name, seq_data)
                image_url = await render_puml_to_url(puml)
                diagrams.append({"usecase_name": uc_name, "puml_code": puml, "image_url": image_url})
            return {"diagrams": diagrams, "new_json_data": new_json_data}

        new_json_data = sync_puml_to_state(model_type, puml_code, current_state)
        image_url = await render_puml_to_url(puml_code)
        return {
            "new_json_data": new_json_data,
            "image_url": image_url,
        }


# 模块级单例，供路由层直接引入使用
uml_service = UMLService()
