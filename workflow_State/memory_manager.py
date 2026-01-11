from typing import List, Dict, Optional, Any
from datetime import datetime
from workflow_State.main_state import AgentState


class MemoryManager:
    """
    Manages conversational memory and context tracking across the workflow.
    
    Handles:
    - Conversation history
    - File context (recently worked files)
    - Reference resolution ("it", "that file", etc.)
    """
    
    @staticmethod
    def initialize_memory(state: AgentState) -> AgentState:
        """Initialize memory fields if they don't exist"""
        if "conversation_history" not in state:
            state["conversation_history"] = []
        if "recent_files" not in state:
            state["recent_files"] = []
        if "current_working_file" not in state:
            state["current_working_file"] = None
        if "reference_context" not in state:
            state["reference_context"] = {}
        
        return state
    
    @staticmethod
    def add_conversation_turn(
        state: AgentState,
        role: str,
        content: str,
        files_mentioned: List[str] = None
    ) -> AgentState:
        """
        Add a conversation turn to memory.
        
        Args:
            state: Current workflow state
            role: "user" or "assistant"
            content: Message content
            files_mentioned: List of files referenced in this turn
        """
        if "conversation_history" not in state:
            state["conversation_history"] = []
        
        turn = {
            "role": role,
            "content": content,
            "files_mentioned": files_mentioned or [],
            "timestamp": datetime.utcnow().isoformat()
        }
        
        state["conversation_history"].append(turn)
        
        # Keep only last 10 turns to avoid context overflow
        if len(state["conversation_history"]) > 10:
            state["conversation_history"] = state["conversation_history"][-10:]
        
        return state
    
    @staticmethod
    def update_file_context(
        state: AgentState,
        file_path: str,
        operation: str,
        agent: str
    ) -> AgentState:
        """
        Update the file context memory when a file is worked on.
        
        Args:
            state: Current workflow state
            file_path: Path to the file
            operation: "created", "modified", "read", "deleted"
            agent: Which agent performed the operation
        """
        if "recent_files" not in state:
            state["recent_files"] = []
        
        # Remove existing entry for this file
        state["recent_files"] = [
            f for f in state["recent_files"] 
            if f["file_path"] != file_path
        ]
        
        # Add new entry at the front (most recent)
        file_entry = {
            "file_path": file_path,
            "last_modified": datetime.utcnow().isoformat(),
            "operation": operation,
            "agent": agent
        }
        
        state["recent_files"].insert(0, file_entry)
        
        # Keep only last 20 files
        if len(state["recent_files"]) > 20:
            state["recent_files"] = state["recent_files"][:20]
        
        # Update current working file
        if operation in ["created", "modified"]:
            state["current_working_file"] = file_path
        
        return state
    
    @staticmethod
    def resolve_reference(state: AgentState, user_input: str) -> Optional[str]:
        """
        Resolve ambiguous references like "it", "that file", "the script".
        
        Returns the most likely file the user is referring to.
        
        Args:
            state: Current workflow state
            user_input: User's message
            
        Returns:
            File path if reference can be resolved, None otherwise
        """
        user_lower = user_input.lower()
        
        # Direct file mentions take precedence
        for file in state.get("generated_files", []):
            if file.lower() in user_lower:
                return file
        
        # Check for pronouns/references
        reference_keywords = [
            "it", "that", "this", "the file", "the script", 
            "that file", "this file", "the code", "that code"
        ]
        
        has_reference = any(keyword in user_lower for keyword in reference_keywords)
        
        if has_reference:
            # Check current working file
            if state.get("current_working_file"):
                print(f"[Memory] Resolved reference to: {state['current_working_file']}")
                return state["current_working_file"]
            
            # Check most recently modified file
            recent_files = state.get("recent_files", [])
            if recent_files:
                most_recent = recent_files[0]
                if most_recent["operation"] in ["created", "modified"]:
                    print(f"[Memory] Resolved reference to most recent: {most_recent['file_path']}")
                    return most_recent["file_path"]
            
            # Check generated files (most recent)
            generated = state.get("generated_files", [])
            if generated:
                print(f"[Memory] Resolved reference to last generated: {generated[-1]}")
                return generated[-1]
        
        return None
    
    @staticmethod
    def get_conversation_context(state: AgentState, last_n: int = 5) -> str:
        """
        Get recent conversation context as a formatted string.
        
        Args:
            state: Current workflow state
            last_n: Number of recent turns to include
            
        Returns:
            Formatted conversation history
        """
        history = state.get("conversation_history", [])
        recent = history[-last_n:] if len(history) > last_n else history
        
        if not recent:
            return "No previous conversation."
        
        context = "Recent conversation:\n"
        for turn in recent:
            role = turn["role"].capitalize()
            content = turn["content"][:100]  # Truncate long messages
            context += f"{role}: {content}\n"
            if turn.get("files_mentioned"):
                context += f"  (Files: {', '.join(turn['files_mentioned'])})\n"
        
        return context
    
    @staticmethod
    def get_file_context(state: AgentState) -> str:
        """
        Get summary of recent file operations.
        
        Returns:
            Formatted file context
        """
        recent_files = state.get("recent_files", [])[:5]  # Last 5 files
        
        if not recent_files:
            return "No files worked on yet."
        
        context = "Recently worked files:\n"
        for file_info in recent_files:
            context += f"- {file_info['file_path']} ({file_info['operation']} by {file_info['agent']})\n"
        
        current = state.get("current_working_file")
        if current:
            context += f"\nCurrent focus: {current}\n"
        
        return context
    
    @staticmethod
    def build_context_for_agent(state: AgentState) -> str:
        """
        Build comprehensive context string for agents to use.
        
        Returns:
            Complete context including conversation and file history
        """
        conversation = MemoryManager.get_conversation_context(state)
        files = MemoryManager.get_file_context(state)
        
        context = f"""
=== CONTEXT FROM MEMORY ===

{conversation}

{files}

Use this context to understand what the user is referring to.
If the user says "it", "that file", or similar references, check the current working file or recent files above.

=========================
"""
        return context