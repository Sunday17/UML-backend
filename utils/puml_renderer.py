"""PlantUML 渲染工具：将 PUML 源码转为官方在线 URL。"""

import base64
import zlib
import string

# PlantUML 官方编码表的魔法字典
plantuml_alphabet = string.digits + string.ascii_uppercase + string.ascii_lowercase + '-_'
base64_alphabet = string.ascii_uppercase + string.ascii_lowercase + string.digits + '+/'
b64_to_plantuml = bytes.maketrans(base64_alphabet.encode('utf-8'), plantuml_alphabet.encode('utf-8'))


def _encode_puml(puml_content: str) -> str:
    """将 PlantUML 文本压缩并编码为官方服务器支持的 URL 格式。"""
    zlibbed_str = zlib.compress(puml_content.encode('utf-8'))
    compressed_string = zlibbed_str[2:-4]
    return base64.b64encode(compressed_string).translate(b64_to_plantuml).decode('utf-8')


async def render_puml_to_url(puml_code: str) -> str:
    """
    将 PlantUML 源码转为官方在线渲染 URL。

    直接拼接格式，无需发起网络请求：
    http://www.plantuml.com/plantuml/png/{encoded_str}

    Args:
        puml_code: PlantUML 源码

    Returns:
        PlantUML 官方 PNG 渲染地址，失败时返回空字符串
    """
    if not puml_code or not puml_code.strip():
        return ""

    encoded = _encode_puml(puml_code)
    return f"http://www.plantuml.com/plantuml/png/{encoded}"
