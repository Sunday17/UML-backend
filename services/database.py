# app/services/database.py
import logging
from typing import Optional, Dict, Any, List
from sqlalchemy import text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.database import engine
from app.models.uml import Project, UMLModel

logger = logging.getLogger(__name__)

class DatabaseService:
    # --- 1. 系统基础方法 ---
    async def health_check(self) -> bool:
        """检查数据库连通性 (main.py 中启动时会调用)"""
        try:
            async with engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"数据库连通性检查失败: {e}")
            return False

    # --- 2. 项目 (Project) 相关业务 ---
    async def create_project(self, db: AsyncSession, name: str, req_text: str, thread_id: str) -> Project:
        """创建一个新的建模项目"""
        project = Project(name=name, requirement_text=req_text, thread_id=thread_id)
        db.add(project)
        await db.commit()
        await db.refresh(project)
        return project

    async def get_project_by_thread(self, db: AsyncSession, thread_id: str) -> Optional[Project]:
        """通过 thread_id 查找项目上下文"""
        statement = select(Project).where(Project.thread_id == thread_id)
        result = await db.exec(statement)
        return result.first()

    # --- 3. UML 模型 (UMLModel) 相关业务 ---
    async def save_initial_uml_model(self, db: AsyncSession, project_id: int, model_type: str, data_json: Dict[str, Any]) -> UMLModel:
        """保存大模型提取的初始状态 (JSON格式，尚未确认生成图)"""
        uml_model = UMLModel(project_id=project_id, model_type=model_type, data_json=data_json)
        db.add(uml_model)
        await db.commit()
        await db.refresh(uml_model)
        return uml_model

    async def update_model_with_puml(self, db: AsyncSession, project_id: int, model_type: str, confirmed_data: Dict[str, Any], puml_code: str, image_base64: str) -> Optional[UMLModel]:
        """用户确认后，更新 JSON，并保存最终生成的代码和图片"""
        statement = select(UMLModel).where(UMLModel.project_id == project_id, UMLModel.model_type == model_type)
        result = await db.exec(statement)
        model = result.first()
        
        if model:
            model.data_json = confirmed_data
            model.puml_code = puml_code
            model.image_base64 = image_base64
            model.is_confirmed = True
            db.add(model)
            await db.commit()
            await db.refresh(model)
        return model

# 实例化一个单例对象，供其他模块引入
database_service = DatabaseService()