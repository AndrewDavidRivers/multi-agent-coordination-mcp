#!/usr/bin/env python3
"""
Fixed Stdio MCP Server for Coordinating Multiple Parallel Agents
"""

import asyncio
import json
import sqlite3
import logging
import sys
from datetime import datetime
from typing import List, Dict, Optional, Any
from contextlib import contextmanager

# Add current directory to path
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.server.session import ServerSession
from mcp.server.models import InitializationOptions
from mcp.types import (
    Tool,
    TextContent,
    ServerCapabilities,
)

from models import Project, Task, TodoItem, File, Status

# Configure logging to stderr
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
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

# Create the MCP server
server = Server("agent-coordinator-mcp")

@server.list_tools()
async def handle_list_tools() -> List[Tool]:
    """List all available tools for agent coordination"""
    return [
        Tool(
            name="get_instructions",
            description="Get comprehensive instructions on how to use the agent coordination system",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="create_project",
            description="Create a new project. Projects are identified by unique names.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Unique project name"},
                    "description": {"type": "string", "description": "Project description"}
                },
                "required": ["name", "description"]
            }
        ),
        Tool(
            name="get_project",
            description="Get project details by name",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Project name"}
                },
                "required": ["name"]
            }
        ),
        Tool(
            name="create_task",
            description="Create a new task within a project",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_name": {"type": "string", "description": "Name of the project"},
                    "name": {"type": "string", "description": "Task name"},
                    "description": {"type": "string", "description": "Task description"},
                    "order": {"type": "integer", "description": "Execution order", "default": 0},
                    "dependencies": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of task IDs that must be completed first"
                    }
                },
                "required": ["project_name", "name", "description"]
            }
        ),
        Tool(
            name="create_todo_item",
            description="Create a new todo item within a task",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer", "description": "ID of the parent task"},
                    "title": {"type": "string", "description": "Todo item title"},
                    "description": {"type": "string", "description": "Detailed description"},
                    "order": {"type": "integer", "description": "Execution order", "default": 0},
                    "dependencies": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of todo item IDs that must be completed first"
                    },
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of file paths that will be modified"
                    }
                },
                "required": ["task_id", "title"]
            }
        ),
        Tool(
            name="get_next_todo_item",
            description="Get the next available todo item that can be worked on",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_name": {"type": "string", "description": "Name of the project"},
                    "agent_id": {"type": "string", "description": "Unique identifier for the agent"}
                },
                "required": ["project_name", "agent_id"]
            }
        ),
        Tool(
            name="update_todo_status",
            description="Update the status of a todo item",
            inputSchema={
                "type": "object",
                "properties": {
                    "todo_id": {"type": "integer", "description": "ID of the todo item"},
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "completed", "cancelled"],
                        "description": "New status"
                    },
                    "agent_id": {"type": "string", "description": "ID of the agent making the update"}
                },
                "required": ["todo_id", "status", "agent_id"]
            }
        ),
        Tool(
            name="check_file_locks",
            description="Check if files are locked before modifying them",
            inputSchema={
                "type": "object",
                "properties": {
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of file paths to check"
                    }
                },
                "required": ["files"]
            }
        ),
        Tool(
            name="lock_files",
            description="Lock files for exclusive modification",
            inputSchema={
                "type": "object",
                "properties": {
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of file paths to lock"
                    },
                    "agent_id": {"type": "string", "description": "ID of the agent locking the files"}
                },
                "required": ["files", "agent_id"]
            }
        ),
        Tool(
            name="unlock_files",
            description="Unlock files after modification",
            inputSchema={
                "type": "object",
                "properties": {
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of file paths to unlock"
                    },
                    "agent_id": {"type": "string", "description": "ID of the agent unlocking the files"}
                },
                "required": ["files", "agent_id"]
            }
        ),
        Tool(
            name="get_project_status",
            description="Get comprehensive status of a project including all tasks and todo items",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_name": {"type": "string", "description": "Name of the project"}
                },
                "required": ["project_name"]
            }
        ),
        Tool(
            name="insert_todo_item",
            description="Insert a new todo item at a specific position in the order",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer", "description": "ID of the parent task"},
                    "title": {"type": "string", "description": "Todo item title"},
                    "description": {"type": "string", "description": "Detailed description"},
                    "after_todo_id": {"type": "integer", "description": "Insert after this todo item ID"},
                    "dependencies": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of todo item IDs that must be completed first"
                    },
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of file paths that will be modified"
                    }
                },
                "required": ["task_id", "title"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle tool calls from agents"""
    
    try:
        if name == "get_instructions":
            return [TextContent(type="text", text=get_instructions())]
        
        elif name == "create_project":
            result = create_project(arguments['name'], arguments['description'])
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        
        elif name == "get_project":
            result = get_project(arguments['name'])
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        
        elif name == "create_task":
            result = create_task(
                arguments['project_name'],
                arguments['name'],
                arguments['description'],
                arguments.get('order', 0),
                arguments.get('dependencies', [])
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        
        elif name == "create_todo_item":
            result = create_todo_item(
                arguments['task_id'],
                arguments['title'],
                arguments.get('description', ''),
                arguments.get('order', 0),
                arguments.get('dependencies', []),
                arguments.get('files', [])
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        
        elif name == "get_next_todo_item":
            result = get_next_todo_item(arguments['project_name'], arguments['agent_id'])
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        
        elif name == "update_todo_status":
            result = update_todo_status(arguments['todo_id'], arguments['status'], arguments['agent_id'])
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        
        elif name == "check_file_locks":
            result = check_file_locks(arguments['files'])
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        
        elif name == "lock_files":
            result = lock_files(arguments['files'], arguments['agent_id'])
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        
        elif name == "unlock_files":
            result = unlock_files(arguments['files'], arguments['agent_id'])
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        
        elif name == "get_project_status":
            result = get_project_status(arguments['project_name'])
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        
        elif name == "insert_todo_item":
            result = insert_todo_item(
                arguments['task_id'],
                arguments['title'],
                arguments.get('description', ''),
                arguments.get('after_todo_id'),
                arguments.get('dependencies', []),
                arguments.get('files', [])
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        
        else:
            return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]
            
    except Exception as e:
        logger.error(f"Error in tool {name}: {e}")
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

# Tool implementation functions
def get_instructions() -> str:
    return """
# Agent Coordination System Instructions

This MCP server helps coordinate multiple autonomous agents working on the same project.

## Available Tools:
1. get_instructions - Get these instructions
2. create_project - Create a new project
3. get_project - Get project details
4. create_task - Create a task within a project
5. create_todo_item - Create a todo item within a task
6. get_next_todo_item - Get next available work for an agent
7. update_todo_status - Update todo item status
8. check_file_locks - Check if files are locked
9. lock_files - Lock files for exclusive access
10. unlock_files - Release file locks
11. get_project_status - Get comprehensive project status
12. insert_todo_item - Insert todo item at specific position

## Workflow:
1. Create project: create_project(name="my-app", description="...")
2. Create tasks: create_task(project_name="my-app", name="Auth", description="...")
3. Create todos: create_todo_item(task_id=1, title="Login form", files=["login.tsx"])
4. Agents get work: get_next_todo_item(project_name="my-app", agent_id="agent-1")
5. Lock files: lock_files(files=["login.tsx"], agent_id="agent-1")
6. Update status: update_todo_status(todo_id=1, status="completed", agent_id="agent-1")
7. Unlock files: unlock_files(files=["login.tsx"], agent_id="agent-1")

All tools return JSON responses with results or error messages.
"""

def create_project(name: str, description: str) -> dict:
    with get_db() as conn:
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO projects (name, description, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (name, description, Status.PENDING.value, datetime.now(), datetime.now())
            )
            project_id = cursor.lastrowid
            cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
            row = cursor.fetchone()
            return dict(row)
        except sqlite3.IntegrityError:
            return {"error": f"Project '{name}' already exists"}

def get_project(name: str) -> dict:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM projects WHERE name = ?", (name,))
        row = cursor.fetchone()
        if not row:
            return {"error": f"Project '{name}' not found"}
        return dict(row)

def create_task(project_name: str, name: str, description: str, order: int = 0, dependencies: List[int] = None) -> dict:
    if dependencies is None:
        dependencies = []
        
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM projects WHERE name = ?", (project_name,))
        project_row = cursor.fetchone()
        if not project_row:
            return {"error": f"Project '{project_name}' not found"}
        
        project_id = project_row["id"]
        cursor.execute(
            "INSERT INTO tasks (project_id, name, description, order_index, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (project_id, name, description, order, Status.PENDING.value, datetime.now(), datetime.now())
        )
        task_id = cursor.lastrowid
        
        for dep_id in dependencies:
            cursor.execute(
                "INSERT INTO task_dependencies (task_id, depends_on_task_id) VALUES (?, ?)",
                (task_id, dep_id)
            )
        
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        result = dict(row)
        result["dependencies"] = dependencies
        return result

def create_todo_item(task_id: int, title: str, description: str = "", order: int = 0, dependencies: List[int] = None, files: List[str] = None) -> dict:
    if dependencies is None:
        dependencies = []
    if files is None:
        files = []
        
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        if not cursor.fetchone():
            return {"error": f"Task with ID {task_id} not found"}
        
        cursor.execute(
            "INSERT INTO todo_items (task_id, title, description, order_index, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (task_id, title, description, order, Status.PENDING.value, datetime.now(), datetime.now())
        )
        todo_id = cursor.lastrowid
        
        for dep_id in dependencies:
            cursor.execute(
                "INSERT INTO todo_dependencies (todo_id, depends_on_todo_id) VALUES (?, ?)",
                (todo_id, dep_id)
            )
        
        for file_path in files:
            cursor.execute(
                "INSERT INTO todo_files (todo_id, file_path) VALUES (?, ?)",
                (todo_id, file_path)
            )
        
        cursor.execute("SELECT * FROM todo_items WHERE id = ?", (todo_id,))
        row = cursor.fetchone()
        result = dict(row)
        result["dependencies"] = dependencies
        result["files"] = files
        return result

def get_next_todo_item(project_name: str, agent_id: str) -> dict:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM projects WHERE name = ?", (project_name,))
        project_row = cursor.fetchone()
        if not project_row:
            return {"error": f"Project '{project_name}' not found"}
        
        project_id = project_row["id"]
        
        # Find available todo items
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
        ORDER BY task.order_index, t.order_index
        LIMIT 1
        """
        
        cursor.execute(query, (project_id,))
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
        
        result = dict(row)
        result["status"] = "in_progress"
        result["assigned_agent"] = agent_id
        result["files"] = files
        return result

def update_todo_status(todo_id: int, status: str, agent_id: str) -> dict:
    valid_statuses = ["pending", "in_progress", "completed", "cancelled"]
    if status not in valid_statuses:
        return {"error": f"Invalid status. Must be one of: {valid_statuses}"}
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM todo_items WHERE id = ?", (todo_id,))
        row = cursor.fetchone()
        if not row:
            return {"error": f"Todo item with ID {todo_id} not found"}
        
        if row["assigned_agent"] and row["assigned_agent"] != agent_id:
            return {"error": f"Todo item is assigned to different agent: {row['assigned_agent']}"}
        
        assigned_agent = agent_id if status == "in_progress" else None
        if status in ["completed", "cancelled"]:
            assigned_agent = None
        
        cursor.execute(
            "UPDATE todo_items SET status = ?, assigned_agent = ?, updated_at = ? WHERE id = ?",
            (status, assigned_agent, datetime.now(), todo_id)
        )
        
        return {
            "id": todo_id,
            "status": status,
            "assigned_agent": assigned_agent,
            "updated_at": str(datetime.now())
        }

def check_file_locks(files: List[str]) -> dict:
    with get_db() as conn:
        cursor = conn.cursor()
        locked_files = {}
        for file_path in files:
            cursor.execute("SELECT * FROM file_locks WHERE file_path = ?", (file_path,))
            row = cursor.fetchone()
            if row:
                locked_files[file_path] = dict(row)
        
        return {
            "checked_files": files,
            "locked_files": locked_files,
            "all_available": len(locked_files) == 0
        }

def lock_files(files: List[str], agent_id: str) -> dict:
    with get_db() as conn:
        cursor = conn.cursor()
        locked_by_others = []
        for file_path in files:
            cursor.execute("SELECT locked_by FROM file_locks WHERE file_path = ? AND locked_by != ?", (file_path, agent_id))
            if cursor.fetchone():
                locked_by_others.append(file_path)
        
        if locked_by_others:
            return {"error": f"Files already locked by another agent: {locked_by_others}"}
        
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

def unlock_files(files: List[str], agent_id: str) -> dict:
    with get_db() as conn:
        cursor = conn.cursor()
        unlocked_files = []
        not_owned = []
        
        for file_path in files:
            cursor.execute("SELECT locked_by FROM file_locks WHERE file_path = ?", (file_path,))
            row = cursor.fetchone()
            
            if not row:
                continue
            elif row["locked_by"] == agent_id:
                cursor.execute("DELETE FROM file_locks WHERE file_path = ?", (file_path,))
                unlocked_files.append(file_path)
            else:
                not_owned.append(file_path)
        
        result = {"unlocked_files": unlocked_files, "agent_id": agent_id}
        if not_owned:
            result["error"] = f"Cannot unlock files not owned by agent: {not_owned}"
        
        return result

def get_project_status(project_name: str) -> dict:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM projects WHERE name = ?", (project_name,))
        project_row = cursor.fetchone()
        if not project_row:
            return {"error": f"Project '{project_name}' not found"}
        
        project_id = project_row["id"]
        
        # Get tasks and todos
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
        
        tasks = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("""
            SELECT COUNT(*) as total_todos,
                   COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_todos,
                   COUNT(CASE WHEN status = 'in_progress' THEN 1 END) as in_progress_todos,
                   COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending_todos
            FROM todo_items ti
            JOIN tasks t ON ti.task_id = t.id
            WHERE t.project_id = ?
        """, (project_id,))
        
        stats = dict(cursor.fetchone())
        completion_pct = round((stats["completed_todos"] / max(stats["total_todos"], 1)) * 100, 1)
        
        return {
            "project": dict(project_row),
            "tasks": tasks,
            "overall_stats": {**stats, "completion_percentage": completion_pct}
        }

def insert_todo_item(task_id: int, title: str, description: str = "", after_todo_id: Optional[int] = None, dependencies: List[int] = None, files: List[str] = None) -> dict:
    if dependencies is None:
        dependencies = []
    if files is None:
        files = []
        
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        if not cursor.fetchone():
            return {"error": f"Task with ID {task_id} not found"}
        
        if after_todo_id:
            cursor.execute("SELECT order_index FROM todo_items WHERE id = ?", (after_todo_id,))
            row = cursor.fetchone()
            if not row:
                return {"error": f"Todo item with ID {after_todo_id} not found"}
            order_index = row["order_index"] + 1
            cursor.execute(
                "UPDATE todo_items SET order_index = order_index + 1 WHERE task_id = ? AND order_index >= ?",
                (task_id, order_index)
            )
        else:
            order_index = 0
            cursor.execute(
                "UPDATE todo_items SET order_index = order_index + 1 WHERE task_id = ?",
                (task_id,)
            )
        
        cursor.execute(
            "INSERT INTO todo_items (task_id, title, description, order_index, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (task_id, title, description, order_index, Status.PENDING.value, datetime.now(), datetime.now())
        )
        todo_id = cursor.lastrowid
        
        for dep_id in dependencies:
            cursor.execute(
                "INSERT INTO todo_dependencies (todo_id, depends_on_todo_id) VALUES (?, ?)",
                (todo_id, dep_id)
            )
        
        for file_path in files:
            cursor.execute(
                "INSERT INTO todo_files (todo_id, file_path) VALUES (?, ?)",
                (todo_id, file_path)
            )
        
        cursor.execute("SELECT * FROM todo_items WHERE id = ?", (todo_id,))
        row = cursor.fetchone()
        result = dict(row)
        result["dependencies"] = dependencies
        result["files"] = files
        return result

async def main():
    """Main entry point"""
    logger.info("Starting Agent Coordinator MCP Server (stdio)")
    
    async with stdio_server() as (read_stream, write_stream):
        async with ServerSession(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="agent-coordinator-mcp",
                server_version="1.0.0",
                capabilities=ServerCapabilities()
            )
        ) as session:
            await session.run()

if __name__ == "__main__":
    asyncio.run(main()) 