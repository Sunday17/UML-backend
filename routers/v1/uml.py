"""routers/v1/uml.py — 通用 UML 业务路由（支持 usecase / class / sequence）。

路由结构：
  POST /uml/{type}/extract   — 启动 LLM 提取，运行到断点暂停，返回中间态 JSON
  POST /uml/{type}/generate — 接收确认数据，继续图执行，生成 PUML
  POST /uml/sync           — PUML 代码逆向同步

每种图类型的中间态数据结构（extracted_data）：
  usecase  -> {actors, usecases, entities, relationships}
  class    -> {classes, class_details, class_relationships}
  sequence -> {sequence_data}
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from models.database import get_session
from services.database import database_service
from services.uml_service import uml_service
from schemas.uml import (
    ExtractRequest,
    TableDataResponse,
    GenerateRequest,
    UMLFinalResponse,
    SyncRequest,
    SyncResponse,
    SequenceDiagramItem,
)


router = APIRouter()

# 支持的图类型
_VALID_TYPES = {"usecase", "class", "sequence"}


def _validate_type(model_type: str) -> str:
    """校验图类型参数，不合法则抛 400。"""
    if model_type not in _VALID_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid model_type '{model_type}'. Must be one of: {sorted(_VALID_TYPES)}",
        )
    return model_type


# ================================================================
# 1. 启动 LLM 提取（断点暂停，返回中间态 JSON）
# ================================================================

@router.post("/{model_type}/extract", response_model=TableDataResponse)
async def extract_uml(
    model_type: str,
    req: ExtractRequest,
    db: AsyncSession = Depends(get_session),
):
    """
    启动 LangGraph 提取流程，运行到断点暂停，返回中间态 JSON（供前端表格展示）。

    工作流程：
    1. 根据 model_type 初始化 initial_state（触发 route_start 路由）
    2. ainvoke 执行，在 interrupt_before 设定的节点处自动挂起
    3. 返回提取结果，前端可编辑确认
    4. 结果存入数据库（is_confirmed=False）

    注意：需求文本从数据库 project.requirement_text 自动读取，无需前端传入。
    """
    model_type = _validate_type(model_type)

    # 校验项目存在，同时取出需求文本
    project = await database_service.get_project_by_id(db, req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 时序图前置依赖检查：必须已有已确认的 usecase 和 class
    if model_type == "sequence":
        missing = await uml_service.get_missing_dependencies(db, req.project_id)
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"生成时序图前需先完成以下图表：{', '.join(missing)}，请先前往生成。",
            )

    # 需求文本从数据库直接读取，不再依赖前端传入
    requirement_text = project.requirement_text

    # 启动 LangGraph 提取（自动根据 model_type 路由到对应流水线）
    # 时序图会从数据库读取 usecase/class 数据填充状态
    extracted_data = await uml_service.run_extract(
        model_type=model_type,
        requirement_text=requirement_text,
        thread_id=project.thread_id,
        project_id=project.id,
        db=db,
    )

    # 持久化中间态 JSON
    # 时序图：每个用例存一条记录
    if model_type == "sequence":
        seq_data = extracted_data.get("sequence_data", {})
        saved_usecases = []
        for uc_name in seq_data.keys():
            uc_data = {"sequence_data": {uc_name: seq_data[uc_name]}}
            await database_service.save_initial_uml_model(
                db, project_id=project.id, model_type=model_type, data_json=uc_data, usecase_name=uc_name
            )
            saved_usecases.append(uc_name)
        print(f"[extract] sequence: saved {len(saved_usecases)} usecase diagrams")
    else:
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


# ================================================================
# 2. 接收确认数据，继续执行，生成 PUML
# ================================================================

@router.post("/{model_type}/generate", response_model=UMLFinalResponse)
async def generate_uml(
    model_type: str,
    req: GenerateRequest,
    db: AsyncSession = Depends(get_session),
):
    """
    用户在表格中确认/修改数据后，调用此接口：
    1. 将 confirmed_data 写入 LangGraph checkpoint 状态
    2. 传入 None 恢复执行，从断点继续直到图结束
    3. 渲染 PlantUML 代码
    4. 持久化最终产物（is_confirmed=True）

    时序图特殊规则：必须先完成用例图和类图，若未完成则返回 400 并列出缺少的图。
    """
    model_type = _validate_type(model_type)

    project = await database_service.get_project_by_id(db, req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 时序图前置依赖检查：必须已有已确认的 usecase 和 class
    if model_type == "sequence":
        missing = await uml_service.get_missing_dependencies(db, req.project_id)
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"生成时序图前需先完成以下图表：{', '.join(missing)}，请先前往生成。",
            )

    # 恢复 LangGraph 执行，生成 PUML（db/project_id 传入以便时序图回填）
    result = await uml_service.resume_and_generate(
        model_type=model_type,
        thread_id=project.thread_id,
        confirmed_data=req.confirmed_data,
        project_id=project.id,
        db=db,
    )

    # 持久化最终产物
    # 时序图：每个用例单独存一条记录
    if model_type == "sequence" and "diagrams" in result:
        saved_diagrams = []
        for diag in result["diagrams"]:
            uc_name = diag["usecase_name"]
            uc_data = {"sequence_data": {uc_name: diag.get("sequence_data", {})}}
            model = await database_service.save_sequence_diagram(
                db,
                project_id=project.id,
                usecase_name=uc_name,
                data_json=uc_data,
                puml_code=diag["puml_code"],
                image_url=diag["image_url"],
            )
            saved_diagrams.append(model)
        print(f"[generate] sequence: saved {len(saved_diagrams)} diagrams")

        return UMLFinalResponse(
            diagrams=[
                SequenceDiagramItem(
                    usecase_name=d["usecase_name"],
                    puml_code=d["puml_code"],
                    image_url=d["image_url"],
                )
                for d in result["diagrams"]
            ]
        )

    await database_service.update_model_with_puml(
        db,
        project_id=project.id,
        model_type=model_type,
        confirmed_data=req.confirmed_data,
        puml_code=result["puml_code"],
        image_url=result["image_url"],
    )

    return UMLFinalResponse(
        puml_code=result["puml_code"],
        image_url=result["image_url"],
    )


# ================================================================
# 3. PUML 代码逆向同步
# ================================================================

@router.post("/sync", response_model=SyncResponse)
async def sync_puml_code(
    req: SyncRequest,
    db: AsyncSession = Depends(get_session),
):
    """
    用户手动修改 PUML 代码 -> 逆向解析为 JSON -> 重新渲染图片 -> 更新数据库。

    适用于：
    - 用户在编辑器中直接修改 PUML 源码
    - 需要从源码反向更新模型数据
    """
    req.model_type = _validate_type(req.model_type)

    project = await database_service.get_project_by_id(db, req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 1. 获取当前模型状态（用于 PUML 解析时的上下文参考）
    current_model = await database_service.get_latest_model(db, req.project_id, req.model_type)
    current_state = current_model.data_json if current_model else {}

    # 2. 逆向解析 PUML → JSON
    sync_result = await uml_service.sync_from_puml(
        model_type=req.model_type,
        puml_code=req.puml_code,
        current_state=current_state,
        usecase_name=req.usecase_name,
    )

    # 3. 更新数据库
    # 时序图：每个用例单独存一条记录
    if req.model_type == "sequence" and "diagrams" in sync_result:
        for diag in sync_result["diagrams"]:
            uc_name = diag["usecase_name"]
            uc_data = {"sequence_data": {uc_name: sync_result.get("new_json_data", {}).get(uc_name, {})}}
            await database_service.save_sequence_diagram(
                db,
                project_id=project.id,
                usecase_name=uc_name,
                data_json=uc_data,
                puml_code=diag["puml_code"],
                image_url=diag["image_url"],
            )
        return SyncResponse(
            diagrams=[
                SequenceDiagramItem(
                    usecase_name=d["usecase_name"],
                    puml_code=d["puml_code"],
                    image_url=d["image_url"],
                )
                for d in sync_result["diagrams"]
            ]
        )

    await database_service.update_model_with_puml(
        db,
        project_id=project.id,
        model_type=req.model_type,
        confirmed_data=sync_result["new_json_data"],
        puml_code=req.puml_code,
        image_url=sync_result["image_url"],
    )

    return SyncResponse(
        image_url=sync_result["image_url"],
    )
