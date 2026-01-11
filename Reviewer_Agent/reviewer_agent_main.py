from workflow_State.main_state import AgentState


def ReviewerAgent(state: AgentState) -> AgentState:
    """
    Reviewer Agent - Human-in-the-Loop Review (after entire plan completes)
    
    Called by Context Agent after ALL steps complete.
    
    Responsibilities:
    1. Display summary of all completed work
    2. Get direct user feedback (free-form text input)
    3. Based on feedback:
       - Empty/approval keywords: End workflow
       - Specific feedback: Create new plan, return to context_agent
    """
    
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
    
    # Get user feedback
    print("\n" + "=" * 70)
    print("💬 REVIEW FEEDBACK")
    print("=" * 70)
    print("\nPlease review the completed work above.")
    print("\nProvide your feedback:")
    print("  • Press ENTER (empty) to approve and END the workflow")
    print("  • Type 'looks good', 'approve', 'done', or 'ok' to END the workflow")
    print("  • Type specific feedback/changes to create a NEW plan and continue")
    print("=" * 70)
    
    feedback = input("\nYour feedback: ").strip()
    
    # Parse feedback
    approval_keywords = ['looks good', 'approve', 'approved', 'done', 'ok', 'good', 'lgtm', 'perfect']
    is_approval = (
        not feedback or  # Empty = approval
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
        state["final_summary"] = f"Workflow completed successfully. {len(generated_files)} files created/modified."
        
    else:
        # ============================================================
        # REQUEST CHANGES - Create new plan
        # ============================================================
        print(f"\n🔄 Creating new plan based on your feedback...")
        print(f"Feedback: {feedback}")
        
        # Create new user request incorporating feedback
        original_request = state.get("user_request", "")
        new_request = f"Previous work completed:\n"
        for i, step in enumerate(plan):
            new_request += f"- {step.get('instruction', '')} ({step.get('target_file', 'N/A')})\n"
        new_request += f"\nUser feedback/changes requested:\n{feedback}\n"
        new_request += f"\nOriginal request: {original_request}"
        
        # Clear the plan so context_agent creates a new one
        state["plan"] = []
        state["current_step"] = 0
        state["user_request"] = new_request
        
        # Clear flags
        state["needs_review"] = False
        state["worker_completed"] = False
        
        # Store feedback
        state["user_feedback"] = feedback
        
        # Return to context_agent - it will create new plan
        state["next_node"] = "context_agent"
        state["active_agent"] = "context_agent"
        state["done"] = False
        
        print("✅ Returning to Context Agent to create revised plan...")
    
    return state