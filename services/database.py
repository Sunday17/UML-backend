"""Database service for CRUD operations on Project and UMLModel tables."""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from sqlalchemy import delete, text, select
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.database import engine
from models.uml import Project, UMLModel

logger = logging.getLogger(__name__)

# 旧库若先于 ORM 建表，可能缺少下列列；启动时按名补齐（与当前 uml_models 设计一致）。
_UML_MODELS_MISSING_COLUMN_DDL: list[tuple[str, str]] = [
    ("puml_code", "ALTER TABLE uml_models ADD COLUMN puml_code TEXT NULL"),
    ("image_url", "ALTER TABLE uml_models ADD COLUMN image_url LONGTEXT NULL"),
    ("is_confirmed", "ALTER TABLE uml_models ADD COLUMN is_confirmed TINYINT(1) NOT NULL DEFAULT 0"),
    ("updated_at", "ALTER TABLE uml_models ADD COLUMN updated_at DATETIME NULL"),
    ("usecase_name", "ALTER TABLE uml_models ADD COLUMN usecase_name VARCHAR(255) NULL"),
]


async def ensure_uml_models_schema(conn) -> None:
    """若 `uml_models` 表存在但列落后于 `UMLModel`，则执行 ADD COLUMN（幂等）。"""
    try:
        chk = await conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'uml_models'"
            )
        )
        if chk.scalar_one() == 0:
            return
    except Exception as e:
        logger.warning("skip uml_models schema patch: %s", e)
        return

    for col_name, ddl in _UML_MODELS_MISSING_COLUMN_DDL:
        try:
            r = await conn.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'uml_models' "
                    "AND COLUMN_NAME = :name"
                ),
                {"name": col_name},
            )
            if r.scalar_one() > 0:
                continue
            await conn.execute(text(ddl))
            logger.info("uml_models: added missing column %s", col_name)
        except Exception as e:
            logger.warning("uml_models: could not add column %s: %s", col_name, e)


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
        """删除项目（先删子表，再删项目）。

        不使用 ``session.delete(project)``：ORM 级联会懒加载 ``UMLModel``，若库表列少于模型定义会 SELECT 失败。
        全程用 ``delete()`` 语句，只发 DELETE，不加载子行。
        """
        project = await self.get_project_by_id(db, project_id)
        if not project:
            return False
        await db.execute(delete(UMLModel).where(UMLModel.project_id == project_id))
        await db.execute(delete(Project).where(Project.id == project_id))
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
        usecase_name: str = None,
    ) -> UMLModel:
        """保存 LLM 提取的中间态 JSON（is_confirmed=False）。

        所有图类型统一按 project_id + model_type 去重：
        - usecase / class：同一项目同类型只存一条，重复生成直接覆盖
        - sequence：按 project_id + model_type + usecase_name 去重
        """
        # 1. 先查是否已有记录
        existing = None
        if model_type == "sequence" and usecase_name:
            existing = await self.get_sequence_model(db, project_id, usecase_name)
        else:
            existing = await self.get_latest_model(db, project_id, model_type)

        # 2. 存在则覆盖
        if existing:
            existing.data_json = data_json
            existing.is_confirmed = False
            db.add(existing)
            await db.commit()
            await db.refresh(existing)
            return existing

        # 3. 不存在则新增
        uml_model = UMLModel(
            project_id=project_id,
            model_type=model_type,
            data_json=data_json,
            is_confirmed=False,
            usecase_name=usecase_name,
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
        puml_code: str = None,
        image_url: str = None,
        usecase_name: str = None,
    ) -> Optional[UMLModel]:
        """更新 JSON 数据，保存最终 PUML 代码和图片（is_confirmed=True）。

        所有图类型统一按 project_id + model_type 去重后更新；未找到时新建记录。
        时序图可按 usecase_name 区分，同一项目同一用例只存一条。
        """
        # 1. 查询已有记录
        statement = select(UMLModel).where(
            UMLModel.project_id == project_id,
            UMLModel.model_type == model_type,
        )
        if model_type == "sequence" and usecase_name:
            statement = statement.where(UMLModel.usecase_name == usecase_name)
        else:
            statement = statement.where(UMLModel.usecase_name.is_(None))

        result = await db.exec(statement)
        model = result.first()

        # 2. 存在则更新
        if model:
            model.data_json = confirmed_data
            model.puml_code = puml_code
            model.image_url = image_url
            model.is_confirmed = True
            model.usecase_name = usecase_name
            model.updated_at = datetime.utcnow()
            db.add(model)
            await db.commit()
            await db.refresh(model)
            return model

        # 3. 不存在则新建
        uml_model = UMLModel(
            project_id=project_id,
            model_type=model_type,
            data_json=confirmed_data,
            puml_code=puml_code,
            image_url=image_url,
            is_confirmed=True,
            usecase_name=usecase_name,
        )
        db.add(uml_model)
        await db.commit()
        await db.refresh(uml_model)
        return uml_model

    async def save_sequence_diagram(
        self,
        db: AsyncSession,
        project_id: int,
        usecase_name: str,
        data_json: Dict[str, Any],
        puml_code: str,
        image_url: str,
    ) -> UMLModel:
        """时序图专用：为每个用例保存或更新一条记录。"""
        existing = await self.get_sequence_model(db, project_id, usecase_name)
        if existing:
            existing.data_json = data_json
            existing.puml_code = puml_code
            existing.image_url = image_url
            existing.is_confirmed = True
            existing.updated_at = datetime.utcnow()
            db.add(existing)
            await db.commit()
            await db.refresh(existing)
            return existing

        uml_model = UMLModel(
            project_id=project_id,
            model_type="sequence",
            usecase_name=usecase_name,
            data_json=data_json,
            puml_code=puml_code,
            image_url=image_url,
            is_confirmed=True,
        )
        db.add(uml_model)
        await db.commit()
        await db.refresh(uml_model)
        return uml_model

    async def get_sequence_model(
        self, db: AsyncSession, project_id: int, usecase_name: str
    ) -> Optional[UMLModel]:
        """时序图专用：按项目+用例名查询。"""
        statement = (
            select(UMLModel)
            .where(
                UMLModel.project_id == project_id,
                UMLModel.model_type == "sequence",
                UMLModel.usecase_name == usecase_name,
            )
            .order_by(UMLModel.created_at.desc())
        )
        result = await db.exec(statement)
        return result.first()

    async def list_sequence_models(
        self, db: AsyncSession, project_id: int
    ) -> List[UMLModel]:
        """时序图专用：列出某项目下所有用例的时序图。"""
        statement = (
            select(UMLModel)
            .where(
                UMLModel.project_id == project_id,
                UMLModel.model_type == "sequence",
            )
            .order_by(UMLModel.created_at.desc())
        )
        result = await db.exec(statement)
        return list(result.all())

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

    async def get_latest_confirmed_model(
        self, db: AsyncSession, project_id: int, model_type: str
    ) -> Optional[UMLModel]:
        """获取指定项目和类型的最新已确认（is_confirmed=True）的模型记录。"""
        statement = (
            select(UMLModel)
            .where(
                UMLModel.project_id == project_id,
                UMLModel.model_type == model_type,
                UMLModel.is_confirmed == True,
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
