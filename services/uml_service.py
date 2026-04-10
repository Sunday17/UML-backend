# app/services/uml_service.py
from typing import Dict, Any
from app.core.langgraph.graph import app_graph # 这里导入你编译好的 LangGraph 大图
from app.utils.puml_renderer import render_puml_to_base64 # 见下文 Utils 部分

class UMLService:
    
    @staticmethod
    async def run_extract_usecase(requirement_text: str, thread_id: str) -> Dict[str, Any]:
        """
        阶段 1：接收文本，启动 LangGraph 直到 extract_usecases 节点暂停
        """
        config = {"configurable": {"thread_id": thread_id}}
        initial_state = {"text": requirement_text} 
        
        # ainvoke 会执行图，并在 interrupt_after 设定的节点处自动挂起
        result = await app_graph.ainvoke(initial_state, config)
        
        # 返回提取出来的数据供前端确认
        return {
            "actors": result.get("actors", []),
            "usecases": result.get("usecases", [])
        }

    @staticmethod
    async def resume_generate_usecase(thread_id: str, actors: list, usecases: list) -> Dict[str, Any]:
        """
        阶段 2：接收前端确认后的数据，强制更新 State，唤醒图继续执行
        """
        config = {"configurable": {"thread_id": thread_id}}
        
        # 1. 将用户的修改强行写入当前图的上下文中
        app_graph.update_state(
            config,
            {"actors": actors, "usecases": usecases}
        )
        
        # 2. 传入 None 恢复执行，图会继续跑关系抽取、生成代码等节点
        result = await app_graph.ainvoke(None, config)
        
        puml_code = result.get("puml_code", "")
        
        # 3. 将生成的代码渲染为图片
        image_base64 = await render_puml_to_base64(puml_code)
        
        return {
            "puml_code": puml_code,
            "image_base64": image_base64
        }