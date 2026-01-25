# reviewer_agent_main.py (Fixed - only interrupt once)

from workflow_State.main_state import AgentState
from langgraph.types import interrupt


def ReviewerAgent(state: AgentState) -> AgentState:
    """
    Reviewer Agent - Human-in-the-Loop Review (Checkpointing-based)
    """
    
    # ✅ Check if review should be skipped (for local testing)
    if state.get("skip_review", False):
        print("\n" + "=" * 70)
        print("⏭️  REVIEW SKIPPED (skip_review=True)")
        print("=" * 70)
        state["needs_review"] = False
        state["done"] = True
        state["next_node"] = "orchestrator"
        state["active_agent"] = "reviewer_agent"
        return state
    
    # ✅ CHECK: Has user already provided feedback?
    # If yes, this is a RESUME - process feedback and continue
    # If no, this is FIRST TIME - interrupt and wait
    
    if state.get("user_feedback") is not None:
        # ============================================================
        # RESUMING AFTER USER PROVIDED FEEDBACK
        # ============================================================
        print("\n" + "=" * 70)
        print("▶️  Workflow RESUMED - processing user feedback...")
        print("=" * 70)
        
        feedback = state.get("user_feedback", "")
        print(f"\n✅ Received feedback: {feedback[:100] if feedback else '(empty - approved)'}")
        
        # Parse feedback
        approval_keywords = ['looks good', 'approve', 'approved', 'done', 'ok', 'good', 'lgtm', 'perfect']
        is_approval = (
            not feedback or
            feedback.lower() in approval_keywords or
            any(keyword in feedback.lower() for keyword in approval_keywords)
        )
        
        if is_approval:
            # ============================================================
            # APPROVE - End workflow
            # ============================================================
            print("\n✅ Work approved! Ending workflow...")
            
            state["done"] = True
            state["next_node"] = "orchestrator"
            state["needs_review"] = False
            state["user_feedback"] = None  # Clear feedback
            state["final_summary"] = f"Workflow completed successfully. {len(state.get('generated_files', []))} files created/modified."
            
        else:
            # ============================================================
            # REQUEST CHANGES - Create new plan
            # ============================================================
            print(f"\n🔄 Creating new plan based on feedback...")
            print(f"Feedback: {feedback}")
            
            plan = state.get("plan", [])
            
            # Create new user request incorporating feedback
            original_request = state.get("user_request", "")
            new_request = f"Previous work completed:\n"
            for i, step in enumerate(plan):
                new_request += f"- {step.get('instruction', '')} ({step.get('target_file', 'N/A')})\n"
            new_request += f"\nUser feedback/changes requested:\n{feedback}\n"
            new_request += f"\nOriginal request: {original_request}"
            
            # Reset for new plan
            state["plan"] = []
            state["current_step"] = 0
            state["user_request"] = new_request
            state["needs_review"] = False
            state["worker_completed"] = False
            state["user_feedback"] = None  # ✅ Clear feedback so we don't loop
            state["next_node"] = "context_agent"
            state["active_agent"] = "context_agent"
            state["done"] = False
            
            print("✅ Returning to Context Agent to create revised plan...")
        
        return state
    
    # ============================================================
    # FIRST TIME - NEED TO REQUEST REVIEW
    # ============================================================
    
    plan = state.get("plan", [])
    generated_files = state.get("generated_files", [])
    
    # Display comprehensive summary
    print("\n" + "=" * 70)
    print("🎉 WORKFLOW PLAN COMPLETED - REVIEW REQUIRED")
    print("=" * 70)
    
    print(f"\n📋 Completed Plan Summary:")
    print(f"   Total steps executed: {len(plan)}")
    
    print("\n📝 Steps completed:")
    for i, step in enumerate(plan):
        agent = step.get('agent', 'unknown')
        instruction = step.get('instruction', '')[:60]
        target = step.get('target_file', 'N/A')
        print(f"   Step {i}: [{agent}] {target}")
        print(f"            {instruction}...")
    
    if generated_files:
        print(f"\n📂 Files Created/Modified:")
        for file in generated_files:
            print(f"   ✓ {file}")
    
    print("\n" + "=" * 70)
    print("💬 REVIEW FEEDBACK REQUIRED")
    print("=" * 70)
    
    # ✅ Set flag and INTERRUPT workflow (pauses here until update_state)
    state["needs_review"] = True
    state["active_agent"] = "reviewer_agent"
    
    print("\n⏸️  Workflow INTERRUPTED - waiting for user review...")
    print("    (In production: user will review via VS Code extension)")
    print("=" * 70)
    
    # ✅ This pauses the workflow and saves checkpoint
    # Execution stops here until workflow.update_state() is called
    interrupt("User review required - waiting for feedback")
    
    # This code is unreachable - interrupt() stops execution here
    # When resumed, the function is called again from the top
    # But this time user_feedback will be set, so we go to the resume block above
    
    return state