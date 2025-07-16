#!/usr/bin/env python3
"""
MCP Server for Coordinating Multiple Parallel Agents
This server manages projects, tasks, and todo items with dependency tracking
and file locking to coordinate work across multiple autonomous agents.
"""

import asyncio
import json
import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any
from contextlib import contextmanager

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.server.session import ServerSession
from mcp.types import (
    Resource,
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
    Prompt,
    PromptMessage,
    ServerCapabilities,
    PromptArgument,
)

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

class AgentCoordinatorServer:
    def __init__(self):
        self.server = Server("agent-coordinator-mcp")
        self._setup_handlers()
        
    def _setup_handlers(self):
        @self.server.list_resources()
        async def handle_list_resources() -> List[Resource]:
            """List all available projects and their current status"""
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, name, description, status FROM projects")
                projects = cursor.fetchall()
                
                resources = []
                for project in projects:
                    resources.append(Resource(
                        uri=f"project://{project['id']}",
                        name=f"Project: {project['name']}",
                        description=f"{project['description']} (Status: {project['status']})",
                        mimeType="application/json"
                    ))
                return resources
        
        @self.server.read_resource()
        async def handle_read_resource(uri: str) -> str:
            """Read detailed information about a project"""
            if uri.startswith("project://"):
                project_id = int(uri.replace("project://", ""))
                with get_db() as conn:
                    cursor = conn.cursor()
                    
                    # Get project details
                    cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
                    project = cursor.fetchone()
                    
                    if not project:
                        raise ValueError(f"Project {project_id} not found")
                    
                    # Get tasks for this project
                    cursor.execute("""
                        SELECT * FROM tasks 
                        WHERE project_id = ? 
                        ORDER BY "order"
                    """, (project_id,))
                    tasks = cursor.fetchall()
                    
                    # Get todo items for each task
                    project_data = dict(project)
                    project_data['tasks'] = []
                    
                    for task in tasks:
                        task_data = dict(task)
                        cursor.execute("""
                            SELECT ti.*, GROUP_CONCAT(tif.file_id) as file_ids
                            FROM todo_items ti
                            LEFT JOIN todo_item_files tif ON ti.id = tif.todo_item_id
                            WHERE ti.task_id = ?
                            GROUP BY ti.id
                            ORDER BY ti."order"
                        """, (task['id'],))
                        todo_items = cursor.fetchall()
                        
                        task_data['todo_items'] = []
                        for item in todo_items:
                            item_data = dict(item)
                            # Parse dependencies and file IDs
                            item_data['dependencies'] = json.loads(item_data.get('dependencies', '[]'))
                            file_ids = item_data.pop('file_ids', None)
                            item_data['files'] = []
                            
                            if file_ids:
                                cursor.execute("""
                                    SELECT * FROM files WHERE id IN ({})
                                """.format(','.join('?' * len(file_ids.split(',')))), 
                                file_ids.split(','))
                                item_data['files'] = [dict(f) for f in cursor.fetchall()]
                            
                            task_data['todo_items'].append(item_data)
                        
                        project_data['tasks'].append(task_data)
                    
                    return json.dumps(project_data, indent=2)
            
            raise ValueError(f"Unknown resource URI: {uri}")
        
        @self.server.list_tools()
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
                            "name": {"type": "string", "description": "Unique project name (typically the project root directory name)"},
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
                            "description": {"type": "string", "description": "Task description (overarching goal)"},
                            "order": {"type": "integer", "description": "Order in which task should be executed", "default": 0},
                            "dependencies": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": "List of task IDs that must be completed before this task"
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
                            "order": {"type": "integer", "description": "Execution order within the task", "default": 0},
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
                            "after_todo_id": {"type": "integer", "description": "Insert after this todo item ID (null for beginning)"},
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
        
        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            """Handle tool calls from agents"""
            
            if name == "get_instructions":
                return [TextContent(
                    type="text",
                    text=self._get_instructions()
                )]
            
            elif name == "create_project":
                result = self._create_project(arguments['name'], arguments['description'])
                return [TextContent(type="text", text=json.dumps(result))]
            
            elif name == "get_project":
                result = self._get_project(arguments['name'])
                return [TextContent(type="text", text=json.dumps(result))]
            
            elif name == "create_task":
                result = self._create_task(
                    arguments['project_name'],
                    arguments['name'],
                    arguments['description'],
                    arguments.get('order', 0),
                    arguments.get('dependencies', [])
                )
                return [TextContent(type="text", text=json.dumps(result))]
            
            elif name == "create_todo_item":
                result = self._create_todo_item(
                    arguments['task_id'],
                    arguments['title'],
                    arguments.get('description', ''),
                    arguments.get('order', 0),
                    arguments.get('dependencies', []),
                    arguments.get('files', [])
                )
                return [TextContent(type="text", text=json.dumps(result))]
            
            elif name == "get_next_todo_item":
                result = self._get_next_todo_item(
                    arguments['project_name'],
                    arguments['agent_id']
                )
                return [TextContent(type="text", text=json.dumps(result))]
            
            elif name == "update_todo_status":
                result = self._update_todo_status(
                    arguments['todo_id'],
                    arguments['status'],
                    arguments['agent_id']
                )
                return [TextContent(type="text", text=json.dumps(result))]
            
            elif name == "check_file_locks":
                result = self._check_file_locks(arguments['files'])
                return [TextContent(type="text", text=json.dumps(result))]
            
            elif name == "lock_files":
                result = self._lock_files(arguments['files'], arguments['agent_id'])
                return [TextContent(type="text", text=json.dumps(result))]
            
            elif name == "unlock_files":
                result = self._unlock_files(arguments['files'], arguments['agent_id'])
                return [TextContent(type="text", text=json.dumps(result))]
            
            elif name == "get_project_status":
                result = self._get_project_status(arguments['project_name'])
                return [TextContent(type="text", text=json.dumps(result, indent=2))]
            
            elif name == "insert_todo_item":
                result = self._insert_todo_item(
                    arguments['task_id'],
                    arguments['title'],
                    arguments.get('description', ''),
                    arguments.get('after_todo_id'),
                    arguments.get('dependencies', []),
                    arguments.get('files', [])
                )
                return [TextContent(type="text", text=json.dumps(result))]
            
            else:
                raise ValueError(f"Unknown tool: {name}")
        
        @self.server.list_prompts()
        async def handle_list_prompts() -> List[Prompt]:
            """List available prompts"""
            return [
                Prompt(
                    name="agent_onboarding",
                    description="Complete onboarding instructions for new agents",
                    arguments=[]
                ),
                Prompt(
                    name="project_overview",
                    description="Get an overview of a specific project",
                    arguments=[
                        PromptArgument(
                            name="project_name",
                            description="Name of the project to overview",
                            required=True
                        )
                    ]
                )
            ]
        
        @self.server.get_prompt()
        async def handle_get_prompt(name: str, arguments: Optional[Dict[str, str]] = None) -> PromptMessage:
            """Get a specific prompt"""
            if name == "agent_onboarding":
                return PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=self._get_onboarding_prompt()
                    )
                )
            
            elif name == "project_overview":
                if not arguments or 'project_name' not in arguments:
                    raise ValueError("project_name argument is required")
                
                project = self._get_project(arguments['project_name'])
                if not project:
                    return PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=f"Project '{arguments['project_name']}' not found."
                        )
                    )
                
                overview = self._generate_project_overview(project)
                return PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=overview
                    )
                )
            
            else:
                raise ValueError(f"Unknown prompt: {name}")
    
    def _get_instructions(self) -> str:
        """Return comprehensive instructions for agents"""
        return """
# Agent Coordination System Instructions

## Overview
This MCP server coordinates work across multiple autonomous agents working on the same project. It manages projects, tasks, todo items, and file locking to prevent conflicts.

## Core Concepts

### Projects
- Identified by unique names (typically the project root directory name)
- Contain multiple tasks
- Generally remain in "in_progress" status indefinitely

### Tasks
- Groups of related todo items (similar to sprints)
- Have an execution order and can depend on other tasks
- Contain the overarching goal in their description

### Todo Items
- Individual units of work handled by agents
- Have execution order within their task
- Can depend on other todo items
- Reference files they will modify
- Must be marked as in_progress when started and completed when done

### File Locking
- Files referenced by todo items are automatically locked when the item is in_progress
- Other agents must check file locks before modifying files
- Locks are released when todo items are completed

## Workflow

### Starting Fresh
1. Call `get_instructions` to understand the system
2. Call `get_project` with the current project directory name
3. If no project exists, call `create_project`
4. Create initial task(s) with `create_task`
5. Create todo items with `create_todo_item`, specifying:
   - Files that will be modified
   - Dependencies between items
   - Execution order
6. Call `get_next_todo_item` to get work
7. Mark items as in_progress, then completed

### Joining Existing Work
1. Call `get_instructions` to understand the system
2. Call `get_project` to see current state
3. Call `get_next_todo_item` to get available work
4. Check dependencies and locked files
5. Proceed with assigned todo item

### Best Practices
- Plan todo items to minimize file conflicts
- Keep todo items focused on specific files
- Always mark work as in_progress before starting
- Always mark work as completed when done
- Check file locks before modifying any file
- Create detailed descriptions for tasks and todo items
- Use dependencies to enforce proper execution order

### Important Notes
- Agents work asynchronously - always check current state
- File locks prevent conflicts between agents
- Todo items should be granular enough for single agents
- Tasks group related todo items with a common goal
"""
    
    def _get_onboarding_prompt(self) -> str:
        """Return onboarding prompt for new agents"""
        return """
You are joining a multi-agent development team. This project uses an MCP-based coordination system to manage parallel work across multiple agents.

CRITICAL FIRST STEPS:
1. Call the `get_instructions` tool to learn how the coordination system works
2. Identify the current project name (usually the root directory name)
3. Call `get_project` to check if a project already exists
4. If no project exists, you'll need to create one and plan the work
5. If a project exists, review the current tasks and todo items
6. Call `get_next_todo_item` to get your assigned work

IMPORTANT GUIDELINES:
- Always mark todo items as "in_progress" before starting work
- Always mark todo items as "completed" when finished
- Files are automatically locked when you work on a todo item
- Never modify files that are locked by other agents
- Create granular todo items that reference specific files
- Use dependencies to ensure proper execution order
- Communicate status transparently for other agents

Remember: You are part of a team. Coordinate through the system, respect locks, and keep your work status updated.
"""
    
    def _create_project(self, name: str, description: str) -> Dict[str, Any]:
        """Create a new project"""
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Check if project already exists
            cursor.execute("SELECT id FROM projects WHERE name = ?", (name,))
            if cursor.fetchone():
                return {"error": f"Project '{name}' already exists"}
            
            # Create project
            cursor.execute("""
                INSERT INTO projects (name, description, status)
                VALUES (?, ?, 'in_progress')
            """, (name, description))
            
            project_id = cursor.lastrowid
            return {
                "id": project_id,
                "name": name,
                "description": description,
                "status": "in_progress",
                "message": "Project created successfully"
            }
    
    def _get_project(self, name: str) -> Optional[Dict[str, Any]]:
        """Get project by name"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM projects WHERE name = ?", (name,))
            project = cursor.fetchone()
            
            if not project:
                return None
            
            return dict(project)
    
    def _create_task(self, project_name: str, name: str, description: str, 
                     order: int, dependencies: List[int]) -> Dict[str, Any]:
        """Create a new task"""
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Get project ID
            cursor.execute("SELECT id FROM projects WHERE name = ?", (project_name,))
            project = cursor.fetchone()
            if not project:
                return {"error": f"Project '{project_name}' not found"}
            
            project_id = project['id']
            
            # Create task
            cursor.execute("""
                INSERT INTO tasks (name, description, project_id, status, "order", dependencies)
                VALUES (?, ?, ?, 'pending', ?, ?)
            """, (name, description, project_id, order, json.dumps(dependencies)))
            
            task_id = cursor.lastrowid
            return {
                "id": task_id,
                "name": name,
                "description": description,
                "project_id": project_id,
                "status": "pending",
                "order": order,
                "dependencies": dependencies,
                "message": "Task created successfully"
            }
    
    def _create_todo_item(self, task_id: int, title: str, description: str,
                          order: int, dependencies: List[int], files: List[str]) -> Dict[str, Any]:
        """Create a new todo item"""
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Verify task exists
            cursor.execute("SELECT id FROM tasks WHERE id = ?", (task_id,))
            if not cursor.fetchone():
                return {"error": f"Task {task_id} not found"}
            
            # Create todo item
            cursor.execute("""
                INSERT INTO todo_items (title, description, task_id, status, "order", dependencies)
                VALUES (?, ?, ?, 'pending', ?, ?)
            """, (title, description, task_id, order, json.dumps(dependencies)))
            
            todo_id = cursor.lastrowid
            
            # Add files
            for file_path in files:
                # Get or create file record
                cursor.execute("SELECT id FROM files WHERE path = ?", (file_path,))
                file_record = cursor.fetchone()
                
                if not file_record:
                    cursor.execute("INSERT INTO files (path) VALUES (?)", (file_path,))
                    file_id = cursor.lastrowid
                else:
                    file_id = file_record['id']
                
                # Link file to todo item
                cursor.execute("""
                    INSERT INTO todo_item_files (todo_item_id, file_id)
                    VALUES (?, ?)
                """, (todo_id, file_id))
            
            return {
                "id": todo_id,
                "title": title,
                "description": description,
                "task_id": task_id,
                "status": "pending",
                "order": order,
                "dependencies": dependencies,
                "files": files,
                "message": "Todo item created successfully"
            }
    
    def _get_next_todo_item(self, project_name: str, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get the next available todo item for an agent"""
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Get project
            cursor.execute("SELECT id FROM projects WHERE name = ?", (project_name,))
            project = cursor.fetchone()
            if not project:
                return {"error": f"Project '{project_name}' not found"}
            
            # Get all todo items for the project with their dependencies
            cursor.execute("""
                SELECT ti.*, t.name as task_name, t.dependencies as task_dependencies
                FROM todo_items ti
                JOIN tasks t ON ti.task_id = t.id
                WHERE t.project_id = ?
                ORDER BY t."order", ti."order"
            """, (project['id'],))
            
            todo_items = cursor.fetchall()
            
            # Get completed todo IDs
            cursor.execute("""
                SELECT ti.id
                FROM todo_items ti
                JOIN tasks t ON ti.task_id = t.id
                WHERE t.project_id = ? AND ti.status = 'completed'
            """, (project['id'],))
            completed_ids = {row['id'] for row in cursor.fetchall()}
            
            # Get in-progress todo IDs
            cursor.execute("""
                SELECT ti.id
                FROM todo_items ti
                JOIN tasks t ON ti.task_id = t.id
                WHERE t.project_id = ? AND ti.status = 'in_progress'
            """, (project['id'],))
            in_progress_ids = {row['id'] for row in cursor.fetchall()}
            
            # Find next available todo item
            for item in todo_items:
                if item['status'] != 'pending':
                    continue
                
                # Check task dependencies
                task_deps = json.loads(item['task_dependencies'] or '[]')
                if task_deps:
                    cursor.execute("""
                        SELECT COUNT(*) as incomplete
                        FROM tasks
                        WHERE id IN ({}) AND status != 'completed'
                    """.format(','.join('?' * len(task_deps))), task_deps)
                    if cursor.fetchone()['incomplete'] > 0:
                        continue
                
                # Check todo dependencies
                todo_deps = json.loads(item['dependencies'] or '[]')
                if not all(dep_id in completed_ids for dep_id in todo_deps):
                    continue
                
                # Check file locks
                cursor.execute("""
                    SELECT f.path, f.locked, f.locked_by
                    FROM files f
                    JOIN todo_item_files tif ON f.id = tif.file_id
                    WHERE tif.todo_item_id = ?
                """, (item['id'],))
                files = cursor.fetchall()
                
                locked_files = [f for f in files if f['locked']]
                if locked_files:
                    continue  # Skip if any files are locked
                
                # This item is available
                return {
                    "id": item['id'],
                    "title": item['title'],
                    "description": item['description'],
                    "task_name": item['task_name'],
                    "files": [f['path'] for f in files],
                    "dependencies": todo_deps,
                    "message": "Todo item assigned to agent"
                }
            
            return {"message": "No available todo items at this time"}
    
    def _update_todo_status(self, todo_id: int, status: str, agent_id: str) -> Dict[str, Any]:
        """Update todo item status"""
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Get current todo item
            cursor.execute("SELECT * FROM todo_items WHERE id = ?", (todo_id,))
            todo = cursor.fetchone()
            if not todo:
                return {"error": f"Todo item {todo_id} not found"}
            
            # Update status
            cursor.execute("""
                UPDATE todo_items 
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (status, todo_id))
            
            # Handle file locking based on status
            if status == 'in_progress':
                # Lock all files for this todo item
                cursor.execute("""
                    UPDATE files
                    SET locked = 1, locked_by = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id IN (
                        SELECT file_id FROM todo_item_files WHERE todo_item_id = ?
                    )
                """, (agent_id, todo_id))
            
            elif status in ['completed', 'cancelled']:
                # Unlock all files for this todo item
                cursor.execute("""
                    UPDATE files
                    SET locked = 0, locked_by = NULL, updated_at = CURRENT_TIMESTAMP
                    WHERE id IN (
                        SELECT file_id FROM todo_item_files WHERE todo_item_id = ?
                    )
                """, (todo_id,))
            
            return {
                "id": todo_id,
                "status": status,
                "message": f"Todo item status updated to {status}"
            }
    
    def _check_file_locks(self, files: List[str]) -> Dict[str, Any]:
        """Check if files are locked"""
        with get_db() as conn:
            cursor = conn.cursor()
            
            file_status = {}
            for file_path in files:
                cursor.execute("""
                    SELECT locked, locked_by 
                    FROM files 
                    WHERE path = ?
                """, (file_path,))
                
                result = cursor.fetchone()
                if result:
                    file_status[file_path] = {
                        "locked": bool(result['locked']),
                        "locked_by": result['locked_by']
                    }
                else:
                    file_status[file_path] = {
                        "locked": False,
                        "locked_by": None
                    }
            
            return file_status
    
    def _lock_files(self, files: List[str], agent_id: str) -> Dict[str, Any]:
        """Lock files for exclusive access"""
        with get_db() as conn:
            cursor = conn.cursor()
            
            locked_files = []
            failed_files = []
            
            for file_path in files:
                # Get or create file record
                cursor.execute("SELECT id, locked, locked_by FROM files WHERE path = ?", (file_path,))
                file_record = cursor.fetchone()
                
                if not file_record:
                    cursor.execute("INSERT INTO files (path, locked, locked_by) VALUES (?, 1, ?)", 
                                 (file_path, agent_id))
                    locked_files.append(file_path)
                elif not file_record['locked']:
                    cursor.execute("""
                        UPDATE files 
                        SET locked = 1, locked_by = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (agent_id, file_record['id']))
                    locked_files.append(file_path)
                else:
                    failed_files.append({
                        "path": file_path,
                        "locked_by": file_record['locked_by']
                    })
            
            return {
                "locked": locked_files,
                "failed": failed_files,
                "message": f"Locked {len(locked_files)} files, {len(failed_files)} failed"
            }
    
    def _unlock_files(self, files: List[str], agent_id: str) -> Dict[str, Any]:
        """Unlock files"""
        with get_db() as conn:
            cursor = conn.cursor()
            
            unlocked_files = []
            failed_files = []
            
            for file_path in files:
                cursor.execute("""
                    SELECT id, locked_by 
                    FROM files 
                    WHERE path = ? AND locked = 1
                """, (file_path,))
                
                file_record = cursor.fetchone()
                if file_record and file_record['locked_by'] == agent_id:
                    cursor.execute("""
                        UPDATE files 
                        SET locked = 0, locked_by = NULL, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (file_record['id'],))
                    unlocked_files.append(file_path)
                elif file_record:
                    failed_files.append({
                        "path": file_path,
                        "reason": f"Locked by {file_record['locked_by']}"
                    })
            
            return {
                "unlocked": unlocked_files,
                "failed": failed_files,
                "message": f"Unlocked {len(unlocked_files)} files, {len(failed_files)} failed"
            }
    
    def _get_project_status(self, project_name: str) -> Dict[str, Any]:
        """Get comprehensive project status"""
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Use the project view for statistics
            cursor.execute("""
                SELECT * FROM project_stats WHERE name = ?
            """, (project_name,))
            
            project_stats = cursor.fetchone()
            if not project_stats:
                return {"error": f"Project '{project_name}' not found"}
            
            # Get detailed task information
            cursor.execute("""
                SELECT * FROM task_stats 
                WHERE project_name = ?
                ORDER BY "order"
            """, (project_name,))
            
            tasks = []
            for task in cursor.fetchall():
                task_data = dict(task)
                
                # Get todo items for this task
                cursor.execute("""
                    SELECT * FROM todo_item_details
                    WHERE task_id = ?
                    ORDER BY "order"
                """, (task['id'],))
                
                task_data['todo_items'] = [dict(item) for item in cursor.fetchall()]
                tasks.append(task_data)
            
            return {
                "project": dict(project_stats),
                "tasks": tasks,
                "summary": {
                    "total_tasks": project_stats['total_tasks'],
                    "completed_tasks": project_stats['completed_tasks'],
                    "active_tasks": project_stats['active_tasks'],
                    "completion_percentage": project_stats['completion_percentage']
                }
            }
    
    def _insert_todo_item(self, task_id: int, title: str, description: str,
                          after_todo_id: Optional[int], dependencies: List[int], 
                          files: List[str]) -> Dict[str, Any]:
        """Insert a todo item at a specific position"""
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Determine the new order value
            if after_todo_id:
                cursor.execute("""
                    SELECT "order" FROM todo_items 
                    WHERE id = ? AND task_id = ?
                """, (after_todo_id, task_id))
                after_item = cursor.fetchone()
                if not after_item:
                    return {"error": f"Todo item {after_todo_id} not found in task {task_id}"}
                
                new_order = after_item['order'] + 1
                
                # Shift subsequent items
                cursor.execute("""
                    UPDATE todo_items 
                    SET "order" = "order" + 1 
                    WHERE task_id = ? AND "order" >= ?
                """, (task_id, new_order))
            else:
                # Insert at beginning
                new_order = 0
                cursor.execute("""
                    UPDATE todo_items 
                    SET "order" = "order" + 1 
                    WHERE task_id = ?
                """, (task_id,))
            
            # Create the todo item
            return self._create_todo_item(task_id, title, description, 
                                        new_order, dependencies, files)
    
    def _generate_project_overview(self, project: Dict[str, Any]) -> str:
        """Generate a human-readable project overview"""
        status = self._get_project_status(project['name'])
        
        overview = f"""
# Project Overview: {project['name']}

## Description
{project['description']}

## Status: {project['status']}

## Summary
- Total Tasks: {status['summary']['total_tasks']}
- Completed Tasks: {status['summary']['completed_tasks']}
- Active Tasks: {status['summary']['active_tasks']}
- Overall Completion: {status['summary']['completion_percentage']}%

## Tasks
"""
        
        for task in status['tasks']:
            overview += f"\n### Task: {task['name']} ({task['status']})\n"
            overview += f"{task['description']}\n"
            overview += f"- Todo Items: {task['total_todo_items']}\n"
            overview += f"- Completed: {task['completed_todo_items']}\n"
            overview += f"- In Progress: {task['active_todo_items']}\n"
            overview += f"- Completion: {task['completion_percentage']}%\n"
            
            if task['todo_items']:
                overview += "\nTodo Items:\n"
                for item in task['todo_items']:
                    status_emoji = {
                        'completed': '✅',
                        'in_progress': '🔄',
                        'pending': '⏳',
                        'cancelled': '❌'
                    }.get(item['status'], '❓')
                    
                    overview += f"  {status_emoji} {item['title']}"
                    if item['file_count'] > 0:
                        overview += f" (📁 {item['file_count']} files)"
                    overview += "\n"
        
        return overview
    
    async def run(self):
        """Run the MCP server"""
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
    server = AgentCoordinatorServer()
    asyncio.run(server.run())
