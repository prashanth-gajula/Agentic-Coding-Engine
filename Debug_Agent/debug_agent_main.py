from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import os

from workflow_State.main_state import AgentState
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from prompts.prompts_list import Debug_Agent_Prompt
from workflow_tools.filesystemtools import read_file

load_dotenv()
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")

# Base model + read-only tool for debugging
model = ChatOpenAI(model="gpt-4o-mini")
tools = [read_file]
debug_model = model.bind_tools(tools)


def DebugAgent(state: AgentState) -> AgentState:
    """
    Debug Agent - Analyzes errors and suggests fixes (does NOT modify code)
    
    Responsibilities:
    1. Analyze error messages and stack traces
    2. Use read_file to examine problematic code
    3. Identify root cause
    4. Provide detailed fix suggestions for code_agent
    5. Set worker_completed=True when analysis is done
    6. Return to context_agent
    
    The code_agent will implement the suggested fixes in a subsequent step.
    """
    
    current_task = state.get("current_task", "")
    target_file = state.get("target_file", "")
    error_message = state.get("error_message", "")
    stack_trace = state.get("stack_trace", "")
    current_step = state.get("current_step", 0)
    
    print(f"\n[DebugAgent] Starting analysis for Step {current_step}")
    print(f"[DebugAgent] Task: {current_task[:80]}...")
    
    # Build system prompt
    system_content = (
        Debug_Agent_Prompt
    )
    
    # Build user content with debugging context
    user_content_parts = [f"Debug Task: {current_task}"]
    
    if target_file:
        user_content_parts.append(f"Target file: {target_file}")
    
    if error_message:
        user_content_parts.append(f"\nError Message:\n{error_message}")
    
    if stack_trace:
        user_content_parts.append(f"\nStack Trace:\n{stack_trace}")
    
    user_content_parts.append(
        "\nAnalyze this error thoroughly using the read_file tool if needed, "
        "then provide a detailed fix suggestion."
    )
    user_content = "\n".join(user_content_parts)
    
    # Analysis loop - LLM can read multiple files to understand context
    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=user_content)
    ]
    
    max_iterations = 5  # Allow reading multiple files for analysis
    files_analyzed = []
    
    for iteration in range(max_iterations):
        print(f"[DebugAgent] Analysis iteration {iteration + 1}/{max_iterations}")
        
        # Get LLM response
        response = debug_model.invoke(messages)
        messages.append(response)
        
        # Check if LLM finished analysis (no more tool calls)
        if not response.tool_calls:
            # LLM provided final analysis
            print(f"[DebugAgent] ✅ Analysis complete for Step {current_step}")
            break
        
        # Execute tool calls (LLM is reading files to understand the error)
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]
            
            print(f"[DebugAgent]   📖 Reading: {tool_args.get('path', 'unknown')}")
            
            try:
                if tool_name == "read_file":
                    result = read_file.invoke(tool_args)
                    file_path = tool_args.get("path", "unknown")
                    files_analyzed.append(file_path)
                else:
                    result = f"Unknown tool: {tool_name}"
                    print(f"[DebugAgent]   ⚠️  Unknown tool: {tool_name}")
                
                # Send result back to LLM
                messages.append(
                    ToolMessage(
                        content=str(result),
                        tool_call_id=tool_id
                    )
                )
                
            except Exception as e:
                error_msg = f"Error reading file: {str(e)}"
                print(f"[DebugAgent]   ❌ {error_msg}")
                messages.append(
                    ToolMessage(
                        content=error_msg,
                        tool_call_id=tool_id
                    )
                )
    
    # Extract the final analysis from LLM
    final_response = messages[-1] if messages else None
    analysis = ""
    
    if final_response and hasattr(final_response, 'content'):
        analysis = final_response.content
    
    # Store analysis for code_agent to use
    if analysis:
        # Store in last_diff (or create a new field like debug_analysis)
        state["last_diff"] = f"=== DEBUG ANALYSIS ===\n\n{analysis}"
        
        print(f"\n[DebugAgent] 📋 Analysis Summary:")
        print("=" * 70)
        # Show first 300 chars of analysis
        print(analysis[:300] + ("..." if len(analysis) > 300 else ""))
        print("=" * 70)
        
        if files_analyzed:
            print(f"[DebugAgent] Files analyzed: {', '.join(set(files_analyzed))}")
        
        # Signal successful completion
        state["worker_completed"] = True
    else:
        print(f"[DebugAgent] ❌ Failed to generate analysis")
        state["last_diff"] = "Debug analysis failed - no suggestions available"
        state["worker_completed"] = False
    
    # Always return to context_agent
    state["next_node"] = "context_agent"
    state["done"] = False
    
    return state