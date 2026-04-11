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
    SequenceExtractResponse,
    SequenceOptionsResponse,
    UMLDeleteRequest,
)


router = APIRouter()

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
# 0. 时序图选项（用例列表）
# ================================================================

@router.get("/sequence/options/{project_id}", response_model=SequenceOptionsResponse)
async def get_sequence_options(
    project_id: int,
    db: AsyncSession = Depends(get_session),
):
    """
    返回当前项目可用的时序图选项（已确认用例图的用例名称列表）。
    前端先调用此接口获取可选用例，再传入 selected_usecases 调用 extract。
    """
    project = await database_service.get_project_by_id(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    usecase_model = await database_service.get_latest_model(db, project_id, "usecase")
    if not usecase_model:
        raise HTTPException(
            status_code=400,
            detail="项目下暂无用例图数据，请先前往提取并生成用例图。",
        )
    if not usecase_model.is_confirmed:
        raise HTTPException(
            status_code=400,
            detail="用例图尚未确认，请先在用例图页面确认后，再生成时序图。",
        )
    if not usecase_model.data_json:
        return SequenceOptionsResponse(project_id=project_id, options=[])

    options = usecase_model.data_json.get("usecases", [])
    return SequenceOptionsResponse(project_id=project_id, options=options)


# ================================================================
# 1. 启动 LLM 提取（断点暂停，返回中间态 JSON）
# ================================================================

@router.post("/{model_type}/extract")
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

    project = await database_service.get_project_by_id(db, req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if model_type == "sequence":
        missing = await uml_service.get_missing_dependencies(db, req.project_id)
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"生成时序图前需先完成以下图表：{', '.join(missing)}，请先前往生成。",
            )
        if not req.selected_usecases:
            raise HTTPException(
                status_code=400,
                detail="时序图生成必须传入 selected_usecases 参数，请先调用 /uml/sequence/options/{project_id} 获取可选用例。",
            )

    requirement_text = project.requirement_text

    extracted_data = await uml_service.run_extract(
        model_type=model_type,
        requirement_text=requirement_text,
        thread_id=project.thread_id,
        project_id=project.id,
        db=db,
        selected_usecases=req.selected_usecases,
    )

    # 时序图：渲染 PUML + 图片，再持久化（puml_code / image_url / data_json 三字段全量保存）
    if model_type == "sequence":
        seq_data = extracted_data.get("sequence_data", {})
        diagrams = await uml_service._render_sequence_diagrams(seq_data)
        for d in diagrams:
            uc_name = d["usecase_name"]
            uc_data = {"sequence_data": {uc_name: seq_data.get(uc_name, {})}}
            await database_service.save_sequence_diagram(
                db,
                project_id=project.id,
                usecase_name=uc_name,
                data_json=uc_data,
                puml_code=d["puml_code"],
                image_url=d["image_url"],
            )
        print(f"[extract] sequence: saved {len(diagrams)} diagrams")

        return SequenceExtractResponse(
            project_id=project.id,
            thread_id=project.thread_id,
            diagrams=[
                SequenceDiagramItem(
                    usecase_name=d["usecase_name"],
                    puml_code=d["puml_code"],
                    image_url=d["image_url"],
                )
                for d in diagrams
            ],
        )

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
    """
    model_type = _validate_type(model_type)

    project = await database_service.get_project_by_id(db, req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if model_type == "sequence":
        missing = await uml_service.get_missing_dependencies(db, req.project_id)
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"生成时序图前需先完成以下图表：{', '.join(missing)}，请先前往生成。",
            )

    result = await uml_service.resume_and_generate(
        model_type=model_type,
        thread_id=project.thread_id,
        confirmed_data=req.confirmed_data,
        project_id=project.id,
        db=db,
    )

    # 时序图：每个用例单独存一条记录
    if model_type == "sequence" and "diagrams" in result:
        saved_diagrams = []
        for diag in result["diagrams"]:
            uc_name = diag["usecase_name"]
            uc_data = {"sequence_data": {uc_name: {}}}
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
    """
    req.model_type = _validate_type(req.model_type)

    project = await database_service.get_project_by_id(db, req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    current_model = await database_service.get_latest_model(db, req.project_id, req.model_type)
    current_state = current_model.data_json if current_model else {}

    sync_result = await uml_service.sync_from_puml(
        model_type=req.model_type,
        puml_code=req.puml_code,
        current_state=current_state,
        usecase_name=req.usecase_name,
    )

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


# ================================================================
# 4. UML 图表删除
# ================================================================

@router.delete("/record", status_code=204)
async def delete_uml_record(
    req: UMLDeleteRequest,
    db: AsyncSession = Depends(get_session),
):
    """根据 project_id、model_type 和（可选的）usecase_name 删除特定 UML 记录。

    - usecase / class：删除该类型全部记录。
    - sequence + usecase_name：仅删除该用例的记录。
    - sequence 无 usecase_name：删除该类型全部记录。
    """
    project = await database_service.get_project_by_id(db, req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    success = await database_service.delete_uml_model(
        db,
        project_id=req.project_id,
        model_type=req.model_type,
        usecase_name=req.usecase_name,
    )
    if not success:
        raise HTTPException(status_code=404, detail="UML Record not found")

    return None
