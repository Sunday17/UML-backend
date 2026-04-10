# app/schemas/uml.py
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

# --- 请求体 (Requests) ---

class ExtractRequest(BaseModel):
    """前端发起新建项目并提取用例的请求"""
    name: str = Field(..., example="图书管理系统")
    requirement_text: str = Field(..., example="系统需要包含图书借阅、归还、用户管理等功能...")

class UsecaseConfirmRequest(BaseModel):
    """前端用户修改JSON后，点击确认生成的请求"""
    thread_id: str = Field(..., description="必须携带之前返回的会话ID")
    actors: List[Dict[str, Any]] = Field(..., description="用户确认后的角色列表")
    usecases: List[Dict[str, Any]] = Field(..., description="用户确认后的用例列表")

class RenderRequest(BaseModel):
    """前端用户手动修改 PUML 代码后请求重新渲染"""
    puml_code: str = Field(..., description="修改后的 PlantUML 源码")

# --- 响应体 (Responses) ---

class UMLResponse(BaseModel):
    """统一的 UML 接口返回格式"""
    status: str = Field(default="success")
    thread_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = Field(default=None, description="提取出的结构化JSON")
    puml_code: Optional[str] = Field(default=None, description="生成的PlantUML代码")
    image_base64: Optional[str] = Field(default=None, description="渲染好的图片(Base64)")
    message: Optional[str] = None