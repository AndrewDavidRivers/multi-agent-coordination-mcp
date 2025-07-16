# Proposed Architecture for Agent Coordinator MCP Server

## Executive Summary

The Agent Coordinator MCP is a Model Context Protocol (MCP) server designed to orchestrate multiple autonomous agents working simultaneously on the same codebase within an IDE environment. It provides a coordination layer that prevents conflicts, manages dependencies, and ensures orderly parallel development through intelligent work distribution and file locking mechanisms.

## Problem Statement

### Current Challenges
- **Merge Conflicts**: Multiple agents modifying the same files simultaneously
- **Race Conditions**: Uncoordinated access to shared resources
- **Work Duplication**: Agents unknowingly working on the same tasks
- **Dependency Violations**: Work being done out of proper sequence
- **Progress Visibility**: Lack of transparency in multi-agent workflows

### Solution Approach
A centralized coordination system that manages project state, work assignments, and resource locks while maintaining agent autonomy and enabling true parallel development.

## Core Architecture

### High-Level Design

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│     Agent 1     │    │     Agent 2     │    │     Agent N     │
│                 │    │                 │    │                 │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          │ MCP Protocol         │ MCP Protocol         │ MCP Protocol
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   Agent Coordinator     │
                    │      MCP Server         │
                    │                         │
                    │  ┌─────────────────┐    │
                    │  │  HTTP Server    │    │
                    │  │  (Port 8001)    │    │
                    │  └─────────────────┘    │
                    │  ┌─────────────────┐    │
                    │  │  Stdio Server   │    │
                    │  │  (Traditional)  │    │
                    │  └─────────────────┘    │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │     SQLite Database     │
                    │                         │
                    │  - Projects             │
                    │  - Tasks               │
                    │  - TodoItems           │
                    │  - Files & Locks       │
                    │  - Dependencies        │
                    └─────────────────────────┘
```

### Entity Relationship

```
Project (1) ──────── (N) Task (1) ──────── (N) TodoItem (N) ──────── (N) File
   │                     │                      │                      │
   │                     │                      │                      │
   ├─ name               ├─ name                ├─ title               ├─ path
   ├─ description        ├─ description         ├─ description         ├─ locked
   ├─ status             ├─ order               ├─ status              ├─ locked_by
   └─ audit_fields       ├─ dependencies        ├─ order               └─ audit_fields
                         ├─ status              ├─ dependencies
                         └─ audit_fields        └─ audit_fields
```

### 1. Projects
**Purpose**: Top-level organizational unit representing a complete codebase/repository

**Characteristics**:
- Unique name identification (typically project root directory)
- Contains multiple tasks
- Persistent "in_progress" status (represents ongoing development)
- Audit trail for creation and modification tracking

**Lifecycle**: Created once per codebase, persists indefinitely

### 2. Tasks
**Purpose**: Logical groupings of related work (analogous to development sprints)

**Characteristics**:
- Hierarchical ordering with dependency resolution
- Overarching goal definition in description
- Collection of related todo items
- Status progression: pending → in_progress → completed

**Dependencies**: Must complete prerequisite tasks before starting

### 3. Todo Items
**Purpose**: Atomic units of work assigned to individual agents

**Characteristics**:
- Specific, actionable work units
- File references for modification tracking
- Execution order within parent task
- Dependency chains for proper sequencing
- Status lifecycle: pending → in_progress → completed/cancelled

**Assignment**: One todo item per agent at any given time

### 4. Files
**Purpose**: Resource management and conflict prevention

**Characteristics**:
- Path-based identification
- Automatic locking mechanism
- Agent ownership tracking
- Lock lifecycle tied to todo item status

**Locking Rules**:
- Locked when todo item becomes "in_progress"
- Unlocked when todo item reaches "completed" or "cancelled"
- Prevents concurrent modification conflicts

## Agent Workflow Architecture

### Agent Lifecycle States

```
┌─────────────┐    get_instructions()    ┌─────────────┐
│    Start    │─────────────────────────▶│  Learning   │
└─────────────┘                          └──────┬──────┘
                                                 │ get_project()
                                                 ▼
┌─────────────┐    project exists        ┌─────────────┐
│   Working   │◀─────────────────────────│  Discovery  │
└──────┬──────┘                          └──────┬──────┘
       │                                        │ project missing
       │ get_next_todo_item()                   ▼
       │                                ┌─────────────┐
       │                                │  Planning   │
       │                                └──────┬──────┘
       │                                       │ create_project()
       │                                       │ create_task()
       │                                       │ create_todo_item()
       │                                       ▼
       └────────────────────────────────┌─────────────┐
                                        │   Ready     │
                                        └─────────────┘
```

### Workflow Patterns

#### New Project Initialization
1. **Discovery Phase**
   ```
   get_instructions() → get_project(name) → null
   ```

2. **Planning Phase**
   ```
   create_project(name, description)
   create_task(project_name, task_name, description, order, dependencies)
   create_todo_item(task_id, title, description, order, dependencies, files)
   ```

3. **Execution Phase**
   ```
   get_next_todo_item(project_name, agent_id)
   update_todo_status(todo_id, "in_progress", agent_id)
   [perform work]
   update_todo_status(todo_id, "completed", agent_id)
   ```

#### Joining Existing Project
1. **Context Acquisition**
   ```
   get_instructions() → get_project_status(project_name)
   ```

2. **Work Assignment**
   ```
   get_next_todo_item(project_name, agent_id)
   ```

3. **Execution**
   ```
   update_todo_status(todo_id, "in_progress", agent_id)
   [perform work]
   update_todo_status(todo_id, "completed", agent_id)
   ```

## File Locking Mechanism

### Automatic Lock Management

```
TodoItem Status Change:
pending → in_progress: Lock all referenced files
in_progress → completed: Unlock all referenced files
in_progress → cancelled: Unlock all referenced files
```

### Lock Resolution Algorithm

```python
def get_next_available_todo():
    for todo_item in ordered_todo_items:
        if todo_item.status != 'pending':
            continue
        
        # Check task dependencies
        if not all_task_dependencies_completed():
            continue
        
        # Check todo dependencies
        if not all_todo_dependencies_completed():
            continue
        
        # Check file locks
        if any_referenced_files_locked():
            continue
        
        return todo_item
    
    return None  # No available work
```

### Conflict Prevention

- **Proactive Locking**: Files locked before work begins
- **Dependency Enforcement**: Work order respects logical dependencies
- **Atomic Operations**: Status changes and lock operations are transactional
- **Agent Identification**: Lock ownership tracked for accountability

## API Design & Tools

### Core Management Tools

| Tool | Purpose | Critical Parameters |
|------|---------|-------------------|
| `get_instructions` | System onboarding | None |
| `create_project` | Project initialization | name, description |
| `get_project` | Project discovery | name |
| `get_project_status` | Comprehensive state | project_name |

### Work Coordination Tools

| Tool | Purpose | Critical Parameters |
|------|---------|-------------------|
| `create_task` | Sprint planning | project_name, order, dependencies |
| `create_todo_item` | Work breakdown | task_id, files, dependencies |
| `get_next_todo_item` | Work assignment | project_name, agent_id |
| `update_todo_status` | Progress tracking | todo_id, status, agent_id |

### Resource Management Tools

| Tool | Purpose | Critical Parameters |
|------|---------|-------------------|
| `check_file_locks` | Conflict prevention | files[] |
| `lock_files` | Manual locking | files[], agent_id |
| `unlock_files` | Manual unlocking | files[], agent_id |

### Advanced Planning Tools

| Tool | Purpose | Critical Parameters |
|------|---------|-------------------|
| `insert_todo_item` | Dynamic planning | task_id, after_todo_id |

## Use Cases & Scenarios

### Scenario 1: New Project Development
**Context**: Building a web application from scratch

**Agents**: 
- Agent A: Backend API development
- Agent B: Frontend UI components  
- Agent C: Database schema & migrations

**Workflow**:
1. Agent A initializes project with authentication task
2. Agent B joins, gets assigned frontend setup
3. Agent C handles database initialization
4. Dependency resolution ensures proper build order

### Scenario 2: Feature Development
**Context**: Adding payment processing to existing application

**Agents**:
- Agent X: Backend payment integration
- Agent Y: Frontend payment forms
- Agent Z: Database payment tables

**Workflow**:
1. Agent X creates payment feature task
2. Breaks down into: API endpoints, service layer, tests
3. Agent Y gets UI components (depends on API completion)
4. Agent Z handles schema changes (prerequisite for all)

### Scenario 3: Bug Fix Coordination
**Context**: Critical security vulnerability

**Agents**:
- Agent 1: Security patch implementation
- Agent 2: Test coverage addition
- Agent 3: Documentation updates

**Workflow**:
1. High-priority task created with ordered dependencies
2. Security fix implemented first
3. Tests added to validate fix
4. Documentation updated last
