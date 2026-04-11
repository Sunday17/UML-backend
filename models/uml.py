# app/models/uml.py
from typing import Optional, List, Dict, Any
from datetime import datetime

from sqlalchemy import Column, Text
from sqlalchemy.dialects.mysql import JSON
from sqlmodel import SQLModel, Field, Relationship

class Project(SQLModel, table=True):
    __tablename__ = "projects"

    id: Optional[int] = Field(default=None, primary_key=True, description="项目ID")
    name: str = Field(max_length=255, description="项目名称")
    requirement_text: str = Field(description="用户输入的原始需求文本")
    thread_id: str = Field(index=True, unique=True, max_length=100, description="LangGraph的会话ID")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # 若数据库表由旧版迁移而来且含 NOT NULL 的 user_id，需与表结构一致；无用户体系时可填 0 或后续改表为可空
    user_id: Optional[int] = Field(default=0, description="关联用户（无登录时可填 0）")

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
    usecase_name: Optional[str] = Field(
        default=None,
        max_length=255,
        index=True,
        description="时序图专用：关联的用例名称，usecase/class 图为 NULL",
    )
    
    # 使用 SQLAlchemy 的 JSON 列，完美适配 MySQL 5.7+
    data_json: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    puml_code: Optional[str] = Field(default=None, description="PlantUML 源码")
    # 与库表 image_url 一致：可存外链，也可存 data URL（列类型建议 TEXT/LONGTEXT）
    image_url: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
        description="预览图 URL 或 data URL",
    )
    is_confirmed: bool = Field(default=False, description="用户是否已确认")

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="最后更新时间")

    project: Project = Relationship(back_populates="models")