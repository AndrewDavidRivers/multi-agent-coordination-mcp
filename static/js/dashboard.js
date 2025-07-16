class AgentCoordinatorDashboard {
    constructor() {
        this.websocket = null;
        this.currentProject = null;
        this.currentView = 'kanban'; // Track current view: 'kanban' or 'audit'
        this.projectsData = new Map();
        this.auditData = null;
        this.reconnectInterval = null;
        this.heartbeatInterval = null;

        this.init();
    }

    init() {
        this.setupEventListeners();
        this.connectWebSocket();
        this.loadDashboard();
    }

    setupEventListeners() {
        // Navigation
        document.getElementById('refreshBtn').addEventListener('click', () => {
            this.loadDashboard();
        });

        document.getElementById('backBtn').addEventListener('click', () => {
            this.showDashboard();
        });

        // Project view tabs
        document.getElementById('kanbanTab').addEventListener('click', () => {
            this.switchProjectView('kanban');
        });

        document.getElementById('auditTab').addEventListener('click', () => {
            this.switchProjectView('audit');
        });

        // Audit trail filters
        document.getElementById('eventTypeFilter').addEventListener('change', () => {
            this.filterAuditEvents();
        });

        document.getElementById('agentFilter').addEventListener('change', () => {
            this.filterAuditEvents();
        });

        document.getElementById('searchFilter').addEventListener('input', () => {
            this.filterAuditEvents();
        });

        document.getElementById('clearFilters').addEventListener('click', () => {
            this.clearAuditFilters();
        });

        // Modal
        document.getElementById('todoModalClose').addEventListener('click', () => {
            this.closeTodoModal();
        });

        document.getElementById('todoModal').addEventListener('click', (e) => {
            if (e.target.id === 'todoModal') {
                this.closeTodoModal();
            }
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.closeTodoModal();
            }
        });

        // Window events
        window.addEventListener('beforeunload', () => {
            if (this.websocket) {
                this.websocket.close();
            }
        });
    }

    // WebSocket Management
    connectWebSocket() {
        try {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/dashboard/ws`;

            this.websocket = new WebSocket(wsUrl);

            this.websocket.onopen = () => {
                console.log('WebSocket connected');
                this.updateConnectionStatus('connected');
                this.clearReconnectInterval();
                this.startHeartbeat();
            };

            this.websocket.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleWebSocketMessage(data);
                } catch (error) {
                    console.error('Error parsing WebSocket message:', error);
                }
            };

            this.websocket.onclose = () => {
                console.log('WebSocket disconnected');
                this.updateConnectionStatus('disconnected');
                this.stopHeartbeat();
                this.scheduleReconnect();
            };

            this.websocket.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.updateConnectionStatus('error');
            };

        } catch (error) {
            console.error('Failed to connect WebSocket:', error);
            this.updateConnectionStatus('error');
            this.scheduleReconnect();
        }
    }

    handleWebSocketMessage(data) {
        switch (data.type) {
            case 'project_created':
            case 'project_updated':
                this.refreshProject(data.project_name);
                break;

            case 'task_created':
            case 'task_updated':
                this.refreshProject(data.project_name);
                break;

            case 'todo_created':
            case 'todo_updated':
            case 'todo_status_changed':
                this.refreshProject(data.project_name);
                if (this.currentProject === data.project_name) {
                    this.loadProjectView(data.project_name);
                }
                break;

            case 'heartbeat':
                // Respond to server heartbeat
                this.sendWebSocketMessage({ type: 'heartbeat_response' });
                break;

            default:
                console.log('Unknown WebSocket message type:', data.type);
        }
    }

    sendWebSocketMessage(data) {
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            this.websocket.send(JSON.stringify(data));
        }
    }

    startHeartbeat() {
        this.heartbeatInterval = setInterval(() => {
            this.sendWebSocketMessage({ type: 'heartbeat' });
        }, 30000); // 30 seconds
    }

    stopHeartbeat() {
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
            this.heartbeatInterval = null;
        }
    }

    scheduleReconnect() {
        if (this.reconnectInterval) return;

        this.updateConnectionStatus('connecting');
        this.reconnectInterval = setInterval(() => {
            this.connectWebSocket();
        }, 5000); // Try to reconnect every 5 seconds
    }

    clearReconnectInterval() {
        if (this.reconnectInterval) {
            clearInterval(this.reconnectInterval);
            this.reconnectInterval = null;
        }
    }

    updateConnectionStatus(status) {
        const statusElement = document.getElementById('connectionStatus');
        const statusDot = statusElement.querySelector('.status-dot');
        const statusText = statusElement.querySelector('.status-text');

        statusDot.className = 'status-dot';
        switch (status) {
            case 'connected':
                statusDot.classList.add('connected');
                statusText.textContent = 'Connected';
                break;
            case 'connecting':
                statusDot.classList.add('connecting');
                statusText.textContent = 'Connecting...';
                break;
            case 'disconnected':
                statusDot.classList.add('disconnected');
                statusText.textContent = 'Disconnected';
                break;
            case 'error':
                statusDot.classList.add('disconnected');
                statusText.textContent = 'Connection Error';
                break;
        }
    }

    // API Methods
    async apiCall(endpoint, options = {}) {
        try {
            const response = await fetch(`/dashboard/api${endpoint}`, {
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                },
                ...options
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            return await response.json();
        } catch (error) {
            console.error(`API call failed for ${endpoint}:`, error);
            throw error;
        }
    }

    async loadDashboard() {
        try {
            this.showLoading();
            const data = await this.apiCall('/projects');

            this.projectsData.clear();
            data.projects.forEach(project => {
                this.projectsData.set(project.project.name, project);
            });

            this.renderProjects();
            this.updateGlobalStats();

        } catch (error) {
            this.showError('Failed to load dashboard data');
        } finally {
            this.hideLoading();
        }
    }

    async refreshProject(projectName) {
        try {
            const data = await this.apiCall(`/projects/${encodeURIComponent(projectName)}`);
            this.projectsData.set(projectName, data);

            // Update the project card if we're on dashboard
            if (this.isShowingDashboard()) {
                this.renderProjects();
            }

            this.updateGlobalStats();
        } catch (error) {
            console.error(`Failed to refresh project ${projectName}:`, error);
        }
    }

    async loadProjectView(projectName) {
        try {
            this.showLoading();
            const data = await this.apiCall(`/projects/${encodeURIComponent(projectName)}`);

            this.currentProject = projectName;
            this.projectsData.set(projectName, data);
            this.renderProjectView(data);
            this.showProjectView();

        } catch (error) {
            this.showError(`Failed to load project: ${projectName}`);
        } finally {
            this.hideLoading();
        }
    }

    // Rendering Methods
    renderProjects() {
        const container = document.getElementById('projectsGrid');
        const emptyState = document.getElementById('emptyState');

        if (this.projectsData.size === 0) {
            container.style.display = 'none';
            emptyState.style.display = 'block';
            return;
        }

        container.style.display = 'grid';
        emptyState.style.display = 'none';

        container.innerHTML = '';

        this.projectsData.forEach(project => {
            const card = this.createProjectCard(project);
            container.appendChild(card);
        });
    }

    createProjectCard(project) {
        const card = document.createElement('div');
        card.className = 'project-card';
        card.addEventListener('click', () => this.loadProjectView(project.project.name));

        const completion = project.overall_stats ? project.overall_stats.completion_percentage : 0;
        const totalTodos = project.overall_stats ? project.overall_stats.total_todos : 0;
        const inProgress = project.overall_stats ? project.overall_stats.in_progress_todos : 0;

        card.innerHTML = `
            <div class="project-card-header">
                <h3 class="project-name">${this.escapeHtml(project.project.name)}</h3>
                <div class="project-status ${project.project.status}"></div>
            </div>
            <p class="project-description">${this.escapeHtml(project.project.description)}</p>
            <div class="project-metrics">
                <div class="project-progress">
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: ${completion}%"></div>
                    </div>
                </div>
                <div class="project-stats">
                    <div class="stat-badge">
                        <span class="stat-value">${totalTodos}</span>
                        <span class="stat-label">todos</span>
                    </div>
                    <div class="stat-badge">
                        <span class="stat-value">${inProgress}</span>
                        <span class="stat-label">active</span>
                    </div>
                </div>
            </div>
        `;

        return card;
    }

    renderProjectView(projectData) {
        document.getElementById('projectTitle').textContent = projectData.project.name;
        document.getElementById('projectDescription').textContent = projectData.project.description;

        const completion = projectData.overall_stats.completion_percentage;
        document.getElementById('projectCompletion').textContent = `${completion}%`;

        // Reset to kanban view when loading project
        this.currentView = 'kanban';
        document.getElementById('kanbanTab').classList.add('active');
        document.getElementById('auditTab').classList.remove('active');
        document.getElementById('kanbanView').style.display = 'block';
        document.getElementById('auditTrailView').style.display = 'none';

        this.renderKanbanBoard(projectData.tasks);
    }

    renderKanbanBoard(tasks) {
        const board = document.getElementById('kanbanBoard');
        board.innerHTML = '';

        if (!tasks || tasks.length === 0) {
            board.innerHTML = '<div class="empty-state"><p>No tasks yet in this project.</p></div>';
            return;
        }

        tasks.forEach(task => {
            const column = this.createTaskColumn(task);
            board.appendChild(column);
        });
    }

    createTaskColumn(task) {
        const column = document.createElement('div');
        column.className = 'task-column';

        const todoItems = task.todo_items || [];
        const description = task.description || '';
        const isExpanded = description.length <= 100;

        column.innerHTML = `
            <div class="task-header">
                <h3 class="task-name">
                    ${this.escapeHtml(task.name)}
                    <div class="task-status ${task.status}"></div>
                </h3>
                <div class="task-description ${isExpanded ? 'expanded' : ''}" onclick="this.classList.toggle('expanded')">
                    ${this.escapeHtml(description)}
                </div>
                <div class="task-stats">
                    <span>${task.completed_todos}/${task.total_todos} completed</span>
                    <span>${task.completion_percentage}%</span>
                </div>
            </div>
            <div class="todos-list" id="todos-${task.id}">
                ${todoItems.map(todo => this.createTodoCard(todo)).join('')}
            </div>
        `;

        return column;
    }

    createTodoCard(todo) {
        const files = todo.files || [];
        const filesDisplay = files.length > 0 ? `📁 ${files.length}` : '';
        const agent = todo.assigned_agent ? todo.assigned_agent : '';

        return `
            <div class="todo-card ${todo.status}" onclick="dashboard.showTodoModal(${todo.id})">
                <div class="todo-header">
                    <h4 class="todo-title">${this.escapeHtml(todo.title)}</h4>
                    <span class="todo-status-badge ${todo.status}">${this.formatStatus(todo.status)}</span>
                </div>
                <p class="todo-description">${this.escapeHtml(todo.description || '')}</p>
                <div class="todo-footer">
                    <span class="todo-files">${filesDisplay}</span>
                    <span class="todo-agent">${agent}</span>
                </div>
            </div>
        `;
    }

    // Modal Methods
    async showTodoModal(todoId) {
        try {
            // Find the todo in current project data
            const projectData = this.projectsData.get(this.currentProject);
            let todo = null;

            for (const task of projectData.tasks) {
                const found = task.todo_items.find(t => t.id === todoId);
                if (found) {
                    todo = found;
                    break;
                }
            }

            if (!todo) {
                throw new Error('Todo not found');
            }

            this.populateTodoModal(todo);
            this.openTodoModal();

        } catch (error) {
            this.showError('Failed to load todo details');
        }
    }

    populateTodoModal(todo) {
        document.getElementById('todoModalTitle').textContent = todo.title;
        document.getElementById('todoModalDescription').textContent = todo.description || 'No description provided.';

        const statusBadge = document.getElementById('todoModalStatus');
        statusBadge.textContent = this.formatStatus(todo.status);
        statusBadge.className = `status-badge todo-status-badge ${todo.status}`;

        // Files
        const filesSection = document.getElementById('todoModalFilesSection');
        const filesList = document.getElementById('todoModalFiles');
        if (todo.files && todo.files.length > 0) {
            filesSection.style.display = 'block';
            filesList.innerHTML = todo.files.map(file => `<li>${this.escapeHtml(file)}</li>`).join('');
        } else {
            filesSection.style.display = 'none';
        }

        // Dependencies
        const depsSection = document.getElementById('todoModalDependenciesSection');
        const depsList = document.getElementById('todoModalDependencies');
        if (todo.dependencies && todo.dependencies.length > 0) {
            depsSection.style.display = 'block';
            depsList.innerHTML = todo.dependencies.map(dep => `<li>Todo ID: ${dep}</li>`).join('');
        } else {
            depsSection.style.display = 'none';
        }

        // Agent
        const agentSection = document.getElementById('todoModalAgentSection');
        const agentElement = document.getElementById('todoModalAgent');
        if (todo.assigned_agent) {
            agentSection.style.display = 'block';
            agentElement.textContent = todo.assigned_agent;
        } else {
            agentSection.style.display = 'none';
        }

        // Timestamps
        document.getElementById('todoModalCreated').textContent = this.formatDate(todo.created_at);
        document.getElementById('todoModalUpdated').textContent = this.formatDate(todo.updated_at);
    }

    openTodoModal() {
        const modal = document.getElementById('todoModal');
        modal.style.display = 'flex';
        // Trigger animation
        setTimeout(() => modal.classList.add('show'), 10);
    }

    closeTodoModal() {
        const modal = document.getElementById('todoModal');
        modal.classList.remove('show');
        setTimeout(() => modal.style.display = 'none', 300);
    }

    // View Management
    showDashboard() {
        document.getElementById('dashboardView').style.display = 'block';
        document.getElementById('projectView').style.display = 'none';
        this.currentProject = null;
        this.currentView = 'kanban';
    }

    showProjectView() {
        document.getElementById('dashboardView').style.display = 'none';
        document.getElementById('projectView').style.display = 'block';
    }

    isShowingDashboard() {
        return document.getElementById('dashboardView').style.display !== 'none';
    }

    switchProjectView(view) {
        this.currentView = view;

        // Update tab buttons
        document.getElementById('kanbanTab').classList.toggle('active', view === 'kanban');
        document.getElementById('auditTab').classList.toggle('active', view === 'audit');

        // Update view containers
        document.getElementById('kanbanView').style.display = view === 'kanban' ? 'block' : 'none';
        document.getElementById('auditTrailView').style.display = view === 'audit' ? 'block' : 'none';

        // Load audit trail data if switching to audit view
        if (view === 'audit' && this.currentProject) {
            this.loadAuditTrail(this.currentProject);
        }
    }

    // Audit Trail Methods
    async loadAuditTrail(projectName) {
        try {
            this.showLoading();
            const data = await this.apiCall(`/projects/${encodeURIComponent(projectName)}/audit`);

            this.auditData = data;
            this.populateAgentFilter(data.audit_events);
            this.renderAuditTrail(data);

        } catch (error) {
            console.error('Failed to load audit trail:', error);
            this.showError(`Failed to load audit trail: ${error.message}`);
        } finally {
            this.hideLoading();
        }
    }

    populateAgentFilter(auditEvents) {
        const agentSelect = document.getElementById('agentFilter');
        const agents = new Set();

        auditEvents.forEach(event => {
            if (event.agent_id) {
                agents.add(event.agent_id);
            }
        });

        // Clear existing options (except "All Agents")
        while (agentSelect.children.length > 1) {
            agentSelect.removeChild(agentSelect.lastChild);
        }

        // Add agent options
        agents.forEach(agent => {
            const option = document.createElement('option');
            option.value = agent;
            option.textContent = agent;
            agentSelect.appendChild(option);
        });
    }

    renderAuditTrail(data) {
        const timeline = document.getElementById('auditTimeline');
        const emptyState = document.getElementById('auditEmptyState');

        if (!data.audit_events || data.audit_events.length === 0) {
            timeline.style.display = 'none';
            emptyState.style.display = 'block';
            return;
        }

        timeline.style.display = 'block';
        emptyState.style.display = 'none';

        this.renderAuditEvents(data.audit_events);
    }

    renderAuditEvents(events) {
        const timeline = document.getElementById('auditTimeline');
        timeline.innerHTML = '';

        events.forEach(event => {
            const eventElement = this.createAuditEventElement(event);
            timeline.appendChild(eventElement);
        });
    }

    createAuditEventElement(event) {
        const eventDiv = document.createElement('div');
        eventDiv.className = `audit-event audit-event-${event.event_type}`;

        const timestamp = this.formatDate(event.created_at);
        const eventIcon = this.getEventIcon(event.event_type);
        const description = this.formatEventDescription(event);

        eventDiv.innerHTML = `
            <div class="audit-event-icon">${eventIcon}</div>
            <div class="audit-event-content">
                <div class="audit-event-header">
                    <span class="audit-event-type">${this.formatEventType(event.event_type)}</span>
                    <span class="audit-event-time">${timestamp}</span>
                </div>
                <div class="audit-event-description">${description}</div>
                ${event.agent_id ? `<div class="audit-event-agent">👤 ${event.agent_id}</div>` : ''}
                ${event.details ? this.formatEventDetails(event.details) : ''}
            </div>
        `;

        return eventDiv;
    }

    getEventIcon(eventType) {
        const icons = {
            'project_created': '🏗️',
            'task_created': '📋',
            'todo_created': '✅',
            'status_change': '🔄',
            'file_lock': '🔒',
            'file_unlock': '🔓',
            'assignment': '👤',
            'project_updated': '📝',
            'task_updated': '📝',
            'todo_updated': '📝'
        };
        return icons[eventType] || '📝';
    }

    formatEventType(eventType) {
        return eventType.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    }

    formatEventDescription(event) {
        const { event_type, entity_type, entity_name, old_status, new_status, task_name } = event;

        switch (event_type) {
            case 'project_created':
                return `Project <strong>${entity_name}</strong> was created`;
            case 'task_created':
                return `Task <strong>${entity_name}</strong> was created`;
            case 'todo_created':
                return `Todo <strong>${entity_name}</strong> was created${task_name ? ` in task <strong>${task_name}</strong>` : ''}`;
            case 'status_change':
                return `${entity_type} <strong>${entity_name}</strong> status changed from <span class="status-${old_status}">${this.formatStatus(old_status)}</span> to <span class="status-${new_status}">${this.formatStatus(new_status)}</span>`;
            case 'file_lock':
                return `Files locked for <strong>${entity_name}</strong>`;
            case 'file_unlock':
                return `Files unlocked for <strong>${entity_name}</strong>`;
            case 'assignment':
                return `<strong>${entity_name}</strong> was assigned`;
            default:
                return `${this.formatEventType(event_type)} on <strong>${entity_name}</strong>`;
        }
    }

    formatEventDetails(details) {
        if (!details || typeof details !== 'object') return '';

        let html = '<div class="audit-event-details">';

        if (details.files && details.files.length > 0) {
            html += `<div class="detail-item"><strong>Files:</strong> ${details.files.join(', ')}</div>`;
        }

        if (details.dependencies && details.dependencies.length > 0) {
            html += `<div class="detail-item"><strong>Dependencies:</strong> ${details.dependencies.join(', ')}</div>`;
        }

        html += '</div>';
        return html;
    }

    filterAuditEvents() {
        if (!this.auditData || !this.auditData.audit_events) return;

        const eventTypeFilter = document.getElementById('eventTypeFilter').value;
        const agentFilter = document.getElementById('agentFilter').value;
        const searchFilter = document.getElementById('searchFilter').value.toLowerCase();

        const filteredEvents = this.auditData.audit_events.filter(event => {
            // Event type filter
            if (eventTypeFilter && event.event_type !== eventTypeFilter) return false;

            // Agent filter
            if (agentFilter && event.agent_id !== agentFilter) return false;

            // Search filter
            if (searchFilter) {
                const searchText = `${event.entity_name} ${event.event_type} ${event.task_name || ''}`.toLowerCase();
                if (!searchText.includes(searchFilter)) return false;
            }

            return true;
        });

        this.renderAuditEvents(filteredEvents);
    }

    clearAuditFilters() {
        document.getElementById('eventTypeFilter').value = '';
        document.getElementById('agentFilter').value = '';
        document.getElementById('searchFilter').value = '';

        if (this.auditData && this.auditData.audit_events) {
            this.renderAuditEvents(this.auditData.audit_events);
        }
    }

    // UI State Management
    showLoading() {
        document.body.classList.add('loading');
    }

    hideLoading() {
        document.body.classList.remove('loading');
    }

    showError(message) {
        // Simple error display - could be enhanced with a toast system
        console.error('Dashboard Error:', message);
        alert(message); // For now, using alert. In production, use a proper notification system
    }

    updateGlobalStats() {
        let totalProjects = this.projectsData.size;
        let activeTodos = 0;
        let activeAgents = new Set();

        this.projectsData.forEach(project => {
            if (project.overall_stats) {
                activeTodos += project.overall_stats.in_progress_todos;
            }

            if (project.tasks) {
                project.tasks.forEach(task => {
                    if (task.todo_items) {
                        task.todo_items.forEach(todo => {
                            if (todo.assigned_agent) {
                                activeAgents.add(todo.assigned_agent);
                            }
                        });
                    }
                });
            }
        });

        document.getElementById('totalProjects').textContent = totalProjects;
        document.getElementById('activeTodos').textContent = activeTodos;
        document.getElementById('activeAgents').textContent = activeAgents.size;
    }

    // Utility Methods
    escapeHtml(unsafe) {
        if (typeof unsafe !== 'string') return unsafe;
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    formatStatus(status) {
        return status.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    }

    formatDate(dateString) {
        if (!dateString) return 'N/A';
        try {
            const date = new Date(dateString);
            return date.toLocaleString();
        } catch {
            return dateString;
        }
    }
}

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new AgentCoordinatorDashboard();
});

// Make it available globally for onclick handlers
window.dashboard = null; 