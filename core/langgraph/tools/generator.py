import os
import json
from jinja2 import Environment, FileSystemLoader
from plantuml import PlantUML

# 模板目录配置
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates", "puml")

def _to_dict(pair_list):
    """将 [["A","B"]] 转为 {"A":["B"]} 格式，方便模板引擎遍历"""
    d = {}
    if pair_list:
        for p, c in pair_list:
            d.setdefault(p, []).append(c)
    return d

def render_plantuml_to_image(puml_code: str, img_path: str):
    """调用 PlantUML Server 将 puml 文本直接渲染为 png 图片"""
    try:
        server = PlantUML(url='http://www.plantuml.com/plantuml/img/')
        print(f"⏳ 正在请求渲染图片: {os.path.basename(img_path)} ...")
        
        img_bytes = server.processes(puml_code)
        
        with open(img_path, "wb") as f:
            f.write(img_bytes)
            
        print(f"✅ 图片渲染成功: {img_path}")
    except Exception as e:
        print(f"❌ 图片渲染失败 ({os.path.basename(img_path)}): {e}")


def _render_and_save(target: str, data_context: dict, output_dir: str, file_name_prefix: str):
    """通用的 JSON 保存、模板加载与 PUML/PNG 生成逻辑"""
    os.makedirs(output_dir, exist_ok=True)
    target_upper = target.upper()
    
    # 1. 动态生成 JSON 文件名并保存
    json_path = os.path.join(output_dir, f"{file_name_prefix}_{target}_data.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data_context, f, indent=4, ensure_ascii=False)
    print(f"\n💾 [{target_upper}] 结构化数据基座已保存: {json_path}")

    # 2. 加载对应的 Jinja2 模板
    try:
        env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
        template_file = f"{target}.puml.j2"
        template = env.get_template(template_file)
    except Exception as e:
        print(f"❌ [{target_upper}] 模板加载失败，请检查 {TEMPLATE_DIR}/{template_file} 是否存在。错误信息: {e}")
        return

    # 3. 渲染并生成产物文件
    puml_path = os.path.join(output_dir, f"{file_name_prefix}_{target}.puml")
    img_path = os.path.join(output_dir, f"{file_name_prefix}_{target}.png")
    
    try:
        puml_code = template.render(data_context)
        with open(puml_path, "w", encoding='utf-8') as f:
            f.write(puml_code)
        print(f"📄 [{target_upper}] PUML代码已生成: {puml_path}")
        
        render_plantuml_to_image(puml_code, img_path)
    except Exception as e:
        print(f"⚠️ [{target_upper}] 生成或渲染异常: {e}")

    print(f"🎉 自动化建模流水线 ({target} 环节) 执行完毕！\n")


def generate_usecase_outputs(state: dict, output_dir: str, file_name_prefix: str):
    """专用生成：用例图产物"""
    # 动态构建专属 UML 文件夹路径
    uml_dir = os.path.join(output_dir, f"{file_name_prefix}_UML")
    
    rels = state.get("relationships", {})
    data_context = {
        "actors": state.get("actors", []),
        "usecases": state.get("usecases", []),
        "entities": state.get("entities", {}), 
        "relationships": {
            "inclusion": _to_dict(rels.get("include", [])),
            "extension": _to_dict(rels.get("extend", [])),
            "uc_gen": _to_dict(rels.get("uc_generalization", [])),
            "act_gen": _to_dict(rels.get("actor_generalization", [])),
            "association": state.get("entities", {}) 
        }
    }
    _render_and_save("usecase", data_context, uml_dir, file_name_prefix)

def generate_class_outputs(state: dict, output_dir: str, file_name_prefix: str):
    """专用生成：类图产物"""
    # 动态构建专属 UML 文件夹路径
    uml_dir = os.path.join(output_dir, f"{file_name_prefix}_UML")
    
    data_context = {
        "classes": state.get("classes", []),
        "class_details": state.get("class_details", {}),
        "class_relationships": state.get("class_relationships", {})
    }
    _render_and_save("class", data_context, uml_dir, file_name_prefix)


def generate_sequence_outputs(state: dict, output_dir: str, file_name_prefix: str):
    """专用生成：批量生成多个时序图并打包到文件夹"""
    sequence_data = state.get("sequence_data", {})
    if not sequence_data:
        print("⚠️ 没找到时序图数据。")
        return

    # 将时序图子文件夹放在专属 UML 文件夹内
    uml_dir = os.path.join(output_dir, f"{file_name_prefix}_UML")
    seq_dir = os.path.join(uml_dir, "sequence_diagrams")
    os.makedirs(seq_dir, exist_ok=True)
    
    print(f"\n📂 正在将 {len(sequence_data)} 个时序图打包至: {seq_dir}")
    
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    template = env.get_template("sequence.puml.j2")
    
    for uc_name, data in sequence_data.items():
        # 清理文件名中的非法字符
        safe_name = uc_name.replace("/", "").replace("\\", "")
        
        data_context = {
            "usecase_name": uc_name, # 补充用例名称，以防模板 title 使用
            "participants": data.get("participants", []), 
            "interactions": data.get("interactions", [])
        }
        
        puml_path = os.path.join(seq_dir, f"{safe_name}.puml")
        img_path = os.path.join(seq_dir, f"{safe_name}.png")
        
        try:
            puml_code = template.render(data_context)
            with open(puml_path, "w", encoding='utf-8') as f:
                f.write(puml_code)
            
            render_plantuml_to_image(puml_code, img_path)
        except Exception as e:
            print(f"⚠️ [{uc_name}] 时序图生成失败: {e}")