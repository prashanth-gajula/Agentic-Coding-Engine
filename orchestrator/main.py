from dotenv import load_dotenv
import os

from workflow_State.main_state import AgentState
from langchain_core.messages import HumanMessage

load_dotenv()
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")


def orchestrator(state: AgentState) -> AgentState:
    """
    Orchestrator (Start/End only):
    - On first entry: ensure user_request exists and hand off to context_agent.
    - On completion: if context_agent marked done=True, keep done=True so router ends.
    """

    # Ensure messages exists
    if "messages" not in state or state["messages"] is None:
        state["messages"] = []

    # If this is a fresh run, capture the request
    if not state.get("user_request"):
        if state.get("messages"):
            last_msg = state["messages"][-1]
            state["user_request"] = getattr(last_msg, "content", "") or ""
        else:
            state["user_request"] = ""

    # If context agent says we're done, do nothing except keep done=True
    if state.get("done"):
        summary = state.get("final_summary", "") or state.get("last_diff", "") or ""
        if summary:
            print(f"[Orchestrator] Workflow complete: {summary}")
        else:
            print("[Orchestrator] Workflow complete.")
        return state

    # Otherwise always hand off to Context Agent (controller)
    state["next_node"] = "context_agent"   # optional, but keeps it explicit
    state["active_agent"] = "context_agent"
    state["done"] = False

    print("[Orchestrator] Handing off to Context Agent...")
    return state
