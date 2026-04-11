import json
from core.langgraph.state import UMLState
from services.llm import openai_reasoning_completion, openai_chat_completion
from core.prompts.templates import get_template
from core.langgraph.tools.extract_json_from_response import parse_json_from_response


def extract_classes_node(state: UMLState) -> dict:
    """Agent 3: 负责从需求中提取实体类"""
    print("======== [Class-Agent-1] extracting classes ========")
    input_text = state["input_text"]

    fallback = '从文本提取核心实体类，JSON输出 {"classes":[]}'
    prompt_tpl = get_template("cd_entity_prompt", fallback)
    prompt = prompt_tpl.format(input_text=input_text)

    try:
        res = openai_reasoning_completion(prompt)
    except Exception as e:
        print(f"[ERROR] LLM call failed: {e}")
        return {"classes": []}

    try:
        data = parse_json_from_response(res)
        classes = data.get("classes", [])
        print(f"[OK] classes extracted: {classes}")
        return {"classes": classes}
    except Exception as e:
        print(f"[ERROR] class extraction failed: {e}")
        return {"classes": []}


def extract_class_details_node(state: UMLState) -> dict:
    """Agent 4: 负责提取每个类的属性和方法"""
    print("======== [Class-Agent-2] extracting attributes/methods ========")
    classes = state.get("classes", [])
    if not classes:
        print("[WARN] no classes found, skip attribute/method extraction")
        return {"class_details": {}}

    prompt_tpl = get_template(
        "cd_attr_method_prompt",
        '{"class_details":{"ClassName":{"attributes":[],"methods":[]}}}',
    )
    prompt = prompt_tpl.format(input_text=state["input_text"], classes=classes)

    try:
        res = openai_reasoning_completion(prompt)
    except Exception as e:
        print(f"[ERROR] LLM call failed: {e}")
        return {"class_details": {}}

    try:
        data = parse_json_from_response(res)
        details = data.get("class_details", {})
        print(f"[OK] attributes/methods extracted for {len(details)} classes")
        return {"class_details": details}
    except Exception as e:
        print(f"[ERROR] attribute/method extraction failed: {e}")
        return {"class_details": {}}


def extract_class_rels_node(state: UMLState) -> dict:
    """Agent 5: 负责分析类之间的 UML 关系"""
    print("======== [Class-Agent-3] analyzing class relationships ========")
    classes = state.get("classes", [])
    if len(classes) < 2:
        print("[WARN] less than 2 classes, skip relationship analysis")
        return {"class_relationships": {}}

    prompt_tpl = get_template(
        "cd_rel_prompt",
        '{"association":[],"generalization":[],"composition":[],"aggregation":[],"dependency":[]}',
    )
    prompt = prompt_tpl.format(input_text=state["input_text"], classes=classes)

    try:
        res = openai_reasoning_completion(prompt)
    except Exception as e:
        print(f"[ERROR] LLM call failed: {e}")
        return {"class_relationships": {}}

    try:
        data = parse_json_from_response(res)
        print("[OK] class relationships parsed")
        return {"class_relationships": data}
    except Exception as e:
        print(f"[ERROR] class relationship parsing failed: {e}")
        return {"class_relationships": {}}