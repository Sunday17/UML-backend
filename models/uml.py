# app/models/uml.py
from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field, Relationship, Column, JSON
from datetime import datetime

class Project(SQLModel, table=True):
    __tablename__ = "projects"
    
    id: Optional[int] = Field(default=None, primary_key=True, description="项目ID")
    name: str = Field(max_length=255, description="项目名称")
    requirement_text: str = Field(description="用户输入的原始需求文本")
    thread_id: str = Field(index=True, unique=True, max_length=100, description="LangGraph的会话ID")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # 建立与 UMLModel 的一对多关联
    models: List["UMLModel"] = Relationship(
        back_populates="project",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"} # 级联删除
    )

class UMLModel(SQLModel, table=True):
    __tablename__ = "uml_models"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="projects.id", index=True)
    model_type: str = Field(max_length=50, description="用例图(usecase)/类图(class)/时序图(sequence)")
    
    # 使用 SQLAlchemy 的 JSON 列，完美适配 MySQL 5.7+
    data_json: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    puml_code: Optional[str] = Field(default=None, description="PlantUML 源码")
    image_base64: Optional[str] = Field(default=None, description="Base64图片数据")
    is_confirmed: bool = Field(default=False, description="用户是否已确认")
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    project: Project = Relationship(back_populates="models")