"""PlantUML code parser and reverse-sync utilities."""

import json
from typing import Dict, Any

from services.llm import openai_chat_completion
from core.prompts.templates import get_template


def parse_puml_to_json(puml_code: str) -> Dict[str, Any]:
    """将 PlantUML 代码直接解析为 JSON 数据结构（用于逆向同步）。"""
    return sync_puml_to_state(diagram_type="usecase", puml_code=puml_code, current_state={})


def sync_puml_to_state(
    diagram_type: str, puml_code: str, current_state: Dict[str, Any]
) -> Dict[str, Any]:
    """读取修改后的 PUML 代码，调用大模型将其变更同步回 State JSON。"""
    print(f"[SYNC] analyzing {diagram_type} PUML changes and syncing to state...")

    prompt_tpl = get_template("puml_sync_prompt", "将PUML解析为JSON")

    if diagram_type == "usecase":
        original_data = {
            "entities": current_state.get("entities"),
            "actors": current_state.get("actors"),
            "usecases": current_state.get("usecases"),
            "relationships": current_state.get("relationships"),
        }
    elif diagram_type == "class":
        original_data = {
            "classes": current_state.get("classes"),
            "class_details": current_state.get("class_details"),
            "class_relationships": current_state.get("class_relationships"),
        }
    elif diagram_type == "sequence":
        original_data = {
            "sequence_data": current_state.get("sequence_data", {}),
        }

    prompt = prompt_tpl.format(
        diagram_type=diagram_type,
        original_json=json.dumps(original_data, ensure_ascii=False),
        puml_code=puml_code,
    )

    res = openai_chat_completion(
        "你是一个JSON还原器，只输出有效的JSON。",
        [{"role": "user", "content": prompt}],
    )

    try:
        updated_data = json.loads(res)
        print("[OK] PUML changes parsed and merged to state")
        return updated_data
    except Exception as e:
        print(f"[WARN] PUML reverse-parse failed: {e}, returning empty dict")
        return {}
