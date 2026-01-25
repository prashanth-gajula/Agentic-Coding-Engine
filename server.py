# server.py (Complete with LangSmith tracing - Fixed)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
import os
from datetime import datetime
import traceback

# Import your existing workflow
from workflow_State.workflow_main import create_workflow, create_initial_state, run_workflow_with_tracing
from workflow_State.main_state import AgentState

app = FastAPI(title="Agentic IDE Backend API")

# Enable CORS for VS Code extension
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session storage
active_sessions: Dict[str, Dict[str, Any]] = {}


# Request/Response Models
class WorkflowStartRequest(BaseModel):
    request: str
    project_path: str


class ReviewFeedbackRequest(BaseModel):
    session_id: str
    feedback: str
    action: str


@app.get("/")
def root():
    return {
        "status": "running",
        "service": "Agentic IDE Backend",
        "timestamp": datetime.utcnow().isoformat(),
        "langsmith_tracing": os.getenv("LANGCHAIN_TRACING_V2", "false")
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "langsmith_tracing": os.getenv("LANGCHAIN_TRACING_V2", "false")
    }


@app.post("/workflow/start")
async def start_workflow(req: WorkflowStartRequest):
    """Start a new workflow session"""
    try:
        session_id = f"session_{datetime.now().timestamp()}"
        
        # Set PROJECT_ROOT for file operations
        os.environ["PROJECT_ROOT"] = req.project_path
        
        print(f"\n{'='*70}")
        print(f"Starting workflow: {session_id}")
        print(f"Request: {req.request[:100]}...")
        print(f"Project: {req.project_path}")
        print(f"LangSmith: {os.getenv('LANGCHAIN_TRACING_V2', 'false')}")
        print(f"{'='*70}\n")
        
        # Create workflow
        workflow_app = create_workflow()
        
        # Create initial state
        initial_state = create_initial_state(req.request)
        initial_state["project_path"] = req.project_path
        
        # Store session
        active_sessions[session_id] = {
            "workflow": workflow_app,
            "state": initial_state,
            "status": "created",
            "project_path": req.project_path
        }
        
        return {
            "session_id": session_id,
            "status": "created",
            "message": "Workflow session created"
        }
        
    except Exception as e:
        print(f"Error starting workflow: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/workflow/review")
async def submit_review(review: ReviewFeedbackRequest):
    """Submit review feedback and continue workflow if needed"""
    if review.session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = active_sessions[review.session_id]
    state = session["state"]
    
    print(f"\n{'='*70}")
    print(f"Review feedback: {review.session_id}")
    print(f"Action: {review.action}")
    print(f"Feedback: {review.feedback[:100] if review.feedback else '(empty)'}")
    print(f"{'='*70}\n")
    
    # Process review
    approval_keywords = ['looks good', 'approve', 'done', 'ok', 'lgtm']
    is_approval = (
        review.action == "approve" or
        not review.feedback.strip() or
        any(kw in review.feedback.lower() for kw in approval_keywords)
    )
    
    if is_approval:
        # User approved - workflow complete
        print("✅ User approved work - ending workflow")
        state["done"] = True
        state["needs_review"] = False
        session["status"] = "completed"
    else:
        # User requested changes - create new plan
        print("🔄 User requested changes - resetting for new plan")
        
        original_request = state.get("user_request", "")
        previous_work = "Previous work completed:\n"
        for step in state.get("plan", []):
            previous_work += f"- {step.get('instruction', '')} ({step.get('target_file', 'N/A')})\n"
        
        # Build new request incorporating feedback
        new_request = f"{previous_work}\nUser feedback/changes requested:\n{review.feedback}\n\nOriginal request: {original_request}"
        
        # Reset state for new workflow
        state["user_request"] = new_request
        state["user_feedback"] = review.feedback
        state["needs_review"] = False
        state["plan"] = []  # Clear - context agent will create new plan
        state["current_step"] = 0
        state["worker_completed"] = False
        state["next_node"] = "context_agent"
        state["done"] = False
        
        # Mark session as running so WebSocket can continue
        session["status"] = "running"
        session["paused_for_review"] = False
    
    return {"status": "success", "workflow_done": state["done"]}


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket for real-time workflow execution with LangSmith tracing"""
    await websocket.accept()
    
    print(f"\n{'='*70}")
    print(f"WebSocket connected: {session_id}")
    print(f"{'='*70}\n")
    
    if session_id not in active_sessions:
        await websocket.send_json({"type": "error", "message": "Session not found"})
        await websocket.close()
        return
    
    session = active_sessions[session_id]
    workflow = session["workflow"]
    state = session["state"]
    
    try:
        session["status"] = "running"
        
        # Create workflow stream WITH LANGSMITH TRACING
        workflow_stream = run_workflow_with_tracing(
            workflow,
            state,
            config={"recursion_limit": 50}
        )
        
        step_idx = 0
        
        # Stream workflow execution
        for step_state in workflow_stream:
            # Update session state
            session["state"] = step_state
            
            # Send update to extension
            await websocket.send_json({
                "type": "step_update",
                "active_agent": step_state.get("active_agent"),
                "current_step": step_state.get("current_step"),
                "plan": step_state.get("plan", []),
                "generated_files": step_state.get("generated_files", []),
                "file_contents": step_state.get("file_contents", {}),
                "needs_review": step_state.get("needs_review", False),
                "done": step_state.get("done", False)
            })
            
            print(f"Step {step_idx}: {step_state.get('active_agent')} | "
                  f"Review: {step_state.get('needs_review')} | "
                  f"Done: {step_state.get('done')}")
            
            step_idx += 1
            
            # Pause for review (only if review needed AND not done)
            if step_state.get("needs_review") and not step_state.get("done"):
                print(f"\n⏸️  Workflow paused for review")
                await websocket.send_json({
                    "type": "review_required",
                    "plan": step_state.get("plan", []),
                    "generated_files": step_state.get("generated_files", []),
                    "file_contents": step_state.get("file_contents", {})
                })
                session["status"] = "paused_for_review"
                session["paused_for_review"] = True
                break  # Only break for review, not for done
        
        # After loop ends naturally, check final state
        final_state = session.get("state", {})
        if final_state.get("done"):
            print(f"\n✅ Workflow completed")
            await websocket.send_json({
                "type": "workflow_complete",
                "generated_files": final_state.get("generated_files", []),
                "file_contents": final_state.get("file_contents", {})
            })
            session["status"] = "completed"
        
        print(f"\n{'='*70}")
        print(f"WebSocket stream ended: {session_id}")
        print(f"Status: {session['status']}")
        print(f"{'='*70}\n")
        
    except WebSocketDisconnect:
        print(f"WebSocket disconnected: {session_id}")
        session["status"] = "disconnected"
    
    except GeneratorExit:
        # This is expected when generator is closed
        print(f"Generator closed gracefully: {session_id}")
        session["status"] = session.get("status", "completed")
        
    except StopIteration:
        # Generator exhausted naturally
        print(f"Generator completed: {session_id}")
        session["status"] = session.get("status", "completed")
        
    except Exception as e:
        print(f"Error in WebSocket: {e}")
        traceback.print_exc()
        
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e),
                "traceback": traceback.format_exc()
            })
        except:
            pass
        
        session["status"] = "error"
        
    finally:
        # Close websocket
        try:
            await websocket.close()
        except:
            pass


@app.delete("/workflow/{session_id}")
async def delete_session(session_id: str):
    """Clean up a workflow session"""
    if session_id in active_sessions:
        del active_sessions[session_id]
        return {"status": "deleted", "session_id": session_id}
    else:
        raise HTTPException(status_code=404, detail="Session not found")


if __name__ == "__main__":
    import uvicorn  # used to run asynchronous python web applications often with frameworks like fast API
    
    port = int(os.getenv("PORT", 8000))
    
    print("\n" + "="*70)
    print("🚀 Starting Agentic IDE Backend Server")
    print("="*70)
    print(f"Server: http://localhost:{port}")
    print(f"WebSocket: ws://localhost:{port}/ws/{{session_id}}")
    print(f"Health: http://localhost:{port}/health")
    
    # Show LangSmith status
    if os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true":
        print(f"🔍 LangSmith: ENABLED")
        print(f"📊 Project: {os.getenv('LANGCHAIN_PROJECT', 'default')}")
    else:
        print(f"⚠️  LangSmith: DISABLED (set LANGCHAIN_TRACING_V2=true to enable)")
    
    print("="*70 + "\n")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )