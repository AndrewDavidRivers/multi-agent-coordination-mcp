#!/usr/bin/env python3
"""
HTTP MCP Server for Coordinating Multiple Parallel Agents
This server runs on localhost:8000 for easy integration with Cursor
"""

import asyncio
import json
import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any
from contextlib import contextmanager

from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent
import uvicorn

from models import Project, Task, TodoItem, File, Status

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database connection manager
@contextmanager
def get_db():
    conn = sqlite3.connect('db.sqlite')
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# Create FastMCP server
mcp = FastMCP("Agent Coordinator MCP Server")

@mcp.tool()
def get_instructions() -> str:
    """Get comprehensive instructions on how to use the agent coordination system"""
    return """
# Agent Coordination System Instructions

This MCP server helps coordinate multiple autonomous agents working on the same project by managing:

## Core Concepts

### Projects
- Identified by unique names (typically the project root directory name)
- Container for all related tasks and todos
- Track overall project status and progress

### Tasks
- Groups of related todo items (similar to sprints or milestones)
- Have execution order and dependencies
- Can depend on completion of other tasks

### Todo Items
- Individual actionable items within tasks
- Can have file dependencies and locks
- Support execution order and dependencies on other todos
- Assigned to specific agents for execution

### File Locking
- Prevents conflicts when multiple agents modify the same files
- Automatic lock/unlock when working on todos
- Check locks before starting work

## Typical Workflow

1. **Project Setup**
   ```
   create_project(name="my-app", description="React application")
   ```

2. **Task Creation**
   ```
   create_task(project_name="my-app", name="Authentication", description="Implement user auth")
   create_task(project_name="my-app", name="UI Components", description="Build reusable components")
   ```

3. **Todo Management**
   ```
   create_todo_item(task_id=1, title="Create login form", files=["src/LoginForm.tsx"])
   create_todo_item(task_id=1, title="Add auth middleware", files=["src/middleware/auth.ts"])
   ```

4. **Agent Coordination**
   ```
   # Agent requests work
   get_next_todo_item(project_name="my-app", agent_id="agent-1")
   
   # Agent locks files before work
   lock_files(files=["src/LoginForm.tsx"], agent_id="agent-1")
   
   # Agent updates status
   update_todo_status(todo_id=1, status="completed", agent_id="agent-1")
   
   # Agent unlocks files after work
   unlock_files(files=["src/LoginForm.tsx"], agent_id="agent-1")
   ```

5. **Progress Tracking**
   ```
   get_project_status(project_name="my-app")
   ```

## Best Practices

- Always check file locks before modifying files
- Update todo status as work progresses
- Use descriptive names for projects, tasks, and todos
- Set proper dependencies to ensure correct execution order
- Lock only the files you need and unlock them promptly

Use the available tools to implement this workflow in your autonomous agent system.
"""

@mcp.tool()
def create_project(name: str, description: str) -> dict:
    """Create a new project. Projects are identified by unique names."""
    with get_db() as conn:
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO projects (name, description, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (name, description, Status.PENDING.value, datetime.now(), datetime.now())
            )
            project_id = cursor.lastrowid
            
            # Fetch the created project
            cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
            row = cursor.fetchone()
            
            return {
                "id": row["id"],
                "name": row["name"],
                "description": row["description"],
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"]
            }
        except sqlite3.IntegrityError:
            return {"error": f"Project '{name}' already exists"}

@mcp.tool()
def get_project(name: str) -> dict:
    """Get project details by name"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM projects WHERE name = ?", (name,))
        row = cursor.fetchone()
        
        if not row:
            return {"error": f"Project '{name}' not found"}
        
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"]
        }

@mcp.tool()
def create_task(project_name: str, name: str, description: str, order: int = 0, dependencies: List[int] = None) -> dict:
    """Create a new task within a project"""
    if dependencies is None:
        dependencies = []
        
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Get project ID
        cursor.execute("SELECT id FROM projects WHERE name = ?", (project_name,))
        project_row = cursor.fetchone()
        if not project_row:
            return {"error": f"Project '{project_name}' not found"}
        
        project_id = project_row["id"]
        
        # Create task
        cursor.execute(
            "INSERT INTO tasks (project_id, name, description, order_index, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (project_id, name, description, order, Status.PENDING.value, datetime.now(), datetime.now())
        )
        task_id = cursor.lastrowid
        
        # Add dependencies
        for dep_id in dependencies:
            cursor.execute(
                "INSERT INTO task_dependencies (task_id, depends_on_task_id) VALUES (?, ?)",
                (task_id, dep_id)
            )
        
        # Fetch the created task
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "name": row["name"],
            "description": row["description"],
            "order_index": row["order_index"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "dependencies": dependencies
        }

@mcp.tool()
def create_todo_item(task_id: int, title: str, description: str = "", order: int = 0, dependencies: List[int] = None, files: List[str] = None) -> dict:
    """Create a new todo item within a task"""
    if dependencies is None:
        dependencies = []
    if files is None:
        files = []
        
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Verify task exists
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        if not cursor.fetchone():
            return {"error": f"Task with ID {task_id} not found"}
        
        # Create todo item
        cursor.execute(
            "INSERT INTO todo_items (task_id, title, description, order_index, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (task_id, title, description, order, Status.PENDING.value, datetime.now(), datetime.now())
        )
        todo_id = cursor.lastrowid
        
        # Add dependencies
        for dep_id in dependencies:
            cursor.execute(
                "INSERT INTO todo_dependencies (todo_id, depends_on_todo_id) VALUES (?, ?)",
                (todo_id, dep_id)
            )
        
        # Add file associations
        for file_path in files:
            cursor.execute(
                "INSERT INTO todo_files (todo_id, file_path) VALUES (?, ?)",
                (todo_id, file_path)
            )
        
        # Fetch the created todo
        cursor.execute("SELECT * FROM todo_items WHERE id = ?", (todo_id,))
        row = cursor.fetchone()
        
        return {
            "id": row["id"],
            "task_id": row["task_id"],
            "title": row["title"],
            "description": row["description"],
            "order_index": row["order_index"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "dependencies": dependencies,
            "files": files
        }

@mcp.tool()
def get_next_todo_item(project_name: str, agent_id: str) -> dict:
    """Get the next available todo item that can be worked on"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Get project ID
        cursor.execute("SELECT id FROM projects WHERE name = ?", (project_name,))
        project_row = cursor.fetchone()
        if not project_row:
            return {"error": f"Project '{project_name}' not found"}
        
        project_id = project_row["id"]
        
        # Find available todo items (no incomplete dependencies, not locked)
        query = """
        SELECT DISTINCT t.* FROM todo_items t
        JOIN tasks task ON t.task_id = task.id
        WHERE task.project_id = ? 
        AND t.status = 'pending'
        AND t.assigned_agent IS NULL
        AND NOT EXISTS (
            SELECT 1 FROM todo_dependencies td 
            JOIN todo_items dep ON td.depends_on_todo_id = dep.id 
            WHERE td.todo_id = t.id AND dep.status != 'completed'
        )
        AND NOT EXISTS (
            SELECT 1 FROM todo_files tf
            JOIN file_locks fl ON tf.file_path = fl.file_path
            WHERE tf.todo_id = t.id AND fl.locked_by != ?
        )
        ORDER BY task.order_index, t.order_index
        LIMIT 1
        """
        
        cursor.execute(query, (project_id, agent_id))
        row = cursor.fetchone()
        
        if not row:
            return {"message": "No available todo items"}
        
        # Assign to agent
        cursor.execute(
            "UPDATE todo_items SET assigned_agent = ?, status = 'in_progress', updated_at = ? WHERE id = ?",
            (agent_id, datetime.now(), row["id"])
        )
        
        # Get associated files
        cursor.execute("SELECT file_path FROM todo_files WHERE todo_id = ?", (row["id"],))
        files = [f["file_path"] for f in cursor.fetchall()]
        
        return {
            "id": row["id"],
            "task_id": row["task_id"],
            "title": row["title"],
            "description": row["description"],
            "order_index": row["order_index"],
            "status": "in_progress",
            "assigned_agent": agent_id,
            "files": files
        }

@mcp.tool()
def update_todo_status(todo_id: int, status: str, agent_id: str) -> dict:
    """Update the status of a todo item"""
    valid_statuses = ["pending", "in_progress", "completed", "cancelled"]
    if status not in valid_statuses:
        return {"error": f"Invalid status. Must be one of: {valid_statuses}"}
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Verify todo exists and agent owns it (or is completing it)
        cursor.execute("SELECT * FROM todo_items WHERE id = ?", (todo_id,))
        row = cursor.fetchone()
        if not row:
            return {"error": f"Todo item with ID {todo_id} not found"}
        
        if row["assigned_agent"] and row["assigned_agent"] != agent_id:
            return {"error": f"Todo item is assigned to different agent: {row['assigned_agent']}"}
        
        # Update status
        update_fields = {"status": status, "updated_at": datetime.now()}
        if status == "in_progress":
            update_fields["assigned_agent"] = agent_id
        elif status in ["completed", "cancelled"]:
            update_fields["assigned_agent"] = None
        
        cursor.execute(
            "UPDATE todo_items SET status = ?, assigned_agent = ?, updated_at = ? WHERE id = ?",
            (status, update_fields.get("assigned_agent"), update_fields["updated_at"], todo_id)
        )
        
        return {
            "id": todo_id,
            "status": status,
            "assigned_agent": update_fields.get("assigned_agent"),
            "updated_at": str(update_fields["updated_at"])
        }

@mcp.tool()
def check_file_locks(files: List[str]) -> dict:
    """Check if files are locked before modifying them"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        locked_files = {}
        for file_path in files:
            cursor.execute("SELECT * FROM file_locks WHERE file_path = ?", (file_path,))
            row = cursor.fetchone()
            if row:
                locked_files[file_path] = {
                    "locked_by": row["locked_by"],
                    "locked_at": row["locked_at"]
                }
        
        return {
            "checked_files": files,
            "locked_files": locked_files,
            "all_available": len(locked_files) == 0
        }

@mcp.tool()
def lock_files(files: List[str], agent_id: str) -> dict:
    """Lock files for exclusive modification"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Check if any files are already locked
        locked_by_others = []
        for file_path in files:
            cursor.execute("SELECT locked_by FROM file_locks WHERE file_path = ? AND locked_by != ?", (file_path, agent_id))
            if cursor.fetchone():
                locked_by_others.append(file_path)
        
        if locked_by_others:
            return {"error": f"Files already locked by another agent: {locked_by_others}"}
        
        # Lock all files
        for file_path in files:
            cursor.execute(
                "INSERT OR REPLACE INTO file_locks (file_path, locked_by, locked_at) VALUES (?, ?, ?)",
                (file_path, agent_id, datetime.now())
            )
        
        return {
            "locked_files": files,
            "locked_by": agent_id,
            "locked_at": str(datetime.now())
        }

@mcp.tool()
def unlock_files(files: List[str], agent_id: str) -> dict:
    """Unlock files after modification"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Check ownership and unlock
        unlocked_files = []
        not_owned = []
        
        for file_path in files:
            cursor.execute("SELECT locked_by FROM file_locks WHERE file_path = ?", (file_path,))
            row = cursor.fetchone()
            
            if not row:
                continue  # File wasn't locked
            elif row["locked_by"] == agent_id:
                cursor.execute("DELETE FROM file_locks WHERE file_path = ?", (file_path,))
                unlocked_files.append(file_path)
            else:
                not_owned.append(file_path)
        
        result = {
            "unlocked_files": unlocked_files,
            "agent_id": agent_id
        }
        
        if not_owned:
            result["error"] = f"Cannot unlock files not owned by agent: {not_owned}"
        
        return result

@mcp.tool()
def get_project_status(project_name: str) -> dict:
    """Get comprehensive status of a project including all tasks and todo items"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Get project
        cursor.execute("SELECT * FROM projects WHERE name = ?", (project_name,))
        project_row = cursor.fetchone()
        if not project_row:
            return {"error": f"Project '{project_name}' not found"}
        
        project_id = project_row["id"]
        
        # Get tasks and their todos
        cursor.execute("""
            SELECT t.*, 
                   COUNT(ti.id) as total_todos,
                   COUNT(CASE WHEN ti.status = 'completed' THEN 1 END) as completed_todos,
                   COUNT(CASE WHEN ti.status = 'in_progress' THEN 1 END) as in_progress_todos,
                   COUNT(CASE WHEN ti.status = 'pending' THEN 1 END) as pending_todos
            FROM tasks t
            LEFT JOIN todo_items ti ON t.id = ti.task_id
            WHERE t.project_id = ?
            GROUP BY t.id
            ORDER BY t.order_index
        """, (project_id,))
        
        tasks = []
        for task_row in cursor.fetchall():
            tasks.append({
                "id": task_row["id"],
                "name": task_row["name"],
                "description": task_row["description"],
                "status": task_row["status"],
                "order_index": task_row["order_index"],
                "todo_summary": {
                    "total": task_row["total_todos"],
                    "completed": task_row["completed_todos"],
                    "in_progress": task_row["in_progress_todos"],
                    "pending": task_row["pending_todos"]
                }
            })
        
        # Overall project stats
        cursor.execute("""
            SELECT COUNT(*) as total_todos,
                   COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_todos,
                   COUNT(CASE WHEN status = 'in_progress' THEN 1 END) as in_progress_todos,
                   COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending_todos
            FROM todo_items ti
            JOIN tasks t ON ti.task_id = t.id
            WHERE t.project_id = ?
        """, (project_id,))
        
        stats = cursor.fetchone()
        
        return {
            "project": {
                "id": project_row["id"],
                "name": project_row["name"],
                "description": project_row["description"],
                "status": project_row["status"],
                "created_at": project_row["created_at"],
                "updated_at": project_row["updated_at"]
            },
            "tasks": tasks,
            "overall_stats": {
                "total_todos": stats["total_todos"],
                "completed_todos": stats["completed_todos"],
                "in_progress_todos": stats["in_progress_todos"],
                "pending_todos": stats["pending_todos"],
                "completion_percentage": round((stats["completed_todos"] / max(stats["total_todos"], 1)) * 100, 1)
            }
        }

@mcp.tool()
def insert_todo_item(task_id: int, title: str, description: str = "", after_todo_id: Optional[int] = None, dependencies: List[int] = None, files: List[str] = None) -> dict:
    """Insert a new todo item at a specific position in the order"""
    if dependencies is None:
        dependencies = []
    if files is None:
        files = []
        
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Verify task exists
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        if not cursor.fetchone():
            return {"error": f"Task with ID {task_id} not found"}
        
        # Determine order index
        if after_todo_id:
            cursor.execute("SELECT order_index FROM todo_items WHERE id = ?", (after_todo_id,))
            row = cursor.fetchone()
            if not row:
                return {"error": f"Todo item with ID {after_todo_id} not found"}
            order_index = row["order_index"] + 1
            
            # Shift subsequent items
            cursor.execute(
                "UPDATE todo_items SET order_index = order_index + 1 WHERE task_id = ? AND order_index >= ?",
                (task_id, order_index)
            )
        else:
            order_index = 0
            # Shift all items in task
            cursor.execute(
                "UPDATE todo_items SET order_index = order_index + 1 WHERE task_id = ?",
                (task_id,)
            )
        
        # Create todo item
        cursor.execute(
            "INSERT INTO todo_items (task_id, title, description, order_index, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (task_id, title, description, order_index, Status.PENDING.value, datetime.now(), datetime.now())
        )
        todo_id = cursor.lastrowid
        
        # Add dependencies
        for dep_id in dependencies:
            cursor.execute(
                "INSERT INTO todo_dependencies (todo_id, depends_on_todo_id) VALUES (?, ?)",
                (todo_id, dep_id)
            )
        
        # Add file associations
        for file_path in files:
            cursor.execute(
                "INSERT INTO todo_files (todo_id, file_path) VALUES (?, ?)",
                (todo_id, file_path)
            )
        
        # Fetch the created todo
        cursor.execute("SELECT * FROM todo_items WHERE id = ?", (todo_id,))
        row = cursor.fetchone()
        
        return {
            "id": row["id"],
            "task_id": row["task_id"],
            "title": row["title"],
            "description": row["description"],
            "order_index": row["order_index"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "dependencies": dependencies,
            "files": files
        }

async def main():
    """Run the HTTP MCP server"""
    # Configure uvicorn for the FastMCP app
    config = uvicorn.Config(
        mcp.streamable_http_app(),  # Use the HTTP app from FastMCP
        host="127.0.0.1",
        port=8002,
        log_level="info"
    )
    server = uvicorn.Server(config)
    
    print("🚀 Starting MCP Agent Coordinator on http://127.0.0.1:8001")
    print("🔧 Use this URL in your Cursor MCP configuration")
    print("📡 Available tools: 12 coordination tools")
    
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main()) 