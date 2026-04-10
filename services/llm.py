import json
import re
import time 
from openai import OpenAI
from utils.config import OPENAI_API_KEY, OPENAI_MODEL, BASE_URL, REASONING_MODEL


def openai_chat_completion(system_prompt: str, history: list, temperature=0, max_tokens=1500) -> str:
    """通用的 JSON 模式大模型调用接口"""
    client = OpenAI(api_key=OPENAI_API_KEY, base_url=BASE_URL)
    messages = [
        {"role": "system", "content": system_prompt + " 你是一个只输出 JSON 的自动化接口。不要输出任何分析和解释"},
    ]
    messages.extend(history)
    
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={'type': 'json_object'} 
        )
        usage = response.usage
        print(f"[{OPENAI_MODEL}] 消耗: Prompt {usage.prompt_tokens}, Completion {usage.completion_tokens}")
        return response.choices[0].message.content
    except Exception as e:
        print(f"❌ LLM 调用异常: {e}")
        return "{}"


def openai_reasoning_completion(prompt: str, max_tokens=10000) -> str:
    """专为推理大模型（如 deepseek-reasoner）设计的调用接口"""
    start_time = time.time()
    client = OpenAI(api_key=OPENAI_API_KEY, base_url=BASE_URL)
    
    # 推理模型对 system prompt 支持较弱，建议统一作为 user 角色传入
    messages = [
        {"role": "user", "content": prompt}
    ]
    
    try:
        # 注意：这里去掉了 temperature 和 response_format={'type': 'json_object'}
        response = client.chat.completions.create(
            model=REASONING_MODEL,
            messages=messages,
            max_tokens=max_tokens
        )
        usage = response.usage
        cost_time = time.time() - start_time
        print(f"[{REASONING_MODEL}] 消耗: Prompt {usage.prompt_tokens}, Completion {usage.completion_tokens},time: {cost_time:.2f} s")
        return response.choices[0].message.content
    except Exception as e:
        print(f"❌ 推理 LLM 调用异常: {e}")
        return ""