import json
import re
from core.langgraph.state import UMLState
from services.llm import openai_chat_completion, openai_reasoning_completion
from core.prompts.templates import get_template


def extract_entities_node(state: UMLState) -> dict:
    """Agent 1: 负责从需求文本中提取角色和用例"""
    print("======== [Agent 1] extracting entities ========")
    input_text = state["input_text"]

    fallback = "从文本中提取角色和用例，JSON格式输出：{{\"角色\":[\"用例\"]}}。文本：{input_text}"
    prompt_tpl = get_template("ee_template", fallback)

    prompt = prompt_tpl.format(input_text=input_text)
    system_msg = "你是一个 UML 需求分析助手。请将需求中的参与者和用例提取为 JSON 格式。"

    try:
        res = openai_chat_completion(
            system_prompt=system_msg,
            history=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        print(f"[ERROR] LLM call failed: {e}")
        return {"entities": {}, "actors": [], "usecases": []}

    try:
        data = json.loads(res)
        actors = list(data.keys())
        uc_set = set()
        for ucs in data.values():
            uc_set.update(ucs)
        usecases = list(uc_set)

        print(f"[OK] entities extracted: {len(actors)} actors / {len(usecases)} usecases")
        return {"entities": data, "actors": actors, "usecases": usecases}
    except Exception as e:
        print(f"[ERROR] entity parsing failed: {e}")
        return {"entities": {}, "actors": [], "usecases": []}


def extract_relationships_node(state: UMLState) -> dict:
    """Agent 2: 负责分析实体之间的 UML 关系"""
    print("======== [Agent 2] analyzing relationships ========")
    if not state.get("usecases"):
        print("[WARN] no usecases, skip relationship extraction")
        return {"relationships": {}}

    fallback = "基于以下角色{actors}和用例{usecases}，从文本提取关系。文本：{input_text}"
    era_tpl = get_template("era_template", fallback)

    prompt = era_tpl.format(
        input_text=state["input_text"],
        actors=state["actors"],
        usecases=state["usecases"],
    )

    try:
        res = openai_chat_completion(
            system_prompt="你是一个只输出JSON的UML分析专家",
            history=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        print(f"[ERROR] LLM call failed: {e}")
        return {"relationships": {}}

    try:
        match = re.search(r'(\{.*\})', res, re.DOTALL)
        data = json.loads(match.group(1)) if match else json.loads(res)
        print("[OK] relationships parsed")
        return {"relationships": data}
    except Exception as e:
        print(f"[ERROR] relationship parsing failed: {e}")
        return {"relationships": {}}