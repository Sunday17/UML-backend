"""Database service for CRUD operations on Project and UMLModel tables."""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from sqlalchemy import text, select
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.database import engine
from models.uml import Project, UMLModel

logger = logging.getLogger(__name__)


class DatabaseService:
    """Async CRUD service for projects and UML models."""

    # ------------------------------------------------------------------
    # 1. 系统基础
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        """检查数据库连通性（main.py 启动时会调用）。"""
        try:
            async with engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"数据库连通性检查失败: {e}")
            return False

    # ------------------------------------------------------------------
    # 2. 项目 (Project) CRUD
    # ------------------------------------------------------------------

    async def create_project(
        self, db: AsyncSession, name: str, req_text: str, thread_id: str
    ) -> Project:
        """创建一个新的建模项目。"""
        project = Project(name=name, requirement_text=req_text, thread_id=thread_id)
        db.add(project)
        await db.commit()
        await db.refresh(project)
        return project

    async def list_projects(self, db: AsyncSession) -> List[Project]:
        """返回所有项目，按创建时间倒序。"""
        statement = select(Project).order_by(Project.created_at.desc())
        result = await db.exec(statement)
        return list(result.all())

    async def get_project_by_id(
        self, db: AsyncSession, project_id: int
    ) -> Optional[Project]:
        """通过 project_id 查找项目。"""
        statement = select(Project).where(Project.id == project_id)
        result = await db.exec(statement)
        return result.first()

    async def get_project_by_thread(
        self, db: AsyncSession, thread_id: str
    ) -> Optional[Project]:
        """通过 thread_id 查找项目。"""
        statement = select(Project).where(Project.thread_id == thread_id)
        result = await db.exec(statement)
        return result.first()

    async def delete_project(self, db: AsyncSession, project_id: int) -> bool:
        """删除项目（级联删除关联的 UMLModel）。返回是否成功删除了记录。"""
        project = await self.get_project_by_id(db, project_id)
        if not project:
            return False
        await db.delete(project)
        await db.commit()
        return True

    # ------------------------------------------------------------------
    # 3. UML 模型 (UMLModel) CRUD
    # ------------------------------------------------------------------

    async def save_initial_uml_model(
        self,
        db: AsyncSession,
        project_id: int,
        model_type: str,
        data_json: Dict[str, Any],
    ) -> UMLModel:
        """保存 LLM 提取的中间态 JSON（is_confirmed=False）。"""
        uml_model = UMLModel(
            project_id=project_id,
            model_type=model_type,
            data_json=data_json,
            is_confirmed=False,
        )
        db.add(uml_model)
        await db.commit()
        await db.refresh(uml_model)
        return uml_model

    async def update_model_with_puml(
        self,
        db: AsyncSession,
        project_id: int,
        model_type: str,
        confirmed_data: Dict[str, Any],
        puml_code: str,
        image_base64: str,
    ) -> Optional[UMLModel]:
        """更新 JSON 数据，保存最终 PUML 代码和图片（is_confirmed=True）。"""
        statement = select(UMLModel).where(
            UMLModel.project_id == project_id, UMLModel.model_type == model_type
        )
        result = await db.exec(statement)
        model = result.first()

        if model:
            model.data_json = confirmed_data
            model.puml_code = puml_code
            model.image_base64 = image_base64
            model.is_confirmed = True
            model.updated_at = datetime.utcnow()
            db.add(model)
            await db.commit()
            await db.refresh(model)
        return model

    async def get_latest_model(
        self, db: AsyncSession, project_id: int, model_type: str
    ) -> Optional[UMLModel]:
        """获取指定项目和类型的最新模型记录。"""
        statement = (
            select(UMLModel)
            .where(
                UMLModel.project_id == project_id, UMLModel.model_type == model_type
            )
            .order_by(UMLModel.created_at.desc())
        )
        result = await db.exec(statement)
        return result.first()

    async def list_models_by_project(
        self, db: AsyncSession, project_id: int
    ) -> List[UMLModel]:
        """列出某项目下的所有 UML 模型。"""
        statement = (
            select(UMLModel)
            .where(UMLModel.project_id == project_id)
            .order_by(UMLModel.created_at.desc())
        )
        result = await db.exec(statement)
        return list(result.all())


# 模块级单例，供其他模块直接引入
database_service = DatabaseService()
