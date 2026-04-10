"""routers/v1/projects.py — 项目管理 CRUD 接口。"""

import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from models.database import get_session
from services.database import database_service
from schemas.uml import ProjectCreate, ProjectOut


router = APIRouter()


@router.get("", response_model=list[ProjectOut])
async def list_projects(db: AsyncSession = Depends(get_session)):
    """获取所有项目列表（按创建时间倒序）。"""
    return await database_service.list_projects(db)


@router.post("", response_model=ProjectOut)
async def create_project(req: ProjectCreate, db: AsyncSession = Depends(get_session)):
    """创建新项目，自动生成 UUID 作为 thread_id（LangGraph 会话 ID）。"""
    thread_id = str(uuid.uuid4())
    project = await database_service.create_project(
        db,
        name=req.name,
        req_text=req.requirement_text,
        thread_id=thread_id,
    )
    return project


@router.delete("/{project_id}")
async def delete_project(project_id: int, db: AsyncSession = Depends(get_session)):
    """删除项目及其关联的所有 UML 模型（级联删除）。"""
    deleted = await database_service.delete_project(db, project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"message": "Project and associated UML models deleted"}
