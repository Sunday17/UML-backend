# app/routers/v1/uml.py
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

# 导入数据库会话依赖
from app.models.database import get_session

# 导入我们定义好的 Schemas (数据校验协议)
from app.schemas.uml import ExtractRequest, UsecaseConfirmRequest, UMLResponse

# 导入具体的业务服务
from app.services.database import database_service
from app.services.uml_service import UMLService

router = APIRouter()

@router.post("/usecase/extract", response_model=UMLResponse)
async def extract_usecase(req: ExtractRequest, db: AsyncSession = Depends(get_session)):
    """
    阶段 1：接收自然语言需求，提取用例和角色，返回给前端等待确认
    """
    # 1. 生成全局唯一的会话 ID (供 LangGraph 记忆使用)
    thread_id = str(uuid.uuid4())
    
    # 2. 数据库操作：创建新项目
    project = await database_service.create_project(
        db, name=req.name, req_text=req.requirement_text, thread_id=thread_id
    )
    
    # 3. 核心业务：调用大模型运行 LangGraph (直到断点处)
    extracted_data = await UMLService.run_extract_usecase(
        requirement_text=req.requirement_text, thread_id=thread_id
    )
    
    # 4. 数据库操作：保存这个未确认的初始模型状态
    await database_service.save_initial_uml_model(
        db, project_id=project.id, model_type="usecase", data_json=extracted_data
    )
    
    return UMLResponse(
        status="success", 
        thread_id=thread_id, 
        data=extracted_data
    )


@router.post("/usecase/generate", response_model=UMLResponse)
async def generate_usecase(req: UsecaseConfirmRequest, db: AsyncSession = Depends(get_session)):
    """
    阶段 2：接收前端修改后的数据，恢复 LangGraph 执行，生成代码和图片
    """
    # 1. 数据库操作：校验项目是否存在
    project = await database_service.get_project_by_thread(db, req.thread_id)
    if not project:
        raise HTTPException(status_code=404, detail="未找到对应的项目，请检查 thread_id")
        
    # 2. 核心业务：将用户的确认数据传回 LangGraph，恢复执行并生成图片
    final_result = await UMLService.resume_generate_usecase(
        thread_id=req.thread_id, actors=req.actors, usecases=req.usecases
    )
    
    # 3. 数据库操作：更新数据库中的 JSON 为确认版，并存入生成的代码和图片
    await database_service.update_model_with_puml(
        db, 
        project_id=project.id, 
        model_type="usecase", 
        confirmed_data={"actors": req.actors, "usecases": req.usecases},
        puml_code=final_result["puml_code"],
        image_base64=final_result["image_base64"]
    )
    
    return UMLResponse(
        status="success", 
        thread_id=req.thread_id, 
        puml_code=final_result["puml_code"],
        image_base64=final_result["image_base64"]
    )