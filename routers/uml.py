"""UML generation API routes with Human-in-the-Loop workflow.

路由结构:
- /projects           (GET/POST/DELETE) — 项目管理
- /uml/{type}/extract  (POST)           — 启动 LLM 提取，返回中间态 JSON
- /uml/{type}/generate(POST)           — 接收确认数据，继续图执行，生成 PUML
- /uml/sync           (POST)           — PUML 代码逆向同步
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from models.database import get_session
from services.database import database_service
from services.uml_service import uml_service
from schemas.uml import (
    ProjectCreate,
    ProjectOut,
    ExtractRequest,
    TableDataResponse,
    GenerateRequest,
    UMLFinalResponse,
    SyncRequest,
    SyncResponse,
)


router = APIRouter()

_VALID_TYPES = {"usecase", "class", "sequence"}


def _validate_type(model_type: str) -> str:
    if model_type not in _VALID_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid model_type '{model_type}'. Must be one of: {sorted(_VALID_TYPES)}",
        )
    return model_type


# ================================================================
# 1. 项目管理接口
# ================================================================

@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(db: AsyncSession = Depends(get_session)):
    """获取所有项目列表。"""
    return await database_service.list_projects(db)


@router.post("/projects", response_model=ProjectOut)
async def create_project(req: ProjectCreate, db: AsyncSession = Depends(get_session)):
    """创建新项目，自动生成 UUID 作为 thread_id。"""
    thread_id = str(uuid.uuid4())
    project = await database_service.create_project(
        db,
        name=req.name,
        req_text=req.requirement_text,
        thread_id=thread_id,
    )
    return project


@router.delete("/projects/{project_id}")
async def delete_project(project_id: int, db: AsyncSession = Depends(get_session)):
    """删除项目及其关联的所有 UML 模型（级联删除）。"""
    deleted = await database_service.delete_project(db, project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"message": "Project and associated UML models deleted"}


# ================================================================
# 2. UML 生成业务接口 (usecase / class / sequence)
# ================================================================

@router.post("/uml/{model_type}/extract", response_model=TableDataResponse)
async def extract_uml(
    model_type: str,
    req: ExtractRequest,
    db: AsyncSession = Depends(get_session),
):
    """启动 LLM 提取流程，运行到断点暂停，返回中间态 JSON（供前端表格展示）。

    - 创建项目时自动生成 thread_id（UUID），同一个项目可多次提取不同图类型
    - 提取结果存入 UMLModel（is_confirmed=False）
    """
    model_type = _validate_type(model_type)

    project = await database_service.get_project_by_id(db, req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 使用项目已有的 thread_id，保证同一会话内的状态连贯
    extracted_data = await uml_service.run_extract(
        model_type=model_type,
        requirement_text=req.requirement_text,
        thread_id=project.thread_id,
    )

    # 保存中间态 JSON 到数据库
    await database_service.save_initial_uml_model(
        db,
        project_id=project.id,
        model_type=model_type,
        data_json=extracted_data,
    )

    return TableDataResponse(
        project_id=project.id,
        thread_id=project.thread_id,
        model_type=model_type,
        extracted_data=extracted_data,
    )


@router.post("/uml/{model_type}/generate", response_model=UMLFinalResponse)
async def generate_uml(
    model_type: str,
    req: GenerateRequest,
    db: AsyncSession = Depends(get_session),
):
    """接收用户在表格中修改后的 confirmed_data，更新图状态，继续执行，生成 PUML。

    - 更新 LangGraph checkpoint 状态
    - 继续执行，渲染 PlantUML 代码
    - 将代码和图片 Base64 存入数据库（is_confirmed=True）
    """
    model_type = _validate_type(model_type)

    project = await database_service.get_project_by_id(db, req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 恢复图的执行（update_state + ainvoke(None, config)）
    result = await uml_service.resume_and_generate(
        model_type=model_type,
        thread_id=project.thread_id,
        confirmed_data=req.confirmed_data,
    )

    # 持久化最终产物
    await database_service.update_model_with_puml(
        db,
        project_id=project.id,
        model_type=model_type,
        confirmed_data=req.confirmed_data,
        puml_code=result["puml_code"],
        image_base64=result["image_base64"],
    )

    return UMLFinalResponse(
        puml_code=result["puml_code"],
        image_base64=result["image_base64"],
    )


# ================================================================
# 3. PUML 代码逆向同步
# ================================================================

@router.post("/uml/sync", response_model=SyncResponse)
async def sync_puml_code(
    req: SyncRequest,
    db: AsyncSession = Depends(get_session),
):
    """用户手动修改 PUML 代码 -> 逆向解析为 JSON -> 重新渲染图片 -> 更新数据库。

    适用于：
    - 用户在编辑器中直接修改 PUML 源码
    - 需要从源码反向更新模型数据
    """
    req.model_type = _validate_type(req.model_type)

    project = await database_service.get_project_by_id(db, req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 1. 从数据库获取当前模型状态（用于 PUML 解析时的上下文参考）
    current_model = await database_service.get_latest_model(db, req.project_id, req.model_type)
    current_state = current_model.data_json if current_model else {}

    # 2. 逆向解析 PUML → JSON
    sync_result = await uml_service.sync_from_puml(
        model_type=req.model_type,
        puml_code=req.puml_code,
        current_state=current_state,
    )

    # 3. 更新数据库
    await database_service.update_model_with_puml(
        db,
        project_id=project.id,
        model_type=req.model_type,
        confirmed_data=sync_result["new_json_data"],
        puml_code=req.puml_code,
        image_base64=sync_result["image_base64"],
    )

    return SyncResponse(
        image_base64=sync_result["image_base64"],
        synced_model=sync_result["new_json_data"],
    )
