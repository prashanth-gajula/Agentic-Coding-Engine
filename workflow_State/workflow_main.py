# workflow_main.py (Updated with checkpointing support)
from langchain_core.tracers.langchain import LangChainTracer
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage
#from langgraph.checkpoint.memory import MemorySaver  # ← Add this import
from langgraph.checkpoint.postgres import PostgresSaver
import os

from workflow_State.main_state import AgentState

# Import all your agents
from orchestrator.main import orchestrator
from Context_Agent.context_agent_main import context_agent
from Code_Agent.code_agent_main import CodeAgent
from Debug_Agent.debug_agent_main import DebugAgent
from Reviewer_Agent.reviewer_agent_main import ReviewerAgent


def context_router(state: AgentState) -> str:
    """
    Context Agent is the controller:
    - decides next worker to run (code/debug/document)
    - OR triggers reviewer_agent after worker completion
    - OR decides workflow is complete -> orchestrator
    """
    if state.get("done"):
        return "orchestrator"

    next_node = (state.get("next_node") or "").strip().lower()

    valid = {"code_agent", "debug_agent", "reviewer_agent", "orchestrator"}
    if next_node not in valid:
        return "code_agent"

    return next_node


def orchestrator_router(state: AgentState) -> str:
    """
    Orchestrator routes to:
    - context_agent (on first entry or if not done)
    - END (when workflow is complete)
    """
    if state.get("done"):
        return "end"
    return "context_agent"


def create_workflow():
    """Create the workflow graph with checkpointing support"""
    graph = StateGraph(AgentState)

    # Add all nodes
    graph.add_node("orchestrator", orchestrator)
    graph.add_node("context_agent", context_agent)
    graph.add_node("code_agent", CodeAgent)
    graph.add_node("debug_agent", DebugAgent)
    graph.add_node("reviewer_agent", ReviewerAgent)

    # Entry point: start at orchestrator
    graph.set_entry_point("orchestrator")

    # Orchestrator routing
    graph.add_conditional_edges(
        "orchestrator",
        orchestrator_router,
        {
            "context_agent": "context_agent",
            "end": END
        },
    )

    # Context agent routing: can dispatch to workers, reviewer, or orchestrator
    graph.add_conditional_edges(
        "context_agent",
        context_router,
        {
            "code_agent": "code_agent",
            "debug_agent": "debug_agent",
            "reviewer_agent": "reviewer_agent",
            "orchestrator": "orchestrator",
        },
    )

    # All workers return to context_agent
    graph.add_edge("code_agent", "context_agent")
    graph.add_edge("debug_agent", "context_agent")
    
    # Reviewer also returns to context_agent
    graph.add_edge("reviewer_agent", "context_agent")

    # ✅ Compile WITH checkpointer for pause/resume support
    #checkpointer = MemorySaver()
    #return graph.compile(checkpointer=checkpointer)
    checkpointer = get_checkpointer()
    return graph.compile(checkpointer=checkpointer)

def get_checkpointer():
    """
    Get the appropriate checkpointer based on environment.
    Uses PostgreSQL in production, in-memory for local testing without DB.
    """
    database_url = os.getenv("DATABASE_URL")
    
    if database_url:
        # Production: Use PostgreSQL
        print("🗄️  Using PostgreSQL checkpointer")
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
            import psycopg
            
            # Create a connection with autocommit enabled
            print("📡 Connecting to PostgreSQL...")
            conn = psycopg.connect(database_url, autocommit=True)  # ✅ Add autocommit=True
            print("✅ Connected to PostgreSQL (autocommit enabled)")
            
            # Create the checkpointer with the connection
            print("🔧 Creating PostgresSaver...")
            checkpointer = PostgresSaver(conn)
            
            # Setup tables
            print("📋 Setting up checkpoint tables...")
            checkpointer.setup()
            print("✅ Checkpoint tables ready")
            
            print("✅ PostgreSQL checkpointer initialized successfully")
            return checkpointer
            
        except Exception as e:
            print(f"❌ Failed to connect to PostgreSQL: {e}")
            print(f"⚠️  Error type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            print("⚠️  Falling back to in-memory checkpointer")
            from langgraph.checkpoint.memory import MemorySaver
            return MemorySaver()
    else:
        # Local testing: Use in-memory checkpointer
        print("⚠️  DATABASE_URL not found - using in-memory checkpointer")
        print("⚠️  Checkpoints will not persist across restarts")
        from langgraph.checkpoint.memory import MemorySaver
        return MemorySaver()

def create_initial_state(user_request: str, skip_review: bool = False) -> AgentState:
    """
    Helper function to create initial state for a workflow.
    
    Called by API server with user's request from VS Code.
    
    Args:
        user_request: The task description from the user
        skip_review: If True, skip review step (for local testing)
        
    Returns:
        Initial state dictionary for the workflow
    """
    return {
        "messages": [HumanMessage(content=user_request)],
        "user_request": user_request,
        "task_type": "other",
        "target_files": [],
        "focus_symbol": None,
        "error_message": None,
        "stack_trace": None,
        "test_command": None,
        "last_test_output": None,
        "last_diff": None,
        "active_agent": "orchestrator",
        "done": False,
        "plan": [],
        "current_step": 0,
        "current_task": "",
        "next_node": "context_agent",
        "final_summary": "",
        "generated_files": [],
        "last_code_agent_output": "",
        "target_file": None,
        "worker_completed": False,
        "expected_file_count": 0,
        "needs_review": False,
        "user_feedback": None,
        "file_contents": {},
        "project_path": None,
        "conversation_history": [],
        "recent_files": [],
        "current_working_file": None,
        "reference_context": {},
        "skip_review": skip_review  # ✅ Add skip_review flag
    }


# ============================================
# LangSmith Tracing Helper Functions
# ============================================

def get_langsmith_config():
    """Get LangSmith configuration from environment"""
    return {
        "project_name": os.getenv("LANGCHAIN_PROJECT", "agentic-ide-workflow"),
        "tags": ["agentic-workflow", "vs-code-extension"],
    }


def run_workflow_with_tracing(app, initial_state, config=None):
    """
    Execute workflow with LangSmith tracing using callbacks.
    Supports checkpointing for pause/resume.
    
    Args:
        app: Compiled workflow graph (with checkpointer)
        initial_state: Initial state dictionary OR None to resume from checkpoint
        config: Must include thread_id for checkpointing (e.g., {"configurable": {"thread_id": "session_123"}})
    
    Yields:
        State updates from workflow execution
    """
    langsmith_config = get_langsmith_config()
    
    tracing_enabled = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    
    if tracing_enabled:
        print("🔍 LangSmith tracing enabled")
        print(f"📊 Project: {langsmith_config['project_name']}")
    else:
        print("⚠️  LangSmith tracing disabled")
    
    run_config = config or {}
    
    tracer = None
    if tracing_enabled:
        tracer = LangChainTracer(project_name=langsmith_config["project_name"])
        run_config["callbacks"] = [tracer]
    
    # Add tags
    if "tags" not in run_config:
        run_config["tags"] = []
    run_config["tags"].extend(langsmith_config["tags"])
    
    # Add run name if not resuming (initial_state is not None)
    if initial_state is not None:
        run_config["run_name"] = f"workflow_{initial_state.get('user_request', '')[:50]}"
    
    try:
        # Stream with checkpointing support
        for state in app.stream(initial_state, config=run_config, stream_mode="values"):
            yield state
    except RecursionError as e:
        print(f"❌ Recursion limit exceeded - workflow stuck in loop")
        raise Exception("Workflow exceeded maximum steps. This usually indicates an infinite loop. Please simplify your request.")
    finally:
        # Ensure tracer is properly closed
        if tracer is not None:
            try:
                tracer.wait_for_futures()
            except Exception as e:
                print(f"Note: Tracer cleanup issue (non-critical): {e}")


"""
---->This is for local testing<-----
the input for the workflow is handled by the fast API this is just to test the agentic workflow.

if __name__ == "__main__":
    # Load environment variables for local testing
    from dotenv import load_dotenv
    load_dotenv()
    
    app = create_workflow()

    initial_user_request = "can you create me a python code to connect to pinecone vector database and a langchain agent that uses this vector database as one of the tool i need these two in different files and the titles of these files need to be based on their functionality."
    
    # ✅ For local testing, skip review to avoid blocking
    initial_state = create_initial_state(initial_user_request, skip_review=True)

    print("=== Starting workflow with LangSmith tracing ===")
    print("Initial user request:", initial_user_request)
    print("⚠️  Review step will be SKIPPED (local testing mode)")
    print("------------------------")

    final_state = None
    
    # ✅ Thread ID for checkpointing (required)
    config = {
        "configurable": {"thread_id": "local_test_session"},
        "recursion_limit": 50
    }

    # Stream the graph execution step by step WITH TRACING
    for step_idx, state in enumerate(
        run_workflow_with_tracing(
            app, 
            initial_state, 
            config=config  # ✅ Pass config with thread_id
        )
    ):
        print(f"\n--- STEP {step_idx} ---")
        print("active_agent:", state.get("active_agent"))
        print("task_type:", state.get("task_type"))
        print("done:", state.get("done"))
        print("current_step:", state.get("current_step"))
        print("needs_review:", state.get("needs_review"))
        print("generated_files:", state.get("generated_files", []))

        # Show last message content (truncated) if available
        if state.get("messages"):
            last_msg = state["messages"][-1]
            content = getattr(last_msg, "content", "")
            if isinstance(content, str):
                short = content[:150].replace("\n", " ")
                print("last_message:", short + ("..." if len(content) > 150 else ""))

        final_state = state

    print("\n=== FINAL STATE ===")
    if final_state:
        print("done:", final_state.get("done"))
        print("Generated files:", final_state.get("generated_files", []))
        print("Steps completed:", final_state.get("current_step"))
        if final_state.get("user_feedback"):
            print("User feedback received:", final_state.get("user_feedback"))
    else:
        print("No state returned.")
"""