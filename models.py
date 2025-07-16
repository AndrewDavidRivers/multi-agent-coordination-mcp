from datetime import datetime
from enum import Enum
from typing import Optional, List
from abc import ABC, abstractmethod

class Status(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class BaseModel(ABC):
    """Base model with common functionality"""
    def __init__(self, id: int):
        self.id = id
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, self.__class__):
            return False
        return self.id == other.id
    
    def __hash__(self) -> int:
        return hash((self.__class__.__name__, self.id))
    
    @abstractmethod
    def __str__(self) -> str:
        pass

class AuditableModel(BaseModel):
    """Model with audit trail"""
    def __init__(self, id: int, created_at: Optional[datetime] = None, updated_at: Optional[datetime] = None):
        super().__init__(id)
        now = datetime.now()
        self.created_at = created_at or now
        self.updated_at = updated_at or now
    
    def touch(self):
        """Update the updated_at timestamp"""
        self.updated_at = datetime.now()

class Project(AuditableModel):
    def __init__(self, id: int, name: str, description: str, 
                 status: Status = Status.PENDING, 
                 created_at: Optional[datetime] = None, 
                 updated_at: Optional[datetime] = None):
        super().__init__(id, created_at, updated_at)
        self.name = self._validate_name(name)
        self.description = description
        self.status = status
        self._tasks: List['Task'] = []
    
    def _validate_name(self, name: str) -> str:
        if not name or not name.strip():
            raise ValueError("Project name cannot be empty")
        return name.strip()
    
    @property
    def tasks(self) -> List['Task']:
        return self._tasks.copy()
    
    def add_task(self, task: 'Task'):
        if task not in self._tasks:
            self._tasks.append(task)
            task._project = self
            self.touch()
    
    def remove_task(self, task: 'Task'):
        if task in self._tasks:
            self._tasks.remove(task)
            task._project = None
            self.touch()
    
    @property
    def is_completed(self) -> bool:
        return self.status == Status.COMPLETED
    
    def complete(self):
        self.status = Status.COMPLETED
        self.touch()
    
    def cancel(self):
        self.status = Status.CANCELLED
        self.touch()
    
    def __str__(self) -> str:
        return f"Project({self.id}: {self.name} - {self.status.value})"
    
    def __repr__(self) -> str:
        return f"Project(id={self.id}, name='{self.name}', status={self.status})"

class File(AuditableModel):
    def __init__(self, id: int, path: str,
                 created_at: Optional[datetime] = None,
                 updated_at: Optional[datetime] = None):
        super().__init__(id, created_at, updated_at)
        self.path = self._validate_path(path)
        self._locked = False
        self._locked_by: Optional[str] = None
    
    def _validate_path(self, path: str) -> str:
        if not path or not path.strip():
            raise ValueError("File path cannot be empty")
        return path.strip()
    
    def lock(self, locked_by: str = "system"):
        """Lock the file with optional identifier of who locked it"""
        if self._locked:
            raise ValueError(f"File already locked by {self._locked_by}")
        self._locked = True
        self._locked_by = locked_by
        self.touch()
    
    def unlock(self, unlocked_by: Optional[str] = None):
        """Unlock the file with optional verification of who's unlocking"""
        if not self._locked:
            raise ValueError("File is not locked")
        if unlocked_by and self._locked_by != unlocked_by:
            raise ValueError(f"File locked by {self._locked_by}, cannot unlock by {unlocked_by}")
        self._locked = False
        self._locked_by = None
        self.touch()
    
    @property
    def is_locked(self) -> bool:
        return self._locked
    
    @property
    def locked_by(self) -> Optional[str]:
        return self._locked_by
    
    def __str__(self) -> str:
        lock_status = f" (locked by {self._locked_by})" if self._locked else ""
        return f"File({self.id}: {self.path}{lock_status})"
    
    def __repr__(self) -> str:
        return f"File(id={self.id}, path='{self.path}', locked={self._locked})"

class TodoItem(AuditableModel):
    def __init__(self, id: int, title: str, description: str = "",
                 status: Status = Status.PENDING,
                 files: Optional[List[File]] = None,
                 order: int = 0,
                 dependencies: Optional[List[int]] = None,
                 created_at: Optional[datetime] = None,
                 updated_at: Optional[datetime] = None):
        super().__init__(id, created_at, updated_at)
        self.title = self._validate_title(title)
        self.description = description
        self.status = status
        self.order = order
        self.dependencies = dependencies.copy() if dependencies else []
        self._files: List[File] = files.copy() if files else []
        self._task: Optional['Task'] = None
    
    def _validate_title(self, title: str) -> str:
        if not title or not title.strip():
            raise ValueError("TodoItem title cannot be empty")
        return title.strip()
    
    @property
    def files(self) -> List[File]:
        return self._files.copy()
    
    @property
    def task(self) -> Optional['Task']:
        return self._task
    
    def add_file(self, file: File):
        if file not in self._files:
            self._files.append(file)
            self.touch()
    
    def remove_file(self, file: File):
        if file in self._files:
            self._files.remove(file)
            self.touch()
    
    def contains_file(self, file: File) -> bool:
        return file in self._files
    
    @property
    def is_completed(self) -> bool:
        return self.status == Status.COMPLETED
    
    def complete(self):
        self.status = Status.COMPLETED
        self.touch()
    
    def start(self):
        self.status = Status.IN_PROGRESS
        self.touch()
    
    def cancel(self):
        self.status = Status.CANCELLED
        self.touch()
    
    def reopen(self):
        self.status = Status.PENDING
        self.touch()
    
    def __str__(self) -> str:
        return f"TodoItem({self.id}: {self.title} - {self.status.value})"
    
    def __repr__(self) -> str:
        return f"TodoItem(id={self.id}, title='{self.title}', status={self.status})"
    
    def can_start(self, completed_todo_ids: List[int]) -> bool:
        """Check if this todo item can be started based on its dependencies"""
        return all(dep_id in completed_todo_ids for dep_id in self.dependencies)
    
    def is_available(self, completed_todo_ids: List[int], in_progress_ids: List[int]) -> bool:
        """Check if this todo item is available to be picked up by an agent"""
        return (self.status == Status.PENDING and 
                self.can_start(completed_todo_ids) and 
                self.id not in in_progress_ids)

class Task(AuditableModel):
    def __init__(self, id: int, name: str, description: str = "",
                 project: Optional[Project] = None,
                 status: Status = Status.PENDING,
                 todo_items: Optional[List[TodoItem]] = None,
                 order: int = 0,
                 dependencies: Optional[List[int]] = None,
                 created_at: Optional[datetime] = None,
                 updated_at: Optional[datetime] = None):
        super().__init__(id, created_at, updated_at)
        self.name = self._validate_name(name)
        self.description = description
        self.status = status
        self.order = order
        self.dependencies = dependencies.copy() if dependencies else []
        self._project: Optional[Project] = None
        self._todo_items: List[TodoItem] = []
        
        # Set relationships
        if project:
            project.add_task(self)
        if todo_items:
            for item in todo_items:
                self.add_todo_item(item)
    
    def _validate_name(self, name: str) -> str:
        if not name or not name.strip():
            raise ValueError("Task name cannot be empty")
        return name.strip()
    
    @property
    def project(self) -> Optional[Project]:
        return self._project
    
    @property
    def todo_items(self) -> List[TodoItem]:
        return self._todo_items.copy()
    
    def add_todo_item(self, todo_item: TodoItem):
        if todo_item not in self._todo_items:
            self._todo_items.append(todo_item)
            todo_item._task = self
            self.touch()
    
    def remove_todo_item(self, todo_item: TodoItem):
        if todo_item in self._todo_items:
            self._todo_items.remove(todo_item)
            todo_item._task = None
            self.touch()
    
    def contains_todo_item(self, todo_item: TodoItem) -> bool:
        return todo_item in self._todo_items
    
    @property
    def is_completed(self) -> bool:
        return self.status == Status.COMPLETED
    
    @property
    def completion_percentage(self) -> float:
        if not self._todo_items:
            return 100.0 if self.is_completed else 0.0
        completed_count = sum(1 for item in self._todo_items if item.is_completed)
        return (completed_count / len(self._todo_items)) * 100.0
    
    def complete(self):
        self.status = Status.COMPLETED
        self.touch()
    
    def start(self):
        self.status = Status.IN_PROGRESS  
        self.touch()
    
    def cancel(self):
        self.status = Status.CANCELLED
        self.touch()
    
    def reopen(self):
        self.status = Status.PENDING
        self.touch()
    
    def __str__(self) -> str:
        return f"Task({self.id}: {self.name} - {self.status.value})"
    
    def __repr__(self) -> str:
        return f"Task(id={self.id}, name='{self.name}', status={self.status}, project={self.project.id if self.project else None})"
    
    def can_start(self, completed_task_ids: List[int]) -> bool:
        """Check if this task can be started based on its dependencies"""
        return all(dep_id in completed_task_ids for dep_id in self.dependencies)
    
    def get_available_todo_items(self, completed_todo_ids: List[int], in_progress_ids: List[int]) -> List[TodoItem]:
        """Get all todo items that are available to be worked on"""
        available = []
        for item in sorted(self._todo_items, key=lambda x: x.order):
            if item.is_available(completed_todo_ids, in_progress_ids):
                available.append(item)
        return available
    

    