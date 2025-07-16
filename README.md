# MCP Agent Coordinator

A Model Context Protocol (MCP) server for coordinating multiple parallel agents working on the same project within an IDE. This system manages projects, tasks, todo items, and file locking to enable safe concurrent development by autonomous agents.

## Features

- **Project Management**: Track multiple projects identified by unique names
- **Task Organization**: Group related todo items into tasks (similar to sprints)
- **Dependency Tracking**: Define execution order and dependencies between tasks and todo items
- **File Locking**: Automatic file locking prevents conflicts when multiple agents work simultaneously
- **Agent Assignment**: Intelligent work distribution based on availability and dependencies
- **Progress Tracking**: Real-time status updates and completion tracking
- **HTTP Transport**: Easy integration with Cursor via localhost URL

## Quick Start

### Option 1: HTTP Server (Recommended for Cursor)

The HTTP server runs on localhost:8001 and is the easiest way to connect with Cursor:

#### Windows
```powershell
# PowerShell (recommended)
.\start_http_server.ps1

# OR Command Prompt
start_http_server.bat
```

#### Linux/macOS
```bash
# First activate the virtual environment
source .venv/bin/activate

# Install dependencies
pip install uvicorn

# Start HTTP server
python http_server.py
```

**Cursor Configuration (HTTP):**
```json
{
  "mcpServers": {
    "agent-coordinator": {
      "url": "http://127.0.0.1:8001"
    }
  }
}
```

### Option 2: Stdio Transport (Traditional MCP)

For stdio-based transport (more complex setup):

#### Windows
```powershell
# PowerShell (recommended)
.\start_win.ps1

# OR Command Prompt
start_win.bat
```

#### Linux
```bash
./start_linux.sh
```

#### macOS
```bash
./start_mac.sh
```

**Cursor Configuration (Stdio):**
```json
{
  "mcpServers": {
    "agent-coordinator": {
      "command": "C:\\path\\to\\cursor-agent-coordinator-mcp\\.venv\\Scripts\\python.exe",
      "args": ["server.py"],
      "cwd": "C:\\path\\to\\cursor-agent-coordinator-mcp"
    }
  }
}
```

## Core Concepts

### Projects
- Identified by unique names (typically the project root directory name)
- Contain multiple tasks
- Generally remain in "in_progress" status indefinitely
- One project per codebase/repository

### Tasks
- Groups of related todo items (similar to sprints in Agile)
- Have execution order and can depend on other tasks
- Contain an overarching goal in their description
- Must be completed in order if dependencies exist

### Todo Items
- Individual units of work handled by single agents
- Have execution order within their parent task
- Can depend on other todo items
- Reference specific files they will modify
- Automatically lock referenced files when in progress

### File Locking
- Files are automatically locked when a todo item using them is marked as "in_progress"
- Other agents cannot modify locked files
- Locks are automatically released when todo items are completed or cancelled
- Prevents merge conflicts and race conditions

## Agent Workflow

### For New Projects

1. **Get Instructions**
   ```
   Tool: get_instructions
   ```

2. **Check for Existing Project**
   ```
   Tool: get_project
   Arguments: { "name": "project-directory-name" }
   ```

3. **Create Project** (if none exists)
   ```
   Tool: create_project
   Arguments: {
     "name": "project-directory-name",
     "description": "Project description"
   }
   ```

4. **Create Tasks**
   ```
   Tool: create_task
   Arguments: {
     "project_name": "project-directory-name",
     "name": "Task name",
     "description": "Overall goal for this task",
     "order": 0,
     "dependencies": []
   }
   ```

5. **Create Todo Items**
   ```
   Tool: create_todo_item
   Arguments: {
     "task_id": 1,
     "title": "Implement feature X",
     "description": "Detailed description",
     "order": 0,
     "dependencies": [],
     "files": ["src/main.py", "src/utils.py"]
   }
   ```

### For Existing Projects

1. **Get Instructions** (always start here)
2. **Get Project Status**
   ```
   Tool: get_project_status
   Arguments: { "project_name": "project-directory-name" }
   ```

3. **Get Next Available Work**
   ```
   Tool: get_next_todo_item
   Arguments: {
     "project_name": "project-directory-name",
     "agent_id": "agent-unique-id"
   }
   ```

4. **Update Status to In Progress**
   ```
   Tool: update_todo_status
   Arguments: {
     "todo_id": 1,
     "status": "in_progress",
     "agent_id": "agent-unique-id"
   }
   ```

5. **Complete Work and Update Status**
   ```
   Tool: update_todo_status
   Arguments: {
     "todo_id": 1,
     "status": "completed",
     "agent_id": "agent-unique-id"
   }
   ```

## Available Tools

### Information & Instructions
- `get_instructions` - Get comprehensive system documentation
- `get_project` - Get project details by name
- `get_project_status` - Get full project status with all tasks and todos

### Project Management
- `create_project` - Create a new project
- `create_task` - Create a task within a project
- `create_todo_item` - Create a todo item within a task
- `insert_todo_item` - Insert a todo at a specific position

### Work Assignment
- `get_next_todo_item` - Get next available work for an agent
- `update_todo_status` - Update todo item status (pending/in_progress/completed/cancelled)

### File Management
- `check_file_locks` - Check if files are locked before modifying
- `lock_files` - Manually lock files (usually automatic)
- `unlock_files` - Manually unlock files (usually automatic)

## Best Practices

1. **Granular Todo Items**: Create todo items that focus on specific files to minimize conflicts
2. **Clear Dependencies**: Define dependencies to ensure proper execution order
3. **Status Updates**: Always update status when starting and completing work
4. **File Checking**: Check file locks before attempting modifications
5. **Descriptive Content**: Provide clear descriptions for tasks and todos
6. **Atomic Work Units**: Keep todo items small enough for single agents to complete

## Example Multi-Agent Scenario

```python
# Agent 1: Creates the project structure
1. create_project("my-app", "Web application with user authentication")
2. create_task("my-app", "Setup Infrastructure", "Create basic project structure", 0, [])
3. create_todo_item(1, "Create directory structure", "", 0, [], ["README.md", "package.json"])
4. get_next_todo_item("my-app", "agent-1")
5. update_todo_status(1, "in_progress", "agent-1")
# ... does work ...
6. update_todo_status(1, "completed", "agent-1")

# Agent 2: Joins and gets assigned work
1. get_instructions()
2. get_project_status("my-app")
3. get_next_todo_item("my-app", "agent-2")
# Gets assigned different todo item with no file conflicts
4. update_todo_status(2, "in_progress", "agent-2")
# ... works in parallel ...
```

## Configuration for Clients

### Claude Desktop

Add to your Claude Desktop configuration:

```json
{
  "mcpServers": {
    "agent-coordinator": {
      "command": "python",
      "args": ["path/to/server.py"],
      "cwd": "path/to/project"
    }
  }
}
```

### Other MCP Clients

Refer to your client's documentation for connecting to stdio-based MCP servers.

## Troubleshooting

### Common Issues

1. **"Project already exists"** - Use `get_project` instead of `create_project`
2. **"No available todo items"** - Check dependencies and file locks
3. **"File is locked"** - Another agent is working on a todo item using that file
4. **"Task not found"** - Verify task ID with `get_project_status`

### Debug Commands

- Check all file locks: `check_file_locks` with list of file paths
- View complete project state: `get_project_status`
- See system instructions: `get_instructions`

## Architecture

The system uses:
- SQLite database for persistent storage
- MCP protocol for agent communication
- Automatic transaction management
- Row-level locking for concurrent access
- Views for efficient status queries

## Contributing

This is a coordination system for autonomous agents. Improvements should focus on:
- Better dependency resolution algorithms
- More intelligent work assignment
- Enhanced conflict prevention
- Performance optimizations for large projects

## License

[Specify your license here] 