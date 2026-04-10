"""Graph state schema for LangGraph."""

from pydantic import BaseModel
from typing import Optional


class GraphState(BaseModel):
    """State schema for the LangGraph agent."""

    messages: list = []
    long_term_memory: Optional[str] = None
