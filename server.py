# server.py (Complete with checkpointing support)

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


"""@app.get("/health")
def health():
    return {
        "status": "healthy",
        "langsmith_tracing": os.getenv("LANGCHAIN_TRACING_V2", "false")
    }
"""
@app.get("/health")
def health():
    status = {
        "status": "healthy",
        "langsmith_tracing": os.getenv("LANGCHAIN_TRACING_V2", "false"),
        "active_sessions": len(active_sessions),
        "database": "not_configured"
    }
    
    # Check database connection
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
            # Use context manager properly
            with PostgresSaver.from_conn_string(database_url) as checkpointer:
                checkpointer.setup()
            status["database"] = "connected"
        except Exception as e:
            status["database"] = f"error: {str(e)}"
            status["status"] = "degraded"
    
    return status

@app.post("/workflow/start")
async def start_workflow(req: WorkflowStartRequest):
    """Start a new workflow session with checkpointing"""
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
        
        # Create workflow with checkpointing
        workflow_app = create_workflow()
        
        # ✅ Create initial state (skip_review=False for production)
        initial_state = create_initial_state(req.request, skip_review=False)
        initial_state["project_path"] = req.project_path
        
        # ✅ Store session with thread_id for checkpointing
        active_sessions[session_id] = {
            "workflow": workflow_app,
            "state": initial_state,
            "status": "created",
            "project_path": req.project_path,
            "thread_id": session_id  # Use session_id as thread_id
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
    """Submit review feedback and update checkpoint"""
    if review.session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = active_sessions[review.session_id]
    workflow = session["workflow"]
    thread_id = session["thread_id"]
    
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
    
    # ✅ Update the checkpointed state using LangGraph's update_state
    config = {"configurable": {"thread_id": thread_id}}
    
    try:
        if is_approval:
            print("✅ User approved - updating checkpoint")
            # ✅ Update checkpoint with approval
            workflow.update_state(
                config,
                {
                    "user_feedback": "approved",
                    "done": True,
                    "needs_review": False
                }
            )
            session["status"] = "resuming"
        else:
            print("🔄 User requested changes - updating checkpoint")
            # ✅ Update checkpoint with feedback for changes
            workflow.update_state(
                config,
                {
                    "user_feedback": review.feedback,
                    "needs_review": False,
                    "done": False
                }
            )
            session["status"] = "resuming"
        
        return {
            "status": "success",
            "message": "Feedback received, workflow will resume"
        }
        
    except Exception as e:
        print(f"Error updating checkpoint: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to update checkpoint: {str(e)}")


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket for real-time workflow execution with checkpointing"""
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
    initial_state = session.get("state")
    thread_id = session["thread_id"]
    
    try:
        # ✅ Determine if this is initial run or resuming from checkpoint
        is_resuming = session.get("status") == "resuming"
        
        if is_resuming:
            print(f"▶️  Resuming workflow from checkpoint...")
            session["status"] = "running"
            stream_state = None  # None = resume from checkpoint
        else:
            print(f"▶️  Starting new workflow...")
            session["status"] = "running"
            stream_state = initial_state  # Start with initial state
        
        # ✅ Config with thread_id for checkpointing
        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": 50
        }
        
        # Create workflow stream WITH LANGSMITH TRACING AND CHECKPOINTING
        workflow_stream = run_workflow_with_tracing(
            workflow,
            stream_state,  # None if resuming, initial_state if starting
            config=config
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
            
            # ✅ Check if workflow is paused for review (due to interrupt)
            if step_state.get("needs_review") and not step_state.get("done"):
                print(f"\n⏸️  Workflow interrupted for review (checkpoint saved)")
                await websocket.send_json({
                    "type": "review_required",
                    "plan": step_state.get("plan", []),
                    "generated_files": step_state.get("generated_files", []),
                    "file_contents": step_state.get("file_contents", {})
                })
                session["status"] = "paused_for_review"
                # ✅ Workflow is paused via interrupt() - generator stops naturally
                # Loop will end when interrupt stops yielding states
        
        # After loop ends, check final state
        final_state = session.get("state", {})
        
        if final_state.get("done"):
            print(f"\n✅ Workflow completed")
            await websocket.send_json({
                "type": "workflow_complete",
                "generated_files": final_state.get("generated_files", []),
                "file_contents": final_state.get("file_contents", {})
            })
            session["status"] = "completed"
        elif final_state.get("needs_review"):
            print(f"\n⏸️  Workflow paused - waiting for review")
            session["status"] = "paused_for_review"
        
        print(f"\n{'='*70}")
        print(f"WebSocket stream ended: {session_id}")
        print(f"Status: {session['status']}")
        print(f"{'='*70}\n")
        
    except WebSocketDisconnect:
        print(f"WebSocket disconnected: {session_id}")
        session["status"] = "disconnected"
    
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