"""LangGraph tools for enhanced language model capabilities.

This package contains custom tools that can be used with LangGraph.
DuckDuckGo search is optional (requires langchain-community).
"""

from langchain_core.tools.base import BaseTool

tools: list[BaseTool] = []

try:
    from .duckduckgo_search import duckduckgo_search_tool
    tools.append(duckduckgo_search_tool)
except ImportError:
    pass
