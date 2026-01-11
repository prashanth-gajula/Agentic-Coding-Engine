from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage

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
    graph = StateGraph(AgentState)

    # Add all nodes
    graph.add_node("orchestrator", orchestrator)
    graph.add_node("context_agent", context_agent)
    graph.add_node("code_agent", CodeAgent)
    graph.add_node("debug_agent", DebugAgent)
    graph.add_node("reviewer_agent", ReviewerAgent)  # NEW

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
            "reviewer_agent": "reviewer_agent",  # NEW
            "orchestrator": "orchestrator",
        },
    )

    # All workers return to context_agent
    graph.add_edge("code_agent", "context_agent")
    graph.add_edge("debug_agent", "context_agent")
    #graph.add_edge("document_agent", "context_agent")
    
    # Reviewer also returns to context_agent
    graph.add_edge("reviewer_agent", "context_agent")  # NEW

    return graph.compile()

def create_initial_state(user_request: str) -> AgentState:
    """
    Helper function to create initial state for a workflow.
    
    Called by API server with user's request from VS Code.
    
    Args:
        user_request: The task description from the user
        
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
        "conversation_history": [],
        "recent_files": [],
        "current_working_file": None,
        "reference_context": {}
    }
"""
---->This is for local testing<-----
the input for the workflow is handled by the fast API this is just to test the agentic workflow.
if __name__ == "__main__":
    app = create_workflow()

    initial_user_request = "can you create me a python code to connect to pinecone vector database and a langchain agent that uses this vector database as one of the tool i need these two in different files and the titles of these files need to be based on their functionality."
    
    # Other example requests:
    # initial_user_request = "the pinecone_connection file is empty can you pls complete this file i need the index creation and chunking of the files and storing them in the index and in the langchain agent i need code just to connect to this pinecone vectorstore and perform retrival and ans completion i wnat langchain to use stuffed document chain to connect to the pinecone index."
    # initial_user_request = "can you change the function names in calculator.py file using the imp terms from bahubali move the names of the functions should represent the popular characters or famous ideogoly in the movie."
    
    initial_state: AgentState = {
        "messages": [HumanMessage(content=initial_user_request)],
        "user_request": initial_user_request,
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
        "needs_review": False,  # NEW - for reviewer agent
        "user_feedback": None,  # NEW - stores human feedback
    }

    print("=== Starting workflow ===")
    print("Initial user request:", initial_user_request)
    print("------------------------")

    final_state = None

    # Stream the graph execution step by step
    for step_idx, state in enumerate(
        app.stream(initial_state, stream_mode="values", config={"recursion_limit": 50})
    ):
        print(f"\n--- STEP {step_idx} ---")
        print("active_agent:", state.get("active_agent"))
        print("task_type:", state.get("task_type"))
        print("done:", state.get("done"))
        print("current_step:", state.get("current_step"))
        print("needs_review:", state.get("needs_review"))  # NEW - show review status
        print("generated_files:", state.get("generated_files", []))

        # Show last message content (truncated) if available
        if state.get("messages"):
            last_msg = state["messages"][-1]
            content = getattr(last_msg, "content", "")
            if isinstance(content, str):
                short = content[:150].replace("\n", " ")
                print("last_message:", short + ("..." if len(content) > 150 else ""))

        final_state = state

        # Optional: break early if done
        if state.get("done"):
            print("\n✅ Workflow complete!")
            break

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