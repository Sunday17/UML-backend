import os

PROMPT_DIR = os.path.join(os.path.dirname(__file__), "..", "prompts")

def get_template(template_name: str, fallback_prompt: str) -> str:
    """读取模板文件，若不存在则使用 fallback"""
    file_path = os.path.join(PROMPT_DIR, f"{template_name}.txt")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return fallback_prompt