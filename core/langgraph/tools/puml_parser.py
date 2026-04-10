import json
from services.llm import openai_chat_completion
from core.prompts.templates import get_template

def sync_puml_to_state(diagram_type: str, puml_code: str, current_state: dict) -> dict:
    """读取修改后的 PUML 代码，调用大模型将其变更同步回 State JSON"""
    print(f"🔄 正在分析 {diagram_type} PUML 的人工修改内容并同步至数据流...")
    
    prompt_tpl = get_template("puml_sync_prompt", "将PUML解析为JSON")
    
    # 提取当前状态中与该图相关的核心字段，避免把整个大字典传进去污染上下文
    if diagram_type == "usecase":
        original_data = {
            "entities": current_state.get("entities"),
            "actors": current_state.get("actors"),
            "usecases": current_state.get("usecases"),
            "relationships": current_state.get("relationships")
        }
    elif diagram_type == "class":
        original_data = {
            "classes": current_state.get("classes"),
            "class_details": current_state.get("class_details"),
            "class_relationships": current_state.get("class_relationships")
        }
    else:
        return current_state

    prompt = prompt_tpl.format(
        diagram_type=diagram_type,
        original_json=json.dumps(original_data, ensure_ascii=False),
        puml_code=puml_code
    )
    
    res = openai_chat_completion("你是一个JSON还原器", [{"role": "user", "content": prompt}])
    updated_data = json.loads(res)
    
    if updated_data:
        print("✅ PUML 修改已成功解析并合并至全局 State！")
        return updated_data
    else:
        print("⚠️ PUML 逆向解析失败，将维持原状态。")
        return {}