import json
from core.langgraph.state import UMLState
from services.llm import openai_reasoning_completion, openai_chat_completion
from core.prompts.templates import get_template
from core.langgraph.tools.extract_json_from_response import parse_json_from_response


def extract_seq_participants_node(state: UMLState) -> dict:
    """Agent 6: 为选中的用例提取参与者"""
    print("======== [Seq-Agent-1] extracting participants ========")
    input_text = state.get("input_text", "")
    actors = state.get("actors", [])
    classes = state.get("classes", [])
    sequence_data = state.get("sequence_data", {})
    prompt_tpl = get_template("sd_participant_prompt", "")

    # 仅处理被选中的用例
    target_usecases = state.get("selected_usecases", [])
    if not target_usecases:
        print("[WARN] no selected_usecases, skip participant extraction")
        return {"sequence_data": sequence_data}

    for uc in target_usecases:
        print(f"  -> analyzing participants for: [{uc}]")
        prompt = prompt_tpl.format(
            input_text=input_text,
            current_usecase=uc,
            actors=actors,
            classes=classes,
        )
        try:
            res = openai_chat_completion(
                "你是一个资深的软件系统架构师，精通UML时序图设计与系统解耦。",
                [{"role": "user", "content": prompt}],
            )
        except Exception as e:
            print(f"[ERROR] LLM call failed for {uc}: {e}")
            data = {}
        else:
            try:
                data = parse_json_from_response(res)
            except Exception as e:
                print(f"[ERROR] participant JSON parse failed for {uc}: {e}")
                data = {}

        if uc not in sequence_data:
            sequence_data[uc] = {}
        sequence_data[uc]["participants"] = data.get("participants", [])

    return {"sequence_data": sequence_data}


def extract_seq_messages_node(state: UMLState) -> dict:
    """Agent 7: 为选中的用例编排消息序列"""
    print("======== [Seq-Agent-2] arranging interaction messages ========")
    input_text = state.get("input_text", "")
    sequence_data = state.get("sequence_data", {})
    prompt_tpl = get_template("sd_message_prompt", "")

    # 仅处理被选中的用例
    target_usecases = state.get("selected_usecases", [])
    if not target_usecases:
        print("[WARN] no selected_usecases, skip message extraction")
        return {"sequence_data": sequence_data}

    for uc in target_usecases:
        print(f"  -> arranging messages for: [{uc}]")
        uc_data = sequence_data.get(uc, {})
        participants = uc_data.get("participants", [])
        if not participants:
            continue

        prompt = prompt_tpl.format(
            input_text=input_text,
            current_usecase=uc,
            participants=participants,
        )
        try:
            res = openai_reasoning_completion(prompt)
        except Exception as e:
            print(f"[ERROR] LLM call failed for {uc}: {e}")
            msg_data = {}
        else:
            try:
                msg_data = parse_json_from_response(res)
            except Exception as e:
                print(f"[ERROR] message JSON parse failed for {uc}: {e}")
                msg_data = {}

        sequence_data[uc]["interactions"] = msg_data.get("interactions", [])

    print("[OK] all sequence diagram data assembled")
    return {"sequence_data": sequence_data}