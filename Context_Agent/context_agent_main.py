from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import os
import json
import re

from workflow_State.main_state import AgentState
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from prompts.prompts_list import Context_Agent_Prompt
from workflow_tools.filesystemtools import list_files, read_file, search_text
from workflow_State.memory_manager import MemoryManager  # NEW

load_dotenv()
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")

tools = [list_files, read_file, search_text]
model = ChatOpenAI(model="gpt-4o-mini")
model_with_tools = model.bind_tools(tools)


def _extract_json(text: str) -> dict:
    """Extract JSON object from text response"""
    if not text:
        return {}
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except:
        return {}


def context_agent(state: AgentState) -> AgentState:
    """
    Context Agent - Plans and Coordinates Workflow (WITH MEMORY)
    """
    
    # Initialize memory system
    state = MemoryManager.initialize_memory(state)
    
    # Initialize state fields with defaults
    if "plan" not in state or not state["plan"]:
        state["plan"] = []
    if "current_step" not in state:
        state["current_step"] = 0
    if "worker_completed" not in state:
        state["worker_completed"] = False
    if "generated_files" not in state:
        state["generated_files"] = []
    if "needs_review" not in state:
        state["needs_review"] = False
    
    user_request = state.get("user_request", "") or ""
    
    # ============================================================
    # NEW: RESOLVE REFERENCES IN USER REQUEST
    # ============================================================
    resolved_file = MemoryManager.resolve_reference(state, user_request)
    if resolved_file:
        print(f"[ContextAgent] 🧠 Memory resolved reference to: {resolved_file}")
        state["target_file"] = resolved_file
        
        # Update user request to be more explicit
        if "it" in user_request.lower() or "that" in user_request.lower():
            user_request = user_request.replace(" it ", f" {resolved_file} ")
            user_request = user_request.replace(" that ", f" {resolved_file} ")
            state["user_request"] = user_request
    
    # Add user request to conversation memory
    MemoryManager.add_conversation_turn(
        state,
        role="user",
        content=user_request,
        files_mentioned=[resolved_file] if resolved_file else []
    )
    
    # ============================================================
    # STEP 1: Create execution plan (with memory context)
    # ============================================================
    if not state["plan"]:
        # Build context from memory
        memory_context = MemoryManager.build_context_for_agent(state)
        
        system_content = (
            Context_Agent_Prompt
            + "\n\n" + memory_context  # Include memory!
            + "\n\n=== CURRENT PLANNING TASK ===\n"
            f"User request: {user_request}\n\n"
            "Create a detailed execution plan.\n"
            "IMPORTANT: Use the context from memory above to understand file references.\n"
            "If the user mentioned 'it' or 'that file', check the current working file in the context."
        )
        
        # ... rest of planning logic stays the same ...
        messages = [
            SystemMessage(content=system_content),
            HumanMessage(content=f"User request:\n{user_request}\n\nCreate plan.")
        ]
        
        max_iterations = 5
        plan = None
        
        print(f"[ContextAgent] 🤔 Creating execution plan with memory context...")
        
        for iteration in range(max_iterations):
            response = model_with_tools.invoke(messages)
            messages.append(response)
            
            if not response.tool_calls:
                content = getattr(response, "content", "")
                payload = _extract_json(content)
                plan = payload.get("plan", [])
                
                if plan:
                    print(f"[ContextAgent] ✅ Plan created with {len(plan)} steps")
                    break
                else:
                    print("[ContextAgent] ⚠️  No valid plan found, using fallback")
                    break
            
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_id = tool_call["id"]
                
                print(f"[ContextAgent] 🔍 LLM exploring: {tool_name}")
                
                try:
                    if tool_name == "list_files":
                        result = list_files.invoke(tool_args)
                    elif tool_name == "read_file":
                        result = read_file.invoke(tool_args)
                    elif tool_name == "search_text":
                        result = search_text.invoke(tool_args)
                    else:
                        result = f"Unknown tool: {tool_name}"
                    
                    messages.append(ToolMessage(content=str(result), tool_call_id=tool_id))
                    
                except Exception as e:
                    error_msg = f"Error: {str(e)}"
                    print(f"[ContextAgent] ❌ {error_msg}")
                    messages.append(ToolMessage(content=error_msg, tool_call_id=tool_id))
        
        # Fallback
        if not plan:
            print("[ContextAgent] Using fallback plan")
            
            # Smart fallback uses memory
            target = resolved_file or "output.py"
            
            plan = [{
                "agent": "code_agent",
                "instruction": user_request,
                "target_file": target
            }]
        
        state["plan"] = plan
        
        # Display plan
        print(f"\n[ContextAgent] 📋 Execution Plan ({len(plan)} steps):")
        print("=" * 70)
        for i, step in enumerate(plan):
            agent = step.get('agent', 'unknown')
            target = step.get('target_file', 'N/A')
            instruction = step.get('instruction', '')
            display_instruction = instruction[:60] + "..." if len(instruction) > 60 else instruction
            print(f"  Step {i}: [{agent}] → {target}")
            print(f"           {display_instruction}")
        print("=" * 70 + "\n")
    
    # ============================================================
    # STEP 2: Check if worker just completed a step
    # ============================================================
    current_step = state["current_step"]
    worker_completed = state.get("worker_completed", False)
    
    if worker_completed:
        print(f"[ContextAgent] ✅ Step {current_step} completed")
        
        # Clear worker_completed flag
        state["worker_completed"] = False
        
        # Advance to next step
        state["current_step"] += 1
        current_step = state["current_step"]
        
        print(f"[ContextAgent] Moving to step {current_step}")
    
    # ============================================================
    # STEP 3: Check if ALL steps complete → Trigger Review
    # ============================================================
    plan = state["plan"]
    
    if current_step >= len(plan):
        generated_files = state.get("generated_files", [])
        
        print(f"\n[ContextAgent] 🎉 All {len(plan)} steps complete!")
        if generated_files:
            print(f"[ContextAgent] 📁 Files: {', '.join(generated_files)}")
        
        print(f"[ContextAgent] → Triggering review...")
        
        # Add to conversation memory
        MemoryManager.add_conversation_turn(
            state,
            role="assistant",
            content=f"Completed all tasks. Generated: {', '.join(generated_files)}",
            files_mentioned=generated_files
        )
        
        state["needs_review"] = True
        state["next_node"] = "reviewer_agent"
        state["active_agent"] = "reviewer_agent"
        state["done"] = False
        
        return state
    
    # ============================================================
    # STEP 4: Dispatch current step to worker
    # ============================================================
    step = plan[current_step]
    
    agent = step.get("agent", "code_agent")
    instruction = step.get("instruction", "")
    target_file = step.get("target_file", "")
    
    state["current_task"] = instruction
    state["target_file"] = target_file
    state["done"] = False
    state["next_node"] = agent
    state["active_agent"] = agent
    
    print(f"\n[ContextAgent] → Step {current_step}: Dispatching to {agent}")
    print(f"  Instruction: {instruction[:80]}...")
    if target_file:
        print(f"  Target: {target_file}")
    
    return state