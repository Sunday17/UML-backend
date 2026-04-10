import os
from typing import List, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # 1. 基础应用设置
    APP_ENV: str = "development"
    PROJECT_NAME: str = "UML"
    VERSION: str = "1.0.0"
    DEBUG: bool = True

    # 2. CORS 跨域设置
    # 将字符串 "http://localhost:3000,..." 自动解析为 List
    API_V1_STR: str = ""
    ALLOWED_ORIGINS: Union[str, List[str]] = []

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[str, List[str]]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        return v

    # 3. LLM 设置 (DeepSeek)
    BASE_URL: str
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "deepseek-chat"
    REASONING_MODEL: str = "deepseek-reasoner"

    # 4. MySQL 数据库设置
    MYSQL_HOST: str = "localhost"
    MYSQL_DB: str = "uml_modeling"
    MYSQL_USER: str = "root"
    MYSQL_PORT: int = 3306
    MYSQL_PASSWORD: str
    MYSQL_POOL_SIZE: int = 5
    MYSQL_MAX_OVERFLOW: int = 10

    # 自动生成的异步连接字符串
    @property
    def DATABASE_URL(self) -> str:
        return f"mysql+aiomysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DB}"

    # 配置读取逻辑
    model_config = SettingsConfigDict(
        env_file=".env",              # 指定读取的文件
        env_file_encoding="utf-8",
        case_sensitive=True,          # 区分大小写
        extra="ignore"                # 忽略 .env 中多余的变量
    )

# 全局单例
settings = Settings()