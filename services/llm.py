import time
from openai import OpenAI
from core.config import settings


def openai_chat_completion(system_prompt: str, history: list, temperature=0, max_tokens=1500) -> str:
    """通用的 JSON 模式大模型调用接口"""
    client = OpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.BASE_URL)
    messages = [
        {"role": "system", "content": system_prompt + " 你是一个只输出 JSON 的自动化接口。不要输出任何分析和解释"},
    ]
    messages.extend(history)

    try:
        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        usage = response.usage
        print(f"[{settings.OPENAI_MODEL}] usage: prompt={usage.prompt_tokens}, completion={usage.completion_tokens}")
        return response.choices[0].message.content
    except Exception as e:
        print(f"[ERROR] LLM call failed: {e}")
        raise


def openai_reasoning_completion(prompt: str, max_tokens=10000) -> str:
    """专为推理大模型（如 deepseek-reasoner）设计的调用接口"""
    start_time = time.time()
    client = OpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.BASE_URL)

    messages = [{"role": "user", "content": prompt}]

    try:
        response = client.chat.completions.create(
            model=settings.REASONING_MODEL,
            messages=messages,
            max_tokens=max_tokens,
        )
        usage = response.usage
        cost_time = time.time() - start_time
        print(f"[{settings.REASONING_MODEL}] usage: prompt={usage.prompt_tokens}, completion={usage.completion_tokens}, time={cost_time:.2f}s")
        return response.choices[0].message.content
    except Exception as e:
        print(f"[ERROR] reasoning LLM call failed: {e}")
        raise