# Agentic IDE

AI-powered coding assistant with multi-agent workflow system.

## Features

- 🤖 Multi-agent workflow (Orchestrator, Context Agent, Code Agent, Reviewer)
- 💻 Real-time code generation
- 📝 Automatic file creation and modification
- ☁️ Cloud-deployed backend on Railway
- 🔄 Interactive review system

## Getting Started

1. **Open a workspace folder** in VS Code
2. **Click the robot icon** 🤖 in the Activity Bar (left sidebar)
3. **Type your request** in the chat (e.g., "create a linked list in Python")
4. **Review and approve** generated code

## Configuration

### Backend URL

Configure your backend URL in one of these ways:

**Option 1: .env file (Recommended)**

Create `vscode-extension/.env`:
```
BACKEND_URL=https://your-backend.railway.app
```

**Option 2: VS Code Settings**

1. Open Settings (Ctrl+,)
2. Search for "Agentic IDE"
3. Set "Backend Url" to your Railway deployment URL

## Requirements

- VS Code 1.85.0 or higher
- Backend server running (Railway or localhost)

## Usage Examples

- "Implement a binary search algorithm in Python"
- "Create unit tests for the LinkedList class"
- "Add error handling to the API module"
- "Refactor the database connection code"

## Support

For issues or questions, please contact the developer.

## Release Notes

### 0.1.0

Initial release of Agentic IDE
- Multi-agent workflow system
- Code generation and review
- Cloud deployment support