# Agentic-Coding-Engine



**Orchestrator Agent**
- Entry point and final gate
- Determines if the workflow is complete or needs more work
- Routes to Context Agent or ends the workflow

**Context Agent (Key Innovation)**
- Acts as the controller
- Analyzes the request and codebase context
- Produces a multi-step execution plan
- Dispatches work to Code/Debug
- Routes to Reviewer for human feedback

**Code Agent**
- Generates code files based on each plan step
- Handles multi-file project creation and structured output

**Debug Agent**
- Analyzes errors in generated code
- Produces corrected versions and updates state

**Reviewer Agent**
- Shows generated files + plan to the user
- Calls `interrupt()` to intentionally pause the workflow
- Waits for human feedback to resume

---

### 3) Storage Layer — PostgreSQL Checkpointing

This is the feature that turns the system from “cool demo” to **production-ready infrastructure**.

#### What Gets Stored
- Complete workflow state at each node transition
- User requests, execution plans, generated files
- Agent outputs and conversation history
- Thread IDs linking checkpoint chains

#### Why It Matters
- Workflows survive server restarts (Railway can restart anytime)
- Users can walk away during review and return hours later
- Failed workflows are debuggable by examining checkpoint history
- Enables true pause/resume with `interrupt()` and `update_state()`

#### Core Tables (LangGraph Postgres Saver)
- `checkpoints` — main state snapshots
- `checkpoint_blobs` — large/binary state
- `checkpoint_writes` — pending writes

---

## 🔎 Observability — LangSmith Tracing

Every workflow execution is traced in LangSmith:
- Agent-to-agent transitions
- LLM calls with prompts and responses
- Execution time per node
- Error stack traces

This is critical for debugging and production monitoring.

---

## 🛡️ Production Safeguards

Agentic IDE includes real-world reliability protections:

- **Timeout Handling (5 minutes max per workflow)**
  - Prevents infinite loops and runaway costs
  - Returns a clear error message when exceeded

- **Rate Limiting (50 workflows/hour per IP)**
  - Prevents abuse and cost explosions
  - Returns HTTP 429 after limit is reached  
  - (Note: in-memory rate tracking resets on restart; Redis is a future improvement)

- **Recursion / Step Limits (max 50 node executions)**
  - Catches logic errors that cause looping
  - Terminates safely with a recursion error

- **Auto-commit PostgreSQL**
  - Ensures checkpoints persist immediately

- **Graceful Degradation**
  - If PostgreSQL is unavailable:
    - system can fall back to in-memory checkpointing (optional)
    - logs warnings
    - continues with reduced persistence guarantees

---

## 🧩 Why Checkpointing Is Essential (Memory Isn’t Enough)

In development, in-memory checkpointing (like `MemorySaver`) feels fine. In production it fails because:
- Servers restart mid-workflow
- Users don’t respond instantly to review prompts
- WebSockets drop due to network instability
- Horizontal scaling requires shared state

**Checkpointing fixes this** by persisting complete snapshots after each major state transition, including pauses for review.

Impact:
- ✅ Workflows survive restarts  
- ✅ Users can review on their own time  
- ✅ Can scale across multiple server instances  
- ✅ Full state history enables fast debugging  

Cost:
- ~50ms per checkpoint (tiny compared to LLM latency)

---

## 🧑‍⚖️ Human-in-the-Loop — Pause and Resume

Fully autonomous code generation is risky:
- subtle security vulnerabilities
- wrong assumptions about requirements
- overwriting files unintentionally
- mismatched code conventions

Agentic IDE uses a “review checkpoint” pattern:
1. Agents generate code + state updates
2. Reviewer Agent calls `interrupt()` and saves checkpoint (`needs_review=true`)
3. VS Code shows generated files + plan
4. User selects:
   - **Approve** → resume and finalize
   - **Request Changes** → feedback injected and agents iterate
5. Workflow resumes via `update_state()` and continues from the paused node

This mirrors how real development works: **generate → review → refine → approve**.

---

## 🔁 Why Multi-Agent Beats a Single Mega-Prompt

**Single-agent (mega-prompt) drawbacks**
- context overload
- no specialization
- hard to debug failures
- hard to improve one capability without breaking others

**Multi-agent benefits**
- separation of concerns
- transparent routing decisions
- easy to debug with traces
- modular improvements (upgrade one agent without rewriting everything)
- composable (add new agents like Docs/Test/Refactor later)

---

## 👀 Example Workflow (End-to-End)

Request:
> “Create a Python function to check if two strings are anagrams.”

Typical sequence:
1. **Orchestrator** routes new request → Context
2. **Context** creates a plan (e.g., generate `string_utils.py`)
3. **Code Agent** generates file(s)
4. **Context** verifies plan steps complete
5. **Reviewer Agent** calls `interrupt()` → checkpoint saved → review UI displayed
6. User clicks **Approve**
7. Backend injects feedback via `update_state()` and resumes
8. **Orchestrator** ends workflow with success
9. Extension writes received files to the workspace

---

## 🧰 Tech Stack

- **Frontend**: VS Code Extension (TypeScript), Webview UI, Workspace FS APIs
- **Backend**: FastAPI (Python), WebSockets
- **Workflow**: LangGraph multi-agent state graph, conditional routing, `interrupt()`
- **Persistence**: PostgreSQL checkpointing (LangGraph Postgres saver)
- **Observability**: LangSmith tracing
- **Deployment**: Railway (backend + Postgres)

---
# macOS/Linux
source .venv/bin/activate
