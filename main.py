#!/usr/bin/env python3
"""
MCP Agent Coordinator Server
A unified MCP server for coordinating multiple autonomous agents working on the same project.

Supports both stdio (traditional MCP) and HTTP modes for different client integrations.
"""

import asyncio
import json
import sqlite3
import logging
import os
import sys
import webbrowser
from datetime import datetime
from typing import List, Dict, Optional, Any, Set
from contextlib import contextmanager

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.responses import HTMLResponse, JSONResponse, FileResponse
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect
from starlette.middleware.cors import CORSMiddleware

from models import Project, Task, TodoItem, File, Status

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
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

def init_database():
    """Initialize database tables including the new audit_events table with migration support"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Create schema_version table to track migrations
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                id INTEGER PRIMARY KEY,
                version INTEGER NOT NULL,
                applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Check current schema version
        cursor.execute("SELECT MAX(version) as current_version FROM schema_version")
        row = cursor.fetchone()
        current_version = row[0] if row[0] is not None else 0
        
        # Migration 1: Create audit_events table
        if current_version < 1:
            logger.info("Applying migration 1: Creating audit_events table")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id INTEGER,
                    entity_name TEXT,
                    old_status TEXT,
                    new_status TEXT,
                    agent_id TEXT,
                    project_name TEXT,
                    task_name TEXT,
                    details TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes for efficient queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_events_project_time 
                ON audit_events(project_name, created_at DESC)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_events_entity 
                ON audit_events(entity_type, entity_id, created_at DESC)
            """)
            
            # Record migration
            cursor.execute("INSERT INTO schema_version (version) VALUES (1)")
            logger.info("Migration 1 completed successfully")
        
        logger.info(f"Database initialization completed successfully (current version: {max(current_version, 1)})")

# Audit logging helper functions
def log_audit_event(event_type: str, entity_type: str, entity_id: Optional[int] = None, 
                   entity_name: Optional[str] = None, old_status: Optional[str] = None, 
                   new_status: Optional[str] = None, agent_id: Optional[str] = None,
                   project_name: Optional[str] = None, task_name: Optional[str] = None,
                   details: Optional[Dict[str, Any]] = None):
    """Generic audit event logging function"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO audit_events 
                (event_type, entity_type, entity_id, entity_name, old_status, new_status, 
                 agent_id, project_name, task_name, details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event_type, entity_type, entity_id, entity_name, old_status, new_status,
                agent_id, project_name, task_name, json.dumps(details) if details else None
            ))
            logger.debug(f"Audit event logged: {event_type} for {entity_type} {entity_id or entity_name}")
    except Exception as e:
        logger.error(f"Failed to log audit event: {e}")

def log_status_change(entity_type: str, entity_id: int, entity_name: str, 
                     old_status: str, new_status: str, agent_id: Optional[str] = None,
                     project_name: Optional[str] = None, task_name: Optional[str] = None,
                     additional_details: Optional[Dict[str, Any]] = None):
    """Log status change events for projects, tasks, or todos"""
    details = {
        "change_type": "status_update",
        "previous_status": old_status,
        "current_status": new_status,
        **(additional_details or {})
    }
    
    log_audit_event(
        event_type="status_change",
        entity_type=entity_type,
        entity_id=entity_id,
        entity_name=entity_name,
        old_status=old_status,
        new_status=new_status,
        agent_id=agent_id,
        project_name=project_name,
        task_name=task_name,
        details=details
    )

def log_project_event(event_type: str, project_id: int, project_name: str,
                     agent_id: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
    """Log project-related events"""
    log_audit_event(
        event_type=event_type,
        entity_type="project",
        entity_id=project_id,
        entity_name=project_name,
        agent_id=agent_id,
        project_name=project_name,
        details=details
    )

def log_task_event(event_type: str, task_id: int, task_name: str, project_name: str,
                  agent_id: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
    """Log task-related events"""
    log_audit_event(
        event_type=event_type,
        entity_type="task",
        entity_id=task_id,
        entity_name=task_name,
        agent_id=agent_id,
        project_name=project_name,
        task_name=task_name,
        details=details
    )

def log_todo_event(event_type: str, todo_id: int, todo_title: str, task_name: str,
                  project_name: str, agent_id: Optional[str] = None, 
                  details: Optional[Dict[str, Any]] = None):
    """Log todo item-related events"""
    log_audit_event(
        event_type=event_type,
        entity_type="todo",
        entity_id=todo_id,
        entity_name=todo_title,
        agent_id=agent_id,
        project_name=project_name,
        task_name=task_name,
        details=details
    )

def log_file_event(event_type: str, file_path: str, agent_id: Optional[str] = None,
                  project_name: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
    """Log file lock/unlock events"""
    log_audit_event(
        event_type=event_type,
        entity_type="file",
        entity_name=file_path,
        agent_id=agent_id,
        project_name=project_name,
        details=details
    )

def log_completion_event(entity_type: str, entity_id: int, entity_name: str,
                        project_name: str, agent_id: Optional[str] = None,
                        task_name: Optional[str] = None, completion_time: Optional[datetime] = None):
    """Log completion events with timing information"""
    details = {
        "completion_time": (completion_time or datetime.now()).isoformat(),
        "milestone": "completion"
    }
    
    log_audit_event(
        event_type="completion",
        entity_type=entity_type,
        entity_id=entity_id,
        entity_name=entity_name,
        new_status="completed",
        agent_id=agent_id,
        project_name=project_name,
        task_name=task_name,
        details=details
    )

# WebSocket connection manager for real-time updates
class WebSocketManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        try:
            await websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")
            self.disconnect(websocket)

    async def broadcast(self, message: dict):
        if not self.active_connections:
            return
        
        disconnected = set()
        for connection in self.active_connections.copy():
            try:
                await connection.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Error broadcasting to connection: {e}")
                disconnected.add(connection)
        
        for connection in disconnected:
            self.disconnect(connection)

    async def notify_project_change(self, project_name: str, change_type: str):
        await self.broadcast({
            "type": change_type,
            "project_name": project_name,
            "timestamp": datetime.now().isoformat()
        })

    async def notify_task_change(self, project_name: str, task_id: int, change_type: str):
        await self.broadcast({
            "type": change_type,
            "project_name": project_name,
            "task_id": task_id,
            "timestamp": datetime.now().isoformat()
        })

    async def notify_todo_change(self, project_name: str, todo_id: int, change_type: str):
        await self.broadcast({
            "type": change_type,
            "project_name": project_name,
            "todo_id": todo_id,
            "timestamp": datetime.now().isoformat()
        })

# Global WebSocket manager
ws_manager = WebSocketManager()

# Initialize MCP server
mcp = FastMCP("Agent Coordinator MCP Server")

@mcp.tool()
def get_instructions() -> str:
    """Get comprehensive instructions on how to use the agent coordination system"""
    return """
# Agent Coordination System Instructions

This MCP server coordinates work across multiple autonomous agents working on the same project by managing:

## Core Concepts

### Projects
- **GLOBAL SCOPE**: Projects represent entire software applications, systems, or major initiatives
- Identified by unique names (typically the project root directory name)
- Should describe the overall purpose, technology stack, and high-level objectives
- Examples: "E-commerce Platform", "Machine Learning Pipeline", "Authentication Service"
- Container for all related tasks and todos across the entire project lifecycle

### Tasks
- **SPECIFIC FUNCTIONAL AREAS**: Tasks are concrete, well-defined work packages within a project
- Should represent specific features, components, or system areas (e.g., "User Authentication", "Payment Processing", "Data Validation")
- Have clear deliverables and acceptance criteria
- Support execution order and dependencies on other tasks
- Should be granular enough to be completed by a single agent or small team

### Todo Items
- **INDIVIDUAL ACTIONABLE ITEMS**: Specific, atomic work units within tasks
- Must have clear, measurable completion criteria
- Can specify exact files that need modification
- Support execution order and dependencies on other todos
- Should focus on single responsibility (one file, one function, one test, etc.)

### File Locking
- Prevents conflicts when multiple agents modify the same files
- Automatic lock/unlock when working on todos
- Check locks before starting work

## ⚠️ CRITICAL COMPLETION REQUIREMENTS ⚠️

**ABSOLUTE REQUIREMENT**: Items and tasks MUST ALWAYS be marked as completed when finished.

### Completion Rules (NON-NEGOTIABLE):
1. **Every todo item** that is finished MUST be marked `"completed"` immediately
2. **Every task** that has all todos completed MUST be marked `"completed"`
3. **Never leave items in "in_progress" state** after work is done
4. **Completion is mandatory**, not optional - the entire coordination system depends on accurate status tracking
5. **Check your work**: Before moving to next item, verify the current one is marked complete

### Consequences of Not Marking Complete:
- Other agents will think work is still in progress
- Dependencies won't be satisfied
- Project status becomes inaccurate
- Work may be duplicated
- The coordination system fails

## Typical Workflow

1. **Get Instructions**: Always start by calling `get_instructions`
2. **Check for Existing Project**: `get_project(name="project-dir-name")`
3. **Create Project** (if needed): `create_project(name="project-dir-name", description="High-level description of entire system/application")`
4. **Create Tasks**: `create_task(project_name="project-dir-name", name="Specific Feature/Component", description="Detailed description of what this task accomplishes and its deliverables")`
5. **Create Todos**: `create_todo_item(task_id=1, title="Specific action item", files=["exact/file/path.ext"])`
6. **Get Work**: `get_next_todo_item(project_name="project-dir-name", agent_id="agent-1")`
7. **Start Work**: `update_todo_status(todo_id=1, status="in_progress", agent_id="agent-1")`
8. **⚠️ COMPLETE WORK**: `update_todo_status(todo_id=1, status="completed", agent_id="agent-1")` **[MANDATORY]**

## Best Practices

- **ALWAYS mark items completed** when finished - this cannot be overstated
- Always check file locks before modifying files (`check_file_locks`)
- Use descriptive, specific names for projects, tasks, and todos
- Set proper dependencies to ensure correct execution order
- Lock only the files you need and unlock them promptly
- Create granular todo items that focus on specific files to minimize conflicts
- Review project status regularly to ensure completion tracking is accurate

## File Locking Rules

- Files are automatically locked when a todo item becomes "in_progress"
- Files are automatically unlocked when a todo item is "completed" or "cancelled"
- Manual locking/unlocking is also available if needed
- Never modify files that are locked by other agents

## Project Structure Guidelines

### Project Descriptions Should Include:
- Overall purpose and goals
- Technology stack and architecture
- Target users or stakeholders
- Key business requirements
- Success criteria

### Task Descriptions Should Include:
- Specific functionality being implemented
- Acceptance criteria
- Dependencies on other tasks
- Expected deliverables
- Technical implementation approach

### Todo Descriptions Should Include:
- Exact action to be performed
- Expected outcome
- Files to be modified
- Testing requirements

**REMEMBER: The success of multi-agent coordination depends entirely on accurate completion tracking. Mark everything complete when it's done!**

Use the available tools to implement this workflow in your autonomous agent system.
"""

@mcp.tool()
async def create_project(name: str, description: str) -> dict:
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
            
            result = {
                "id": row["id"],
                "name": row["name"],
                "description": row["description"],
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "message": "Project created successfully"
            }
            
            # Log audit event for project creation
            log_project_event(
                event_type="project_created",
                project_id=project_id,
                project_name=name,
                details={
                    "description": description,
                    "initial_status": Status.PENDING.value,
                    "creation_method": "mcp_tool"
                }
            )
            
            # Notify WebSocket clients
            asyncio.create_task(ws_manager.notify_project_change(name, "project_created"))
            
            return result
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
        
        # Log audit event for project access
        log_project_event(
            event_type="project_accessed",
            project_id=row["id"],
            project_name=name,
            details={
                "access_method": "mcp_tool",
                "project_status": row["status"]
            }
        )
        
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"]
        }

@mcp.tool()
async def create_task(project_name: str, name: str, description: str, order: int = 0, dependencies: List[int] = None) -> dict:
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
        
        result = {
            "id": row["id"],
            "project_id": row["project_id"],
            "name": row["name"],
            "description": row["description"],
            "order_index": row["order_index"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "dependencies": dependencies,
            "message": "Task created successfully"
        }
        
        # Log audit event for task creation
        log_task_event(
            event_type="task_created",
            task_id=task_id,
            task_name=name,
            project_name=project_name,
            details={
                "description": description,
                "order_index": order,
                "initial_status": Status.PENDING.value,
                "dependencies": dependencies,
                "creation_method": "mcp_tool"
            }
        )
        
        # Notify WebSocket clients
        asyncio.create_task(ws_manager.notify_task_change(project_name, task_id, "task_created"))
        
        return result

@mcp.tool()
def create_todo_item(task_id: int, title: str, description: str = "", order: int = 0, dependencies: List[int] = None, files: List[str] = None) -> dict:
    """Create a new todo item within a task"""
    if dependencies is None:
        dependencies = []
    if files is None:
        files = []
        
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Verify task exists and get task/project info
        cursor.execute("""
            SELECT t.*, p.name as project_name 
            FROM tasks t 
            JOIN projects p ON t.project_id = p.id 
            WHERE t.id = ?
        """, (task_id,))
        task_row = cursor.fetchone()
        if not task_row:
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
        
        # Log audit event for todo creation
        log_todo_event(
            event_type="todo_created",
            todo_id=todo_id,
            todo_title=title,
            task_name=task_row["name"],
            project_name=task_row["project_name"],
            details={
                "description": description,
                "order_index": order,
                "initial_status": Status.PENDING.value,
                "dependencies": dependencies,
                "associated_files": files,
                "creation_method": "mcp_tool"
            }
        )
        
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
            "files": files,
            "message": "Todo item created successfully"
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
        
        # Find available todo items (no incomplete dependencies, not locked files)
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
            return {"message": "No available todo items at this time"}
        
        # Get associated files
        cursor.execute("SELECT file_path FROM todo_files WHERE todo_id = ?", (row["id"],))
        files = [f["file_path"] for f in cursor.fetchall()]
        
        return {
            "id": row["id"],
            "task_id": row["task_id"],
            "title": row["title"],
            "description": row["description"],
            "order_index": row["order_index"],
            "status": row["status"],
            "files": files,
            "message": "Todo item available for assignment. Call update_todo_status to claim it."
        }

@mcp.tool()
async def update_todo_status(todo_id: int, status: str, agent_id: str) -> dict:
    """Update the status of a todo item"""
    valid_statuses = ["pending", "in_progress", "completed", "cancelled"]
    if status not in valid_statuses:
        return {"error": f"Invalid status. Must be one of: {valid_statuses}"}
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Verify todo exists and get current status
        cursor.execute("""
            SELECT ti.*, t.name as task_name, p.name as project_name 
            FROM todo_items ti
            JOIN tasks t ON ti.task_id = t.id 
            JOIN projects p ON t.project_id = p.id 
            WHERE ti.id = ?
        """, (todo_id,))
        row = cursor.fetchone()
        if not row:
            return {"error": f"Todo item with ID {todo_id} not found"}
        
        old_status = row["status"]
        
        # Check agent permissions
        if row["assigned_agent"] and row["assigned_agent"] != agent_id and status not in ["pending"]:
            return {"error": f"Todo item is assigned to different agent: {row['assigned_agent']}"}
        
        # Update status and assignment
        assigned_agent = None
        if status == "in_progress":
            assigned_agent = agent_id
        elif status == "pending":
            assigned_agent = None
        elif status in ["completed", "cancelled"]:
            assigned_agent = None
        
        cursor.execute(
            "UPDATE todo_items SET status = ?, assigned_agent = ?, updated_at = ? WHERE id = ?",
            (status, assigned_agent, datetime.now(), todo_id)
        )
        
        # Handle file locking
        if status == "in_progress":
            # Lock all files for this todo item
            cursor.execute("SELECT file_path FROM todo_files WHERE todo_id = ?", (todo_id,))
            files = [f["file_path"] for f in cursor.fetchall()]
            for file_path in files:
                cursor.execute(
                    "INSERT OR REPLACE INTO file_locks (file_path, locked_by, locked_at) VALUES (?, ?, ?)",
                    (file_path, agent_id, datetime.now())
                )
        elif status in ["completed", "cancelled"]:
            # Unlock all files for this todo item
            cursor.execute("SELECT file_path FROM todo_files WHERE todo_id = ?", (todo_id,))
            files = [f["file_path"] for f in cursor.fetchall()]
            for file_path in files:
                cursor.execute("DELETE FROM file_locks WHERE file_path = ? AND locked_by = ?", (file_path, agent_id))
        
        # Get project name for notification
        cursor.execute("""
            SELECT p.name FROM projects p 
            JOIN tasks t ON p.id = t.project_id 
            JOIN todo_items ti ON t.id = ti.task_id 
            WHERE ti.id = ?
        """, (todo_id,))
        project_row = cursor.fetchone()
        project_name = project_row["name"] if project_row else None
        
        result = {
            "id": todo_id,
            "status": status,
            "assigned_agent": assigned_agent,
            "updated_at": str(datetime.now()),
            "message": f"Todo item status updated to {status}"
        }
        
        # Log audit event for status change
        log_status_change(
            entity_type="todo",
            entity_id=todo_id,
            entity_name=row["title"],
            old_status=old_status,
            new_status=status,
            agent_id=agent_id,
            project_name=row["project_name"],
            task_name=row["task_name"],
            additional_details={
                "previous_agent": row["assigned_agent"],
                "new_agent": assigned_agent,
                "change_method": "mcp_tool"
            }
        )
        
        # Log completion event if status is completed
        if status == "completed":
            log_completion_event(
                entity_type="todo",
                entity_id=todo_id,
                entity_name=row["title"],
                project_name=row["project_name"],
                agent_id=agent_id,
                task_name=row["task_name"]
            )
        
        # Notify WebSocket clients
        if project_name:
            asyncio.create_task(ws_manager.notify_todo_change(project_name, todo_id, "todo_status_changed"))
        
        return result

@mcp.tool()
def get_project_audit_trail(project_name: str, limit: int = 50) -> dict:
    """Get comprehensive audit trail for a project with completion summary"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Verify project exists
        cursor.execute("SELECT id FROM projects WHERE name = ?", (project_name,))
        project_row = cursor.fetchone()
        if not project_row:
            return {"error": f"Project '{project_name}' not found"}
        
        # Get all audit events for the project
        cursor.execute("""
            SELECT event_type, entity_type, entity_id, entity_name, old_status, new_status,
                   agent_id, task_name, details, created_at
            FROM audit_events 
            WHERE project_name = ? 
            ORDER BY created_at DESC 
            LIMIT ?
        """, (project_name, limit))
        
        audit_events = []
        for row in cursor.fetchall():
            event = dict(row)
            if event["details"]:
                try:
                    event["details"] = json.loads(event["details"])
                except (json.JSONDecodeError, TypeError):
                    pass
            audit_events.append(event)
        
        # Get completion statistics
        cursor.execute("""
            SELECT COUNT(*) as total_completed,
                   COUNT(CASE WHEN entity_type = 'project' THEN 1 END) as projects_completed,
                   COUNT(CASE WHEN entity_type = 'task' THEN 1 END) as tasks_completed,
                   COUNT(CASE WHEN entity_type = 'todo' THEN 1 END) as todos_completed
            FROM audit_events 
            WHERE project_name = ? AND event_type = 'completion'
        """, (project_name,))
        
        completion_stats = dict(cursor.fetchone())
        
        # Get timeline of major milestones
        cursor.execute("""
            SELECT event_type, entity_type, entity_name, agent_id, created_at
            FROM audit_events 
            WHERE project_name = ? AND event_type IN ('project_created', 'task_created', 'completion')
            ORDER BY created_at ASC
        """, (project_name,))
        
        milestones = [dict(row) for row in cursor.fetchall()]
        
        return {
            "project_name": project_name,
            "audit_events": audit_events,
            "completion_statistics": completion_stats,
            "milestones": milestones,
            "total_events": len(audit_events)
        }

@mcp.tool()
def get_project_completion_summary(project_name: str) -> dict:
    """Get a comprehensive completion summary for a project including timing and agent information"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Verify project exists
        cursor.execute("SELECT * FROM projects WHERE name = ?", (project_name,))
        project_row = cursor.fetchone()
        if not project_row:
            return {"error": f"Project '{project_name}' not found"}
        
        project_info = dict(project_row)
        
        # Get completed tasks with completion times and agents
        cursor.execute("""
            SELECT t.id, t.name, t.description, t.created_at,
                   ae.created_at as completed_at, ae.agent_id as completed_by
            FROM tasks t
            LEFT JOIN audit_events ae ON t.id = ae.entity_id 
                AND ae.entity_type = 'task' AND ae.event_type = 'completion'
            WHERE t.project_id = ? AND t.status = 'completed'
            ORDER BY ae.created_at DESC
        """, (project_row["id"],))
        
        completed_tasks = [dict(row) for row in cursor.fetchall()]
        
        # Get completed todos with completion times and agents
        cursor.execute("""
            SELECT ti.id, ti.title, ti.description, t.name as task_name,
                   ti.created_at, ae.created_at as completed_at, ae.agent_id as completed_by
            FROM todo_items ti
            JOIN tasks t ON ti.task_id = t.id
            LEFT JOIN audit_events ae ON ti.id = ae.entity_id 
                AND ae.entity_type = 'todo' AND ae.event_type = 'completion'
            WHERE t.project_id = ? AND ti.status = 'completed'
            ORDER BY ae.created_at DESC
        """, (project_row["id"],))
        
        completed_todos = [dict(row) for row in cursor.fetchall()]
        
        # Get agent productivity statistics
        cursor.execute("""
            SELECT agent_id, 
                   COUNT(*) as total_completions,
                   COUNT(CASE WHEN entity_type = 'task' THEN 1 END) as tasks_completed,
                   COUNT(CASE WHEN entity_type = 'todo' THEN 1 END) as todos_completed,
                   MIN(created_at) as first_completion,
                   MAX(created_at) as last_completion
            FROM audit_events 
            WHERE project_name = ? AND event_type = 'completion' AND agent_id IS NOT NULL
            GROUP BY agent_id
            ORDER BY total_completions DESC
        """, (project_name,))
        
        agent_stats = [dict(row) for row in cursor.fetchall()]
        
        # Get overall project progress
        cursor.execute("""
            SELECT COUNT(*) as total_tasks,
                   COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_tasks,
                   COUNT(CASE WHEN status = 'in_progress' THEN 1 END) as in_progress_tasks,
                   COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending_tasks
            FROM tasks WHERE project_id = ?
        """, (project_row["id"],))
        
        task_progress = dict(cursor.fetchone())
        
        cursor.execute("""
            SELECT COUNT(*) as total_todos,
                   COUNT(CASE WHEN ti.status = 'completed' THEN 1 END) as completed_todos,
                   COUNT(CASE WHEN ti.status = 'in_progress' THEN 1 END) as in_progress_todos,
                   COUNT(CASE WHEN ti.status = 'pending' THEN 1 END) as pending_todos
            FROM todo_items ti
            JOIN tasks t ON ti.task_id = t.id
            WHERE t.project_id = ?
        """, (project_row["id"],))
        
        todo_progress = dict(cursor.fetchone())
        
        return {
            "project": project_info,
            "completed_tasks": completed_tasks,
            "completed_todos": completed_todos,
            "agent_statistics": agent_stats,
            "progress_summary": {
                "tasks": task_progress,
                "todos": todo_progress,
                "overall_completion_percentage": round(
                    (task_progress["completed_tasks"] / max(task_progress["total_tasks"], 1)) * 100, 1
                )
            }
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
            
            # Log audit event for file locking
            log_file_event(
                event_type="file_locked",
                file_path=file_path,
                agent_id=agent_id,
                details={
                    "lock_method": "mcp_tool",
                    "lock_time": datetime.now().isoformat()
                }
            )
        
        return {
            "locked_files": files,
            "locked_by": agent_id,
            "locked_at": str(datetime.now()),
            "message": f"Successfully locked {len(files)} files"
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
                
                # Log audit event for file unlocking
                log_file_event(
                    event_type="file_unlocked",
                    file_path=file_path,
                    agent_id=agent_id,
                    details={
                        "unlock_method": "mcp_tool",
                        "unlock_time": datetime.now().isoformat()
                    }
                )
            else:
                not_owned.append(file_path)
        
        result = {
            "unlocked_files": unlocked_files,
            "agent_id": agent_id,
            "message": f"Successfully unlocked {len(unlocked_files)} files"
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
        
        # Log audit event for project status access
        log_project_event(
            event_type="project_status_accessed",
            project_id=project_id,
            project_name=project_name,
            details={
                "access_method": "mcp_tool",
                "current_status": project_row["status"]
            }
        )
        
        # Get tasks and their todos
        cursor.execute("""
            SELECT t.id, t.project_id, t.name, t.description, t.status, t.created_at, t.updated_at,
                   COUNT(ti.id) as total_todos,
                   COUNT(CASE WHEN ti.status = 'completed' THEN 1 END) as completed_todos,
                   COUNT(CASE WHEN ti.status = 'in_progress' THEN 1 END) as in_progress_todos,
                   COUNT(CASE WHEN ti.status = 'pending' THEN 1 END) as pending_todos
            FROM tasks t
            LEFT JOIN todo_items ti ON t.id = ti.task_id
            WHERE t.project_id = ?
            GROUP BY t.id
            ORDER BY t.id
        """, (project_id,))
        
        tasks = []
        for task_row in cursor.fetchall():
            # Get detailed todo items for each task
            cursor.execute("""
                SELECT ti.*, 
                       GROUP_CONCAT(tf.file_path) as files,
                       GROUP_CONCAT(td.depends_on_todo_id) as dependencies
                FROM todo_items ti
                LEFT JOIN todo_files tf ON ti.id = tf.todo_id
                LEFT JOIN todo_dependencies td ON ti.id = td.todo_id
                WHERE ti.task_id = ?
                GROUP BY ti.id
                ORDER BY ti.order_index
            """, (task_row["id"],))
            
            todo_items = []
            for todo_row in cursor.fetchall():
                todo_data = dict(todo_row)
                todo_data["files"] = todo_row["files"].split(",") if todo_row["files"] else []
                todo_data["dependencies"] = [int(x) for x in todo_row["dependencies"].split(",") if x] if todo_row["dependencies"] else []
                todo_items.append(todo_data)
            
            task_data = dict(task_row)
            task_data["todo_items"] = todo_items
            task_data["completion_percentage"] = round((task_row["completed_todos"] / max(task_row["total_todos"], 1)) * 100, 1)
            tasks.append(task_data)
        
        # Overall project stats
        cursor.execute("""
            SELECT COUNT(*) as total_todos,
                   COUNT(CASE WHEN ti.status = 'completed' THEN 1 END) as completed_todos,
                   COUNT(CASE WHEN ti.status = 'in_progress' THEN 1 END) as in_progress_todos,
                   COUNT(CASE WHEN ti.status = 'pending' THEN 1 END) as pending_todos
            FROM todo_items ti
            JOIN tasks t ON ti.task_id = t.id
            WHERE t.project_id = ?
        """, (project_id,))
        
        stats = cursor.fetchone()
        
        return {
            "project": dict(project_row),
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
            cursor.execute("SELECT order_index FROM todo_items WHERE id = ? AND task_id = ?", (after_todo_id, task_id))
            row = cursor.fetchone()
            if not row:
                return {"error": f"Todo item with ID {after_todo_id} not found in task {task_id}"}
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
            "files": files,
            "message": "Todo item inserted successfully"
        }

# Web API endpoints for the dashboard
async def get_all_projects_api(request):
    """Get all projects with summary data"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM projects ORDER BY created_at DESC")
            projects = []
            
            for project_row in cursor.fetchall():
                project_data = get_project_status(project_row["name"])
                if "error" not in project_data:
                    projects.append(project_data)
            
            return JSONResponse({"projects": projects})
    except Exception as e:
        logger.error(f"Error getting all projects: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_project_api(request):
    """Get detailed project data"""
    try:
        project_name = request.path_params["project_name"]
        project_data = get_project_status(project_name)
        
        if "error" in project_data:
            return JSONResponse(project_data, status_code=404)
        
        return JSONResponse(project_data)
    except Exception as e:
        logger.error(f"Error getting project: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_project_audit_api(request):
    """Get audit trail for a project"""
    try:
        project_name = request.path_params["project_name"]
        limit = int(request.query_params.get("limit", 50))
        
        audit_data = get_project_audit_trail(project_name, limit)
        
        if "error" in audit_data:
            return JSONResponse(audit_data, status_code=404)
        
        return JSONResponse(audit_data)
    except Exception as e:
        logger.error(f"Error getting project audit trail: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

async def get_project_completion_api(request):
    """Get completion summary for a project"""
    try:
        project_name = request.path_params["project_name"]
        
        completion_data = get_project_completion_summary(project_name)
        
        if "error" in completion_data:
            return JSONResponse(completion_data, status_code=404)
        
        return JSONResponse(completion_data)
    except Exception as e:
        logger.error(f"Error getting project completion summary: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

async def console_dashboard(request):
    """Serve the main dashboard HTML"""
    try:
        with open("static/index.html", "r", encoding="utf-8") as f:
            html_content = f.read()
        return HTMLResponse(html_content)
    except FileNotFoundError:
        return HTMLResponse("<h1>Dashboard not found</h1><p>Please ensure static files are properly deployed.</p>", status_code=404)
    except UnicodeDecodeError as e:
        logger.error(f"Unicode error reading dashboard HTML: {e}")
        return HTMLResponse("<h1>Dashboard Error</h1><p>Error reading dashboard file.</p>", status_code=500)

async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                if message.get("type") == "heartbeat":
                    await ws_manager.send_personal_message({"type": "heartbeat"}, websocket)
                elif message.get("type") == "heartbeat_response":
                    # Client responded to our heartbeat
                    pass
            except json.JSONDecodeError:
                logger.error("Invalid JSON received from WebSocket")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)

def start_stdio_server():
    """Start the MCP server in stdio mode"""
    try:
        logger.info("Starting Agent Coordinator MCP Server in stdio mode...")
        init_database()
        mcp.run()
        logger.info("Agent Coordinator MCP Server started successfully")
    except Exception as e:
        logger.error(f"Error starting stdio server: {str(e)}")
        raise

def start_http_server():
    """Start the MCP server in HTTP mode using uvicorn"""
    try:
        host = os.getenv("MCP_SERVER_HOST", "127.0.0.1")
        port = int(os.getenv("MCP_SERVER_PORT", "8001"))

        # Ensure MCP server is fully initialized
        logger.info("Initializing MCP server...")
        init_database()
        
        # Create Starlette app with MCP at root and specific dashboard paths
        app = Starlette(
            routes=[
                # Dashboard routes with specific paths
                Route("/console", console_dashboard),
                Route("/dashboard/api/projects", get_all_projects_api),
                Route("/dashboard/api/projects/{project_name}", get_project_api),
                Route("/dashboard/api/projects/{project_name}/audit", get_project_audit_api),
                Route("/dashboard/api/projects/{project_name}/completion", get_project_completion_api),
                
                # WebSocket for real-time updates
                WebSocketRoute("/dashboard/ws", websocket_endpoint),
                
                # Static files for dashboard
                Mount("/static", StaticFiles(directory="static"), name="static"),
                
                # MCP server at root
                Mount("/", mcp.sse_app()),
            ]
        )
        
        # Add CORS middleware for web dashboard
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        logger.info(f"Starting Agent Coordinator MCP Server in HTTP mode on http://{host}:{port}...")
        logger.info("🔧 Use this URL in your Cursor MCP configuration:")
        logger.info(f'   {{"mcpServers": {{"agent-coordinator": {{"url": "http://{host}:{port}"}}}}}}')
        logger.info("📡 Available tools: 12 coordination tools")
        logger.info(f"🌐 Web Dashboard: http://{host}:{port}/console")
        
        # Auto-launch browser for the dashboard
        dashboard_url = f"http://{host}:{port}/console"
        try:
            webbrowser.open(dashboard_url)
            logger.info("🚀 Opened web dashboard in default browser")
        except Exception as e:
            logger.warning(f"Could not auto-open browser: {e}")
            logger.info(f"Manually open: {dashboard_url}")
        
        uvicorn.run(app, host=host, port=port)
    except Exception as e:
        logger.error(f"Error starting HTTP server: {str(e)}")
        raise

if __name__ == "__main__":
    try:
        # Check which mode to run in (default to HTTP for easier setup)
        use_stdio = os.getenv("USE_STDIO", "false").lower() == "true"

        if use_stdio:
            # Run in stdio mode (traditional MCP)
            start_stdio_server()
        else:
            # Run in HTTP mode (easier for Cursor)
            start_http_server()
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        raise 