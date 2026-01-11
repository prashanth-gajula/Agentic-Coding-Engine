from typing import Annotated, List, Optional, Literal
from typing_extensions import TypedDict

from langgraph.graph import add_messages
from langchain_core.messages import AnyMessage

# High-level type of task the system is currently handling
TaskType = Literal["navigate", "edit", "debug", "test", "document", "other"]


class AgentState(TypedDict):
    """
    Common shared state for the entire agentic IDE graph.
    All nodes (orchestrator, context agent, code edit agent, debug agent, etc.)
    read from and write to this state.
    """

    # Conversation + tool history.
    # LangGraph will automatically append new messages to this list.
    messages: Annotated[List[AnyMessage], add_messages]

    # Original user request for this turn / workflow.
    user_request: str

    # What kind of task this is (classified by the orchestrator).
    task_type: TaskType

    # Files currently in focus (paths like "app/main.py", "src/utils/db.py").
    target_files: List[str]

    # Optional finer-grained focus (function name, symbol, or line range).
    focus_symbol: Optional[str]

    # Debugging-related info (used when task_type == "debug").
    error_message: Optional[str]
    stack_trace: Optional[str]

    # Testing-related info (used when tests are run).
    test_command: Optional[str]
    last_test_output: Optional[str]

    # Latest code change proposal (for example, a unified diff or patch summary).
    last_diff: Optional[str]

    # Name of the worker agent currently being invoked
    # (e.g. "orchestrator", "context_agent", "code_edit_agent", "debug_agent").
    active_agent: Optional[str]

    # Set to True when the workflow for this user request is complete.
    done: bool

    # Planning and execution tracking
    plan: list
    current_step: int
    current_task: str
    next_node: str
    final_summary: str
    generated_files: list
    last_code_agent_output: str
    target_file: Optional[str]  # ADD THIS - for target file per step
    
    # Step completion tracking - ADD THESE
    worker_completed: bool  # Flag set by workers when they finish
    expected_file_count: int  # Number of files expected before current step
    
    needs_review: bool  # Context agent sets this to trigger review
    user_feedback: Optional[str]  # Stores user's revision feedback
    
    #memory 
    conversation_history: list
    recent_files: list
    current_working_file: Optional[str]
    reference_context: dict