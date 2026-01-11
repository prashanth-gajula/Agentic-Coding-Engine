from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import os

from workflow_State.main_state import AgentState
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from prompts.prompts_list import Code_Agent_Prompt
from workflow_tools.filesystemtools import read_file, write_file, apply_patch
from workflow_State.memory_manager import MemoryManager

load_dotenv()
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")

tools = [read_file, write_file, apply_patch]
model = ChatOpenAI(model="gpt-4o-mini")
code_model = model.bind_tools(tools)


def CodeAgent(state: AgentState) -> AgentState:
    """
    Code Agent - Executes ONE step from the plan (WITH MEMORY)
    
    Flow:
    - Context Agent assigns ONE step (e.g., "create file X")
    - Code Agent can use MULTIPLE tool calls to complete that ONE step
    - Code Agent signals completion and returns to Context Agent
    - Code Agent updates memory with file operations
    - Context Agent then assigns the NEXT step
    
    Internal loop: Allows multiple tool calls within one step
    External loop: Context Agent controls step progression
    """
    
    # Initialize memory system
    state = MemoryManager.initialize_memory(state)
    
    current_task = state.get("current_task", "")
    target_file = state.get("target_file", "")
    current_step = state.get("current_step", 0)
    
    print(f"\n[CodeAgent] Starting work on Step {current_step}")
    print(f"[CodeAgent] Task: {current_task[:80]}...")
    
    # Build context from memory for better understanding
    memory_context = MemoryManager.build_context_for_agent(state)
    
    system_content = (
        Code_Agent_Prompt
        + "\n\n" + memory_context  # Include memory context
        + "\n\nUse the context above to understand file references and previous work."
    )
    
    user_content = (
        f"Current Step: {current_step}\n"
        f"Task for THIS step: {current_task}\n"
    )
    if target_file:
        user_content += f"Target file: {target_file}\n"
    
    user_content += "\nComplete THIS step using the available tools. When done, confirm completion."
    
    # Multi-iteration loop (within one step)
    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=user_content)
    ]
    
    max_iterations = 5  # Safety limit for this ONE step
    files_created = []
    files_modified = []
    files_read = []
    
    for iteration in range(max_iterations):
        print(f"[CodeAgent] Iteration {iteration + 1}/{max_iterations}")
        
        # Get LLM response
        response = code_model.invoke(messages)
        messages.append(response)
        
        # Check if LLM wants to use tools
        if not response.tool_calls:
            # No more tool calls - this step is complete
            print(f"[CodeAgent] Step {current_step} execution complete")
            break
        
        # Execute each tool call
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]
            
            print(f"[CodeAgent]   🔧 {tool_name}({list(tool_args.keys())})")
            
            try:
                # Execute the appropriate tool
                if tool_name == "write_file":
                    result = write_file.invoke(tool_args)
                    file_path = tool_args.get("path", "unknown")
                    
                    # Determine if this is a new file or modification
                    is_new_file = file_path not in state.get("generated_files", [])
                    
                    if is_new_file:
                        files_created.append(file_path)
                        print(f"[CodeAgent]   ✅ Created: {file_path}")
                        
                        # Update memory: file created
                        MemoryManager.update_file_context(
                            state,
                            file_path=file_path,
                            operation="created",
                            agent="code_agent"
                        )
                    else:
                        files_modified.append(file_path)
                        print(f"[CodeAgent]   ✅ Modified: {file_path}")
                        
                        # Update memory: file modified
                        MemoryManager.update_file_context(
                            state,
                            file_path=file_path,
                            operation="modified",
                            agent="code_agent"
                        )
                    
                elif tool_name == "read_file":
                    result = read_file.invoke(tool_args)
                    file_path = tool_args.get("path", "unknown")
                    files_read.append(file_path)
                    print(f"[CodeAgent]   📖 Read: {file_path}")
                    
                    # Update memory: file read
                    MemoryManager.update_file_context(
                        state,
                        file_path=file_path,
                        operation="read",
                        agent="code_agent"
                    )
                    
                elif tool_name == "apply_patch":
                    result = apply_patch.invoke(tool_args)
                    file_path = tool_args.get("path", "unknown")
                    files_modified.append(file_path)
                    print(f"[CodeAgent]   🔧 Patched: {file_path}")
                    
                    # Update memory: file modified
                    MemoryManager.update_file_context(
                        state,
                        file_path=file_path,
                        operation="modified",
                        agent="code_agent"
                    )
                    
                else:
                    result = f"Unknown tool: {tool_name}"
                    print(f"[CodeAgent]   ⚠️  Unknown tool: {tool_name}")
                
                # Add tool result back to conversation
                messages.append(
                    ToolMessage(
                        content=str(result),
                        tool_call_id=tool_id
                    )
                )
                
            except Exception as e:
                error_msg = f"Error: {str(e)}"
                print(f"[CodeAgent]   ❌ {tool_name} failed: {e}")
                messages.append(
                    ToolMessage(
                        content=error_msg,
                        tool_call_id=tool_id
                    )
                )
    
    # ===== FIXED CODE: Read file contents with correct paths =====
    # Update state with results from THIS step
    if files_created or files_modified:
        # Initialize file_contents if it doesn't exist
        if "file_contents" not in state:
            state["file_contents"] = {}
        
        generated = state.get("generated_files", [])
        
        # Get the project path from state (absolute path passed by VS Code)
        project_path = state.get("project_path", os.getcwd())
        
        print(f"[CodeAgent]   📂 Project path: {project_path}")
        print(f"[CodeAgent]   📂 Current working directory: {os.getcwd()}")
        
        # Process newly created files
        for file_path in files_created:
            if file_path not in generated:
                generated.append(file_path)
            
            # Build the absolute path
            if os.path.isabs(file_path):
                abs_path = file_path
            else:
                abs_path = os.path.join(project_path, file_path)
            
            print(f"[CodeAgent]   🔍 Attempting to read: {file_path}")
            print(f"[CodeAgent]   📁 Absolute path: {abs_path}")
            print(f"[CodeAgent]   ✓ File exists? {os.path.exists(abs_path)}")
            
            # Read and store file contents
            try:
                with open(abs_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    state["file_contents"][file_path] = content
                    print(f"[CodeAgent]   ✅ Successfully read {len(content)} characters from {file_path}")
            except Exception as e:
                print(f"[CodeAgent]   ❌ ERROR reading {abs_path}")
                print(f"[CodeAgent]   ❌ Error type: {type(e).__name__}")
                print(f"[CodeAgent]   ❌ Error message: {e}")
                
                # Debug: List files in project directory
                try:
                    files_in_dir = os.listdir(project_path)
                    print(f"[CodeAgent]   📁 Files in project directory: {files_in_dir}")
                except:
                    pass
                
                state["file_contents"][file_path] = f"Error reading file: {e}"
        
        # Process modified files
        for file_path in files_modified:
            if file_path not in generated:
                generated.append(file_path)
            
            # Build the absolute path
            if os.path.isabs(file_path):
                abs_path = file_path
            else:
                abs_path = os.path.join(project_path, file_path)
            
            print(f"[CodeAgent]   🔍 Attempting to read modified file: {file_path}")
            print(f"[CodeAgent]   📁 Absolute path: {abs_path}")
            
            # Read and store updated file contents
            try:
                with open(abs_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    state["file_contents"][file_path] = content
                    print(f"[CodeAgent]   ✅ Successfully read updated contents ({len(content)} chars)")
            except Exception as e:
                print(f"[CodeAgent]   ❌ ERROR reading {abs_path}: {e}")
                state["file_contents"][file_path] = f"Error reading file: {e}"
        
        state["generated_files"] = generated
        # ===== END FIXED CODE =====
        
        print(f"[CodeAgent] ✅ Step {current_step} complete!")
        if files_created:
            print(f"[CodeAgent]   Created: {files_created}")
        if files_modified:
            print(f"[CodeAgent]   Modified: {files_modified}")
        if files_read:
            print(f"[CodeAgent]   Read: {files_read}")
        
        # Add to conversation memory
        all_files = list(set(files_created + files_modified))
        operation_summary = []
        if files_created:
            operation_summary.append(f"created {len(files_created)} file(s)")
        if files_modified:
            operation_summary.append(f"modified {len(files_modified)} file(s)")
        
        MemoryManager.add_conversation_turn(
            state,
            role="assistant",
            content=f"Code agent {' and '.join(operation_summary)}",
            files_mentioned=all_files
        )
        
        state["worker_completed"] = True
        
    else:
        print(f"[CodeAgent] ❌ Step {current_step} failed - no files created/modified")
        
        # Add failure to conversation memory
        MemoryManager.add_conversation_turn(
            state,
            role="assistant",
            content="Code agent attempted task but no files were created or modified",
            files_mentioned=[]
        )
        
        state["worker_completed"] = False
    
    # Always return to context agent (which will advance to next step)
    state["next_node"] = "context_agent"
    state["done"] = False
    
    return state