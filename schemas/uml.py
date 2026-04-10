"""UML-related Pydantic schemas."""

from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional


# ================================================================
# 1. 项目管理
# ================================================================

class ProjectCreate(BaseModel):
    name: str = Field(..., example="图书管理系统")
    requirement_text: str = Field(..., example="用户可以注册、登录、查询图书")


class ProjectOut(BaseModel):
    id: int
    name: str
    requirement_text: str
    thread_id: str
    created_at: Any

    model_config = {"from_attributes": True}


# ================================================================
# 2. 提取接口 (针对不同图类型)
# ================================================================

class ExtractRequest(BaseModel):
    project_id: int
    requirement_text: str = Field(
        ...,
        example="用户登录系统后，可以查询图书并下单",
        description="支持在提取时动态更新需求文本",
    )


# ================================================================
# 3. 提取结果响应 (表格数据)
# ================================================================

class TableDataResponse(BaseModel):
    project_id: int
    thread_id: str
    model_type: str
    extracted_data: Dict[str, Any] = Field(
        ...,
        description=(
            "usecase: {actors:[], usecases:[], entities:{}}  "
            "class:  {classes:[], class_details:{}, class_relationships:{}}  "
            "sequence:{sequence_data:{}}"
        ),
    )


# ================================================================
# 4. 确认并生成请求
# ================================================================

class GenerateRequest(BaseModel):
    project_id: int
    confirmed_data: Dict[str, Any] = Field(
        ...,
        description="用户在表格中修改后的确认数据，格式同 extracted_data",
    )


# ================================================================
# 5. 最终产物响应
# ================================================================

class UMLFinalResponse(BaseModel):
    puml_code: str = Field(..., description="生成的 PlantUML 源码")
    image_base64: str = Field(
        ...,
        description="渲染后的图片，格式: data:image/png;base64,...",
    )


# ================================================================
# 6. PUML 逆向同步
# ================================================================

class SyncRequest(BaseModel):
    project_id: int
    model_type: str = Field(..., example="usecase")
    puml_code: str = Field(..., example="@startuml\n:Actor: -> (UseCase)\n@enduml")


class SyncResponse(BaseModel):
    image_base64: str = Field(..., description="重新渲染后的图片 Base64")
    synced_model: Dict[str, Any] = Field(..., description="从 PUML 逆向解析出的 JSON 数据")
