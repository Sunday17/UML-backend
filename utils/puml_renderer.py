# app/utils/puml_renderer.py
import httpx
import base64
import zlib
import string

# PlantUML 官方编码表的魔法字典
plantuml_alphabet = string.digits + string.ascii_uppercase + string.ascii_lowercase + '-_'
base64_alphabet = string.ascii_uppercase + string.ascii_lowercase + string.digits + '+/'
b64_to_plantuml = bytes.maketrans(base64_alphabet.encode('utf-8'), plantuml_alphabet.encode('utf-8'))

def _encode_puml(puml_content: str) -> str:
    """将 PlantUML 文本压缩并编码为官方服务器支持的 URL 格式"""
    zlibbed_str = zlib.compress(puml_content.encode('utf-8'))
    compressed_string = zlibbed_str[2:-4]
    return base64.b64encode(compressed_string).translate(b64_to_plantuml).decode('utf-8')

async def render_puml_to_base64(puml_code: str) -> str:
    """
    调用远程/本地 PlantUML Server 生成图片，并转为 Base64
    """
    if not puml_code or not puml_code.strip():
        return ""

    try:
        # 编码代码
        encoded_str = _encode_puml(puml_code)
        # 你可以换成你自己部署的本地 PlantUML Server 地址 (例如 http://localhost:8080)
        server_url = f"http://www.plantuml.com/plantuml/png/{encoded_str}"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(server_url, timeout=15.0)
            
            if response.status_code == 200:
                # 将图片二进制数据转为 Base64，加上前缀，前端 Vue 的 <img :src="res"> 可直接读取
                b64_data = base64.b64encode(response.content).decode('utf-8')
                return f"data:image/png;base64,{b64_data}"
            else:
                print(f"PlantUML 渲染失败, 状态码: {response.status_code}")
                return ""
    except Exception as e:
        print(f"渲染图片发生异常: {e}")
        return ""