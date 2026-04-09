"""This file contains the LangGraph Agent/workflow and interactions with the LLM."""

from typing import (
    AsyncGenerator,
    Dict,
    Optional,
)

from langchain_core.messages import (
    BaseMessage,
    ToolMessage,
    convert_to_openai_messages,
)
from langgraph.graph import (
    END,
    StateGraph,
)
from langgraph.graph.state import (
    Command,
    CompiledStateGraph,
)
from langgraph.types import (
    RunnableConfig,
)

from app.core.config import (
    settings,
)
from app.core.langgraph.tools import tools
from app.core.logging import logger
from app.core.prompts import load_system_prompt
from app.schemas import (
    GraphState,
    Message,
)
from app.services.llm import llm_service
from app.utils import (
    dump_messages,
    prepare_messages,
    process_llm_response,
)


class LangGraphAgent:
    """Manages the LangGraph Agent/workflow and interactions with the LLM.

    This class handles the creation and management of the LangGraph workflow,
    including LLM interactions, database connections, and response processing.
    """

    def __init__(self):
        """Initialize the LangGraph Agent with necessary components."""
        # Use the LLM service with tools bound
        self.llm_service = llm_service
        self.llm_service.bind_tools(tools)
        self.tools_by_name = {tool.name: tool for tool in tools}
        self._graph: Optional[CompiledStateGraph] = None
        self._chat_history: Dict[str, list[Message]] = {}
        logger.info(
            "langgraph_agent_initialized",
            model=settings.DEFAULT_LLM_MODEL,
            environment=settings.ENVIRONMENT.value,
        )

    async def _chat(self, state: GraphState, config: RunnableConfig) -> Command:
        """Process the chat state and generate a response.

        Args:
            state (GraphState): The current state of the conversation.

        Returns:
            Command: Command object with updated state and next node to execute.
        """
        # Get the current LLM instance for metrics
        current_llm = self.llm_service.get_llm()
        model_name = (
            current_llm.model_name
            if current_llm and hasattr(current_llm, "model_name")
            else settings.DEFAULT_LLM_MODEL
        )

        SYSTEM_PROMPT = load_system_prompt(long_term_memory=state.long_term_memory)

        # Prepare messages with system prompt
        messages = prepare_messages(state.messages, current_llm, SYSTEM_PROMPT)

        try:
            # Use LLM service with automatic retries and circular fallback
            response_message = await self.llm_service.call(dump_messages(messages))

            # Process response to handle structured content blocks
            response_message = process_llm_response(response_message)

            logger.info(
                "llm_response_generated",
                session_id=config["configurable"]["thread_id"],
                model=model_name,
                environment=settings.ENVIRONMENT.value,
            )

            # Determine next node based on whether there are tool calls
            if response_message.tool_calls:
                goto = "tool_call"
            else:
                goto = END

            return Command(update={"messages": [response_message]}, goto=goto)
        except Exception as e:
            logger.error(
                "llm_call_failed_all_models",
                session_id=config["configurable"]["thread_id"],
                error=str(e),
                environment=settings.ENVIRONMENT.value,
            )
            raise Exception(f"failed to get llm response after trying all models: {str(e)}")

    # Define our tool node
    async def _tool_call(self, state: GraphState) -> Command:
        """Process tool calls from the last message.

        Args:
            state: The current agent state containing messages and tool calls.

        Returns:
            Command: Command object with updated messages and routing back to chat.
        """
        outputs = []
        for tool_call in state.messages[-1].tool_calls:
            tool_result = await self.tools_by_name[tool_call["name"]].ainvoke(tool_call["args"])
            outputs.append(
                ToolMessage(
                    content=tool_result,
                    name=tool_call["name"],
                    tool_call_id=tool_call["id"],
                )
            )
        return Command(update={"messages": outputs}, goto="chat")

    async def create_graph(self) -> Optional[CompiledStateGraph]:
        """Create and configure the LangGraph workflow.

        Returns:
            Optional[CompiledStateGraph]: The configured LangGraph instance or None if init fails
        """
        if self._graph is None:
            try:
                graph_builder = StateGraph(GraphState)
                graph_builder.add_node("chat", self._chat, ends=["tool_call", END])
                graph_builder.add_node("tool_call", self._tool_call, ends=["chat"])
                graph_builder.set_entry_point("chat")
                graph_builder.set_finish_point("chat")

                self._graph = graph_builder.compile(name=f"{settings.PROJECT_NAME} Agent ({settings.ENVIRONMENT.value})")

                logger.info(
                    "graph_created",
                    graph_name=f"{settings.PROJECT_NAME} Agent",
                    environment=settings.ENVIRONMENT.value,
                    has_checkpointer=False,
                )
            except Exception as e:
                logger.error("graph_creation_failed", error=str(e), environment=settings.ENVIRONMENT.value)
                raise e

        return self._graph

    async def get_response(
        self,
        messages: list[Message],
        session_id: str,
        user_id: Optional[str] = None,
    ) -> list[dict]:
        """Get a response from the LLM.

        Args:
            messages (list[Message]): The messages to send to the LLM.
            session_id (str): The session ID for conversation context.
            user_id (Optional[str]): The user ID for conversation context.

        Returns:
            list[dict]: The response from the LLM.
        """
        if self._graph is None:
            self._graph = await self.create_graph()
        config = {
            "configurable": {"thread_id": session_id},
            "metadata": {
                "user_id": user_id,
                "session_id": session_id,
                "environment": settings.ENVIRONMENT.value,
                "debug": settings.DEBUG,
            },
        }
        relevant_memory = "Long-term memory is disabled in MySQL mode."
        try:
            response = await self._graph.ainvoke(
                input={"messages": dump_messages(messages), "long_term_memory": relevant_memory},
                config=config,
            )
            processed_messages = self.__process_messages(response["messages"])
            self._chat_history[session_id] = processed_messages
            return processed_messages
        except Exception as e:
            logger.error("error_getting_response", error=str(e), session_id=session_id, exc_info=True)
            raise

    async def get_stream_response(
        self, messages: list[Message], session_id: str, user_id: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """Get a stream response from the LLM.

        Args:
            messages (list[Message]): The messages to send to the LLM.
            session_id (str): The session ID for the conversation.
            user_id (Optional[str]): The user ID for the conversation.

        Yields:
            str: Tokens of the LLM response.
        """
        config = {
            "configurable": {"thread_id": session_id},
            "metadata": {
                "user_id": user_id,
                "session_id": session_id,
                "environment": settings.ENVIRONMENT.value,
                "debug": settings.DEBUG,
            },
        }
        if self._graph is None:
            self._graph = await self.create_graph()

        relevant_memory = "Long-term memory is disabled in MySQL mode."

        try:
            streamed_parts: list[str] = []
            async for token, _ in self._graph.astream(
                {"messages": dump_messages(messages), "long_term_memory": relevant_memory},
                config,
                stream_mode="messages",
            ):
                try:
                    if token.content:
                        streamed_parts.append(token.content)
                        yield token.content
                except Exception as token_error:
                    logger.error("Error processing token", error=str(token_error), session_id=session_id)
                    # Continue with next token even if current one fails
                    continue

            assistant_text = "".join(streamed_parts)
            rebuilt_history = list(messages)
            rebuilt_history.append(Message(role="assistant", content=assistant_text))
            self._chat_history[session_id] = rebuilt_history
        except Exception as stream_error:
            logger.error("Error in stream processing", error=str(stream_error), session_id=session_id)
            raise stream_error

    async def get_chat_history(self, session_id: str) -> list[Message]:
        """Get the chat history for a given thread ID.

        Args:
            session_id (str): The session ID for the conversation.

        Returns:
            list[Message]: The chat history.
        """
        return self._chat_history.get(session_id, [])

    def __process_messages(self, messages: list[BaseMessage]) -> list[Message]:
        openai_style_messages = convert_to_openai_messages(messages)
        # keep just assistant and user messages
        return [
            Message(role=message["role"], content=str(message["content"]))
            for message in openai_style_messages
            if message["role"] in ["assistant", "user"] and message["content"]
        ]

    async def clear_chat_history(self, session_id: str) -> None:
        """Clear all chat history for a given thread ID.

        Args:
            session_id: The ID of the session to clear history for.

        Raises:
            Exception: If there's an error clearing the chat history.
        """
        self._chat_history.pop(session_id, None)
        logger.info("chat_history_cleared", session_id=session_id)
