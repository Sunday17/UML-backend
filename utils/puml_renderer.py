# app/utils/puml_renderer.py
import httpx
import base64
import zlib
import string
import asyncio

# PlantUML 官方编码表的魔法字典
plantuml_alphabet = string.digits + string.ascii_uppercase + string.ascii_lowercase + '-_'
base64_alphabet = string.ascii_uppercase + string.ascii_lowercase + string.digits + '+/'
b64_to_plantuml = bytes.maketrans(base64_alphabet.encode('utf-8'), plantuml_alphabet.encode('utf-8'))

# PNG 文件头魔数，用于校验返回内容是否为有效图片
_PNG_MAGIC = b'\x89PNG\r\n\x1a\n'


def _encode_puml(puml_content: str) -> str:
    """将 PlantUML 文本压缩并编码为官方服务器支持的 URL 格式"""
    zlibbed_str = zlib.compress(puml_content.encode('utf-8'))
    compressed_string = zlibbed_str[2:-4]
    return base64.b64encode(compressed_string).translate(b64_to_plantuml).decode('utf-8')


def _is_valid_png(content: bytes) -> bool:
    """检查返回的内容是否为有效的 PNG 图片"""
    return content[:8] == _PNG_MAGIC and len(content) > 100


async def render_puml_to_base64(puml_code: str, max_retries: int = 3) -> str:
    """
    调用远程 PlantUML Server 生成图片，并转为 Base64。

    包含指数退避重试逻辑：首次失败等 1s，二次失败等 2s，
    三次失败等 4s，总共最多尝试 4 次（1 次正常 + 3 次重试）。
    任意一次返回有效 PNG 则立即返回，空结果或非 PNG 内容均视为失败。

    Args:
        puml_code: PlantUML 源码
        max_retries: 最大重试次数（不含首次请求），默认 3 次

    Returns:
        data:image/png;base64,... 格式字符串，或失败时返回空字符串
    """
    if not puml_code or not puml_code.strip():
        return ""

    server_url = f"http://www.plantuml.com/plantuml/png/{_encode_puml(puml_code)}"

    async with httpx.AsyncClient() as client:
        for attempt in range(max_retries + 1):
            try:
                response = await client.get(server_url, timeout=15.0)

                # 状态码非 200 → 重试
                if response.status_code != 200:
                    print(f"[PlantUML] 请求失败（尝试 {attempt + 1}/{max_retries + 1}），"
                          f"状态码 {response.status_code}，{'重试中...' if attempt < max_retries else '已放弃'}")
                # 状态码 200 但内容不是有效 PNG → 重试
                elif not _is_valid_png(response.content):
                    print(f"[PlantUML] 请求失败（尝试 {attempt + 1}/{max_retries + 1}），"
                          f"返回内容无效（非 PNG），{'重试中...' if attempt < max_retries else '已放弃'}")
                else:
                    # 成功：转为 base64 返回
                    b64_data = base64.b64encode(response.content).decode('utf-8')
                    if attempt > 0:
                        print(f"[PlantUML] 第 {attempt} 次重试成功")
                    return f"data:image/png;base64,{b64_data}"

            except httpx.TimeoutException:
                print(f"[PlantUML] 请求超时（尝试 {attempt + 1}/{max_retries + 1}），"
                      f"{'重试中...' if attempt < max_retries else '已放弃'}")
            except Exception as e:
                print(f"[PlantUML] 渲染异常（尝试 {attempt + 1}/{max_retries + 1}）：{e}，"
                      f"{'重试中...' if attempt < max_retries else '已放弃'}")

            # 非最后一次：指数退避等待后再试
            if attempt < max_retries:
                await asyncio.sleep(2 ** attempt)

        # 全部尝试均失败
        print(f"[PlantUML] 渲染失败，已达到最大重试次数（{max_retries + 1} 次）")
        return ""