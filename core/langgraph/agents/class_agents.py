import json
from core.langgraph.state import UMLState
from services.llm import openai_reasoning_completion,openai_chat_completion
from core.prompts.templates import get_template
from core.langgraph.tools.extract_json_from_response import parse_json_from_response

def extract_classes_node(state: UMLState) -> dict:
    """Agent 3: 负责从需求中提取实体类"""
    print("======== [类图-Agent 1] 正在提取实体类(Classes) ========")
    input_text = state["input_text"]
    
    fallback = "从文本提取核心实体类，JSON输出 {\"classes\":[]}"
    prompt_tpl = get_template("cd_entity_prompt", fallback)
    prompt = prompt_tpl.format(input_text=input_text)
    
    #res = openai_chat_completion("你是一个UML专家", [{"role": "user", "content": prompt}])
    res = openai_reasoning_completion(prompt)
    try:
        data = parse_json_from_response(res)
        classes = data.get("classes", [])
        print(f"✅ 提取实体类成功: {classes}")
        return {"classes": classes}
    except Exception as e:
        print(f"❌ 实体类提取失败: {e}")
        return {"classes": []}

def extract_class_details_node(state: UMLState) -> dict:
    """Agent 4: 负责提取每个类的属性和方法"""
    print("======== [类图-Agent 2] 正在提取属性与方法 ========")
    classes = state.get("classes", [])
    if not classes:
        print("⚠️ 未发现实体类，无法提取属性和方法。")
        return {"class_details": {}}

    prompt_tpl = get_template("cd_attr_method_prompt", "提取属性和方法：{\"class_details\":{\"类名\":{\"attributes\":[],\"methods\":[]}}}")
    prompt = prompt_tpl.format(input_text=state["input_text"], classes=classes)
    
    #res = openai_chat_completion("你是一个UML专家", [{"role": "user", "content": prompt}])
    res = openai_reasoning_completion(prompt)
    #print(res)
    try:
        data = parse_json_from_response(res)
        details = data.get("class_details", {})
        #print(details)
        print(f"✅ 属性与方法提取成功: 已解析 {len(details)} 个类")
        return {"class_details": details}
    except Exception as e:
        print(f"❌ 属性与方法提取失败: {e}")
        return {"class_details": {}}

def extract_class_rels_node(state: UMLState) -> dict:
    """Agent 5: 负责分析类之间的 UML 关系"""
    print("======== [类图-Agent 3] 正在分析类间关系 ========")
    classes = state.get("classes", [])
    if len(classes) < 2:
        print("⚠️ 类数量不足，无需分析关系。")
        return {"class_relationships": {}}

    prompt_tpl = get_template("cd_rel_prompt", "提取类关系：{\"association\":[], \"generalization\":[], \"composition\":[], \"aggregation\":[], \"dependency\":[]}")
    prompt = prompt_tpl.format(input_text=state["input_text"], classes=classes)
    
    #res = openai_chat_completion("你是一个UML专家", [{"role": "user", "content": prompt}])
    res = openai_reasoning_completion(prompt)
    try:
        data = parse_json_from_response(res)
        print("✅ 类间逻辑关系解析成功")
        return {"class_relationships": data}
    except Exception as e:
        print(f"❌ 关系解析失败: {e}")
        return {"class_relationships": {}}