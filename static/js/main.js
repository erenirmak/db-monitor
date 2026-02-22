// Initialize Socket.IO connection
const socket = io();

// Global 401/403 handler — redirect to login if session expired, show error if forbidden
const _originalFetch = window.fetch;
window.fetch = async function (...args) {
    const response = await _originalFetch.apply(this, args);
    if (response.status === 401) {
        window.location.href = '/login';
        throw new Error('Session expired — redirecting to login');
    }
    if (response.status === 403) {
        try {
            const data = await response.clone().json();
            if (data.error) {
                showMessage(data.error, 'danger');
            }
        } catch (e) {
            showMessage('Access denied (403 Forbidden)', 'danger');
        }
    }
    return response;
};

let databases = {};
let currentDatabase = null;
let currentSchema = null;
let currentTable = null;
let currentConnectionForm = {};
let addConnectionModal = null;

// Database Configuration Templates
const DATABASE_CONFIGS = {
    postgresql: {
        displayName: 'PostgreSQL',
        fields: [
            { name: 'host', label: 'Host', type: 'text', placeholder: 'localhost', required: true },
            { name: 'port', label: 'Port', type: 'number', placeholder: '5432', required: true, default: 5432 },
            { name: 'username', label: 'Username', type: 'text', required: true },
            { name: 'password', label: 'Password', type: 'password', required: true },
            { name: 'database', label: 'Database Name', type: 'text', required: true }
        ]
    },
    mysql: {
        displayName: 'MySQL / MariaDB',
        fields: [
            { name: 'host', label: 'Host', type: 'text', placeholder: 'localhost', required: true },
            { name: 'port', label: 'Port', type: 'number', placeholder: '3306', required: true, default: 3306 },
            { name: 'username', label: 'Username', type: 'text', required: true },
            { name: 'password', label: 'Password', type: 'password', required: true },
            { name: 'database', label: 'Database Name', type: 'text', required: true }
        ]
    },
    mssql: {
        displayName: 'SQL Server',
        fields: [
            { name: 'host', label: 'Server', type: 'text', placeholder: 'localhost\\SQLEXPRESS', required: true },
            { name: 'port', label: 'Port', type: 'number', placeholder: '1433', required: false, default: 1433 },
            { name: 'username', label: 'Username', type: 'text', required: true },
            { name: 'password', label: 'Password', type: 'password', required: true },
            { name: 'database', label: 'Database Name', type: 'text', required: true }
        ]
    },
    oracle: {
        displayName: 'Oracle',
        fields: [
            { name: 'host', label: 'Host', type: 'text', placeholder: 'localhost', required: true },
            { name: 'port', label: 'Port', type: 'number', placeholder: '1521', required: true, default: 1521 },
            { name: 'username', label: 'Username', type: 'text', required: true },
            { name: 'password', label: 'Password', type: 'password', required: true },
            { name: 'database', label: 'Service Name / SID', type: 'text', required: true }
        ]
    },
    sqlite: {
        displayName: 'SQLite',
        fields: [
            { name: 'filePath', label: 'File Path', type: 'text', placeholder: './data/database.db', required: true, help: 'Local path to SQLite file' }
        ]
    },
    mongodb: {
        displayName: 'MongoDB',
        fields: [
            { name: 'host', label: 'Host', type: 'text', placeholder: 'localhost', required: true },
            { name: 'port', label: 'Port', type: 'number', placeholder: '27017', required: true, default: 27017 },
            { name: 'username', label: 'Username', type: 'text', required: false },
            { name: 'password', label: 'Password', type: 'password', required: false },
            { name: 'database', label: 'Database Name', type: 'text', required: true }
        ]
    },
    opensearch: {
        displayName: 'OpenSearch',
        fields: [
            { name: 'host', label: 'Host', type: 'text', placeholder: 'localhost', required: true },
            { name: 'port', label: 'Port', type: 'number', placeholder: '9200', required: true, default: 9200 },
            { name: 'username', label: 'Username', type: 'text', required: false },
            { name: 'password', label: 'Password', type: 'password', required: false }
        ]
    },
    elasticsearch: {
        displayName: 'Elasticsearch',
        fields: [
            { name: 'host', label: 'Host', type: 'text', placeholder: 'localhost', required: true },
            { name: 'port', label: 'Port', type: 'number', placeholder: '9200', required: true, default: 9200 },
            { name: 'username', label: 'Username', type: 'text', required: false },
            { name: 'password', label: 'Password', type: 'password', required: false }
        ]
    }
};

// Socket.IO Events
window.onlineUsers = [];

socket.on('connect', function() {
    console.log('Connected to server');
    loadDatabases();
});

socket.on('online_users_update', function(data) {
    window.onlineUsers = data.online_users || [];
    // If the user management modal is open, re-render the table to show online status
    const userManagementModal = document.getElementById('userManagementModal');
    if (userManagementModal && userManagementModal.classList.contains('show')) {
        loadUsers();
    }
});

socket.on('db_status_update', function(data) {
    console.log('Database status update:', data);
    updateDatabaseStatus(data.db_key, data.status);
});

socket.on('disconnect', function() {
    console.log('Disconnected from server');
});

// Load databases on page load
document.addEventListener('DOMContentLoaded', function() {
    loadDatabases();
    initializeEventHandlers();

    // Periodically request status updates for our databases
    setInterval(() => {
        Object.keys(databases).forEach(dbKey => {
            socket.emit('check_status', dbKey);
        });
    }, 5000);
});

// Initialize Event Handlers
function initializeEventHandlers() {
    const addConnectionBtn = document.getElementById('addConnectionBtn');
    const addFolderBtn = document.getElementById('addFolderBtn');
    const refreshBtn = document.getElementById('refreshBtn');
    const searchBtn = document.getElementById('searchBtn');
    const databaseTypeSelect = document.getElementById('databaseType');
    const testConnectionBtn = document.getElementById('testConnectionBtn');
    const saveConnectionBtn = document.getElementById('saveConnectionBtn');
    const searchInput = document.getElementById('searchInput');

    // Sidebar Toggle Logic
    const toggleSidebarBtn = document.getElementById('sidebarToggleBtn');
    const closeSidebarBtn = document.getElementById('sidebarCloseBtn');

    function toggleSidebar() {
        const sidebar = document.getElementById('sidebarPanel');
        const appLayout = document.querySelector('.app-layout');

        sidebar.classList.toggle('collapsed');
        appLayout.classList.toggle('sidebar-collapsed');
    }

    if (toggleSidebarBtn) {
        toggleSidebarBtn.addEventListener('click', toggleSidebar);
    }

    if (closeSidebarBtn) {
        closeSidebarBtn.addEventListener('click', toggleSidebar);
    }

    // Sidebar Resize Logic
    const sidebarResizer = document.getElementById('sidebarResizer');
    if (sidebarResizer) {
        const sidebar = document.getElementById('sidebarPanel');
        let isResizing = false;
        let startX = 0;
        let startWidth = 0;

        const startResize = (e) => {
            isResizing = true;
            startX = e.clientX;
            startWidth = sidebar.getBoundingClientRect().width;

            sidebar.classList.add('resizing');
            sidebarResizer.classList.add('active');
            document.body.style.cursor = 'col-resize';

            // Prevent selection
            document.body.style.userSelect = 'none';

            document.addEventListener('mousemove', handleResize);
            document.addEventListener('mouseup', stopResize);
        };

        const handleResize = (e) => {
            if (!isResizing) return;
            // Calculate new width
            const currentX = e.clientX;
            const diffX = currentX - startX;
            const newWidth = Math.max(160, Math.min(600, startWidth + diffX)); // Min 160px, Max 600px

            // Apply via CSS variable on the element style
            sidebar.style.setProperty('--sidebar-width', `${newWidth}px`);
        };

        const stopResize = () => {
            isResizing = false;
            sidebar.classList.remove('resizing');
            sidebarResizer.classList.remove('active');
            document.body.style.cursor = '';
            document.body.style.userSelect = '';

            document.removeEventListener('mousemove', handleResize);
            document.removeEventListener('mouseup', stopResize);
        };

        sidebarResizer.addEventListener('mousedown', startResize);
    }

    // Add Connection Button
    if (addConnectionBtn) {
        addConnectionBtn.addEventListener('click', function() {
            addConnectionModal = new bootstrap.Modal(document.getElementById('addConnectionModal'));
            resetConnectionForm();
            addConnectionModal.show();
        });
    }

    // Add Folder Button
    if (addFolderBtn) {
        addFolderBtn.addEventListener('click', async function() {
            const folderName = prompt("Enter folder name:");
            if (folderName && folderName.trim()) {
                // We create a "placeholder" connection for the folder
                // This is a bit of a hack: an empty folder is just a connection with type 'folder'
                try {
                    await fetch('/api/save-connection', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            name: folderName.trim(),
                            type: 'folder',
                            fields: {},
                            group: folderName.trim()
                        })
                    });
                    loadDatabases();
                } catch(e) { console.error(e); }
            }
        });
    }

    // Refresh Button
    refreshBtn.addEventListener('click', function() {
        loadDatabases();
        showMessage('Databases refreshed', 'success');
    });

    // Search Button
    searchBtn.addEventListener('click', function() {
        const searchBox = document.getElementById('searchBox');
        if (searchBox.style.display === 'none') {
            searchBox.style.display = 'block';
            searchInput.focus();
        } else {
            searchBox.style.display = 'none';
            document.getElementById('searchInput').value = '';
            renderDatabaseList();
        }
    });

    // Search Input
    searchInput.addEventListener('input', function(e) {
        const searchTerm = e.target.value.toLowerCase();
        filterDatabases(searchTerm);
    });

    // Database Type Change
    databaseTypeSelect.addEventListener('change', function() {
        const selectedType = this.value;
        if (selectedType) {
            renderDynamicFields(selectedType);
        }
    });

    // Test Connection Button
    testConnectionBtn.addEventListener('click', testConnection);

    // Save Connection Button
    if (window.USER_PERMISSIONS.includes('manage_connections')) {
        saveConnectionBtn.addEventListener('click', saveConnection);
    } else {
        saveConnectionBtn.style.display = 'none';
        testConnectionBtn.style.display = 'none';
    }
}

// Render Dynamic Form Fields Based on Database Type
function renderDynamicFields(databaseType) {
    const container = document.getElementById('dynamicFieldsContainer');
    const config = DATABASE_CONFIGS[databaseType];

    if (!config) {
        container.innerHTML = '';
        return;
    }

    let html = '<div class="form-group-section"><div class="form-row full">';

    config.fields.forEach((field, index) => {
        const isRequired = field.required ? ' required' : '';
        const requiredLabel = field.required ? '<span class="text-danger">*</span>' : '';
        const helpText = field.help ? `<small class="form-text text-muted">${field.help}</small>` : '';

        html += `
            <div class="mb-3">
                <label for="field_${field.name}" class="form-label">${field.label} ${requiredLabel}</label>
                <input type="${field.type}"
                       class="form-control"
                       id="field_${field.name}"
                       placeholder="${field.placeholder || ''}"
                       value="${field.default || ''}"
                       ${isRequired}>
                ${helpText}
            </div>
        `;
    });

    html += '</div></div>';
    container.innerHTML = html;

    // Save current database type fields
    currentConnectionForm.fields = config.fields;
}

// Reset Connection Form
function resetConnectionForm() {
    document.getElementById('connectionForm').reset();
    document.getElementById('connectionId').value = ''; // Clear ID
    document.getElementById('addConnectionModalLabel').textContent = 'Add New Database Connection';
    document.getElementById('dynamicFieldsContainer').innerHTML = '';
    document.getElementById('connectionMessage').style.display = 'none';
    const extraJsonEl = document.getElementById('extraJson');
    if (extraJsonEl) extraJsonEl.value = '';

    // Hide delete button by default
    const deleteBtn = document.getElementById('deleteConnectionBtn');
    if (deleteBtn) {
        deleteBtn.style.display = 'none';
        deleteBtn.onclick = null;
    }

    currentConnectionForm = {};
}

// Edit Connection
function editConnection(dbKey) {
    const db = databases[dbKey];
    if (!db) return;

    // Open modal
    addConnectionModal = new bootstrap.Modal(document.getElementById('addConnectionModal'));
    resetConnectionForm();

    // Set title and ID
    document.getElementById('addConnectionModalLabel').textContent = 'Edit Connection';
    document.getElementById('connectionId').value = dbKey;
    document.getElementById('connectionName').value = db.name;
    document.getElementById('groupName').value = db.group || '';

    // Show delete button
    const deleteBtn = document.getElementById('deleteConnectionBtn');
    if (deleteBtn) {
        const canEdit = window.USER_PERMISSIONS.includes('manage_connections');
        deleteBtn.style.display = canEdit ? 'inline-block' : 'none';
        deleteBtn.onclick = async function() {
            if (!confirm(`Are you sure you want to delete the connection "${db.name}"?`)) {
                return;
            }
            try {
                const response = await fetch(`/api/disconnect/${dbKey}`, { method: 'POST' });
                const result = await response.json();

                if (result.success) {
                    // Close modal immediately
                    const modal = bootstrap.Modal.getInstance(document.getElementById('addConnectionModal'));
                    if (modal) modal.hide();

                    showMessage('Connection deleted', 'success');

                    // Clear UI if we deleted the active DB
                    if (currentDatabase === dbKey) {
                        currentDatabase = null;
                        document.getElementById('explorerContent').innerHTML =
                            '<div class="empty-state"><p class="text-muted"><i class="fas fa-arrow-left"></i> Select a database from the left sidebar</p></div>';
                        document.getElementById('editorContent').innerHTML =
                            '<div class="welcome-message"><h6>Welcome to Database Monitor</h6><p>Connection removed. Select another database to continue.</p></div>';
                    }
                    loadDatabases();
                } else {
                    alert(result.error || 'Failed to delete');
                }
            } catch (e) {
                console.error(e);
                alert('Error deleting connection');
            }
        };
    }

    // Set Type (trigger change to render fields)
    const typeSelect = document.getElementById('databaseType');
    typeSelect.value = db.engine;

    // Trigger rendering of dynamic fields
    renderDynamicFields(db.engine);

    // Pre-fill existing fields
    if (db.fields) {
        Object.keys(db.fields).forEach(key => {
            const input = document.getElementById(`field_${key}`);
            if (input) {
                // Determine value. If it's a password field, backend sends empty string.
                // We leave it empty so placeholder can show "Leave blank to keep unchanged"
                if (input.type === 'password') {
                     input.placeholder = "Leave blank to keep unchanged";
                } else {
                     input.value = db.fields[key] || '';
                }
            }
        });
    }

    // Populate Extra JSON if available
    const extraJsonEl = document.getElementById('extraJson');
    if (extraJsonEl && db.extra_json) {
         try {
             // Beautify JSON for editing
             extraJsonEl.value = JSON.stringify(db.extra_json, null, 2);
         } catch(e) { /* ignore */ }
    }

    // I will add a nice message about password.
    showConnectionMessage('Passwords are hidden. Leave password field blank to keep current password.', 'info');

    addConnectionModal.show();
}

// Collect the Extra JSON textarea value
function getExtraJson() {
    const el = document.getElementById('extraJson');
    return el ? el.value.trim() : '';
}

// Quick client-side validation of the Extra JSON field
function validateExtraJson() {
    const raw = getExtraJson();
    if (!raw) return true; // empty is fine
    try {
        const parsed = JSON.parse(raw);
        if (typeof parsed !== 'object' || Array.isArray(parsed)) {
            showConnectionMessage('Extra JSON must be a JSON object (e.g. { ... })', 'error');
            return false;
        }
        return true;
    } catch (e) {
        showConnectionMessage(`Invalid Extra JSON: ${e.message}`, 'error');
        return false;
    }
}

// Test Connection
async function testConnection() {
    const connectionType = document.getElementById('databaseType').value;

    if (!connectionType) {
        showConnectionMessage('Please select a database type', 'error');
        return;
    }

    if (!validateExtraJson()) return;

    const connectionData = {
        type: connectionType,
        fields: {},
        extra_json: getExtraJson()
    };

    // Collect form data
    const config = DATABASE_CONFIGS[connectionType];
    config.fields.forEach(field => {
        const value = document.getElementById(`field_${field.name}`).value;
        if (field.required && !value) {
            showConnectionMessage(`${field.label} is required`, 'error');
            return;
        }
        connectionData.fields[field.name] = value;
    });

    showConnectionMessage('Testing connection...', 'info');

    try {
        const response = await fetch('/api/test-connection', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(connectionData)
        });

        const result = await response.json();

        if (result.success) {
            showConnectionMessage('✓ Connection successful!', 'success');
        } else {
            showConnectionMessage(`✗ Connection failed: ${result.error || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        console.error('Error testing connection:', error);
        showConnectionMessage(`✗ Error: ${error.message}`, 'error');
    }
}

// Save Connection
async function saveConnection() {
    const connectionName = document.getElementById('connectionName').value;
    const connectionType = document.getElementById('databaseType').value;
    const connectionId = document.getElementById('connectionId').value;

    if (!connectionName) {
        showConnectionMessage('Please enter a connection name', 'error');
        return;
    }

    if (!connectionType) {
        showConnectionMessage('Please select a database type', 'error');
        return;
    }

    if (!validateExtraJson()) return;

    // Get Group
    const groupNameEl = document.getElementById('groupName');
    const groupName = groupNameEl ? groupNameEl.value.trim() : '';

    const connectionData = {
        name: connectionName,
        type: connectionType,
        fields: {},
        extra_json: getExtraJson(),
        group: groupName,
        id: connectionId || null
    };

    // Collect form data
    const config = DATABASE_CONFIGS[connectionType];
    let isValid = true;

    config.fields.forEach(field => {
        const input = document.getElementById(`field_${field.name}`);
        const value = input.value;

        // Skip validation for password if updating (it might be empty to keep old value)
        if (connectionId && field.type === 'password' && !value) {
            // It's allowed to be empty
        } else if (field.required && !value) {
            showConnectionMessage(`${field.label} is required`, 'error');
            isValid = false;
            return;
        }
        connectionData.fields[field.name] = value;
    });

    if (!isValid) return;

    showConnectionMessage('Saving connection...', 'info');

    try {
        const response = await fetch('/api/save-connection', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(connectionData)
        });

        const result = await response.json();

        if (result.success) {
            showConnectionMessage('✓ Connection saved successfully!', 'success');
            setTimeout(() => {
                addConnectionModal.hide();
                loadDatabases();
            }, 1000);
        } else {
            showConnectionMessage(`✗ Failed to save: ${result.error || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        console.error('Error saving connection:', error);
        showConnectionMessage(`✗ Error: ${error.message}`, 'error');
    }
}

// Show Connection Message
function showConnectionMessage(message, type) {
    const messageDiv = document.getElementById('connectionMessage');
    const icon = type === 'success' ? 'fa-check-circle' : type === 'error' ? 'fa-times-circle' : 'fa-info-circle';
    messageDiv.innerHTML = `<i class="fas ${icon}"></i> ${message}`;
    messageDiv.className = `mt-3 ${type}`;
    messageDiv.style.display = 'block';
}

// Filter Databases by Search Term
function filterDatabases(searchTerm) {
    const databaseList = document.getElementById('databaseList');
    const items = databaseList.querySelectorAll('.database-item');

    items.forEach(item => {
        const name = item.textContent.toLowerCase();
        if (name.includes(searchTerm)) {
            item.style.display = 'block';
        } else {
            item.style.display = 'none';
        }
    });
}

// Disconnect from Database
async function disconnectDatabase(dbKey, event) {
    if (event) event.stopPropagation();

    if (!confirm(`Are you sure you want to delete the connection "${databases[dbKey].name}"?`)) {
        return;
    }

    try {
        const response = await fetch(`/api/disconnect/${dbKey}`, {
            method: 'POST'
        });

        const result = await response.json();

        if (result.success) {
            showMessage('Connection deleted', 'success');
            if (currentDatabase === dbKey) {
                currentDatabase = null;
                document.getElementById('explorerContent').innerHTML =
                    '<div class="empty-state"><p class="text-muted"><i class="fas fa-arrow-left"></i> Select a database from the left sidebar</p></div>';
                document.getElementById('editorContent').innerHTML =
                    '<div class="welcome-message"><h6>Welcome to Database Monitor</h6><p>Connection removed. Select another database to continue.</p></div>';
            }
            loadDatabases();
        } else {
            showMessage(`Failed to disconnect: ${result.error}`, 'danger');
        }
    } catch (error) {
        console.error('Error disconnecting:', error);
        showMessage('Failed to disconnect', 'danger');
    }
}

// Load all databases
async function loadDatabases() {
    try {
        const response = await fetch('/api/databases');
        const databasesList = await response.json();

        databases = {};
        databasesList.forEach(db => {
            databases[db.key] = db;
        });

        // Populate grant database dropdown
        const grantDbSelect = document.getElementById('grantDbKey');
        if (grantDbSelect) {
            grantDbSelect.innerHTML = '<option value="" disabled selected>Select Database</option>' +
                databasesList.map(db => `<option value="${db.key}">${db.name} (${db.key})</option>`).join('');
        }

        renderDatabaseList();
    } catch (error) {
        console.error('Error loading databases:', error);
        // showError('Failed to load databases'); // defined elsewhere?
    }
}

// Render database list with groups and drag-and-drop
function renderDatabaseList() {
    const databaseList = document.getElementById('databaseList');
    if (!databaseList) return;

    if (Object.keys(databases).length === 0) {
        databaseList.innerHTML = '<div class="text-muted p-2">No databases configured</div>';
        return;
    }

    // Helper to render a single db item
    const renderItem = (db) => {
        const isOnline = db.status && db.status.connected;
        const statusClass = isOnline ? 'online' : 'offline';
        const isActive = currentDatabase === db.key ? 'active' : '';

        const canEdit = window.USER_PERMISSIONS.includes('manage_connections');
        const editButton = canEdit ? `
            <button class="btn btn-sm btn-icon" onclick="event.stopPropagation(); editConnection('${db.key}')" title="Edit">
                 <i class="fas fa-cog"></i>
            </button>
        ` : '';

        return `
            <div class="database-item ${isActive}"
                 draggable="true"
                 data-db-key="${db.key}"
                 ondragstart="handleDragStart(event)"
                 ondragover="handleDragOver(event)"
                 ondrop="handleDrop(event)"
                 onclick="selectDatabase('${db.key}')">
                <div class="database-item-name">
                    <i class="fas fa-database"></i>
                    <span>${db.name}</span>
                </div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <div class="status-light ${statusClass}" title="${isOnline ? 'Online' : 'Offline'}"></div>
                    <div class="database-item-actions">
                        ${editButton}
                    </div>
                </div>
            </div>
        `;
    };

    // Group databases
    const groups = {};
    const ungrouped = [];

    // First ensure all actual groups exist (even empty ones from folder placeholders)
    Object.values(databases).forEach(db => {
        if (db.engine === 'folder') {
            // It's a placeholder for a group
            const groupName = db.group || db.name;
            if (!groups[groupName]) groups[groupName] = [];
            return;
        }

        if (db.group) {
            if (!groups[db.group]) groups[db.group] = [];
            groups[db.group].push(db);
        } else {
            ungrouped.push(db);
        }
    });

    // Sort contents
    const sortFn = (a, b) => (a.order || 0) - (b.order || 0);
    ungrouped.sort(sortFn);
    Object.keys(groups).sort().forEach(key => {
        groups[key].sort(sortFn);
    });

    let html = '';

    // Always render an "Ungrouped / Root" drop zone at the top
    html += `
        <div class="ungrouped-items"
             style="min-height: ${ungrouped.length === 0 ? '40px' : 'auto'}; border: 1px dashed ${ungrouped.length === 0 ? '#444' : 'transparent'}; border-radius: 4px; margin-bottom: 10px;"
             ondragover="handleDragOverGroup(event)"
             ondrop="handleDropOnGroup(event, '')"
             title="Drag here to move to top level">
            ${ungrouped.length === 0 && Object.keys(groups).length > 0 ? '<div class="text-muted text-center" style="font-size: 0.8em; padding: 10px;">Root Level (Drop here)</div>' : ''}
            ${ungrouped.map(renderItem).join('')}
        </div>
    `;

    // 1. Render Groups
    Object.keys(groups).forEach(groupName => {
        const canEdit = window.USER_PERMISSIONS.includes('manage_connections');
        const deleteFolderBtn = canEdit ? `
            <button class="btn btn-sm text-danger p-0"
                    onclick="deleteFolder('${groupName}')"
                    title="Delete Folder"
                    style="padding: 0 4px; font-size: 0.8rem; background: none; border: none; z-index: 10;">
                <i class="fas fa-trash"></i>
            </button>
        ` : '';

        html += `
            <div class="database-group"
                 style="position: relative;"
                 ondragover="handleDragOverGroup(event)"
                 ondrop="handleDropOnGroup(event, '${groupName}')">
                <div class="group-header" style="display: flex; align-items: center; justify-content: space-between;">
                    <div style="display: flex; align-items: center; cursor: pointer; flex-grow: 1;" onclick="toggleGroup(this.parentElement)">
                        <i class="fas fa-folder-open me-2"></i>
                        <span>${groupName}</span>
                    </div>
                    ${deleteFolderBtn}
                </div>
                <div class="group-items">
                    ${groups[groupName].length === 0 ? '<div class="text-muted text-center" style="font-size: 0.8em; padding: 5px;">Empty Folder</div>' : groups[groupName].map(renderItem).join('')}
                </div>
            </div>
        `;
    });

    databaseList.innerHTML = html;
}

// Delete Folder
async function deleteFolder(folderName) {
    if (!confirm(`Delete folder "${folderName}"?\n\nThis will remove the folder but keep all connections (moved to root).`)) {
        return;
    }

    try {
        const response = await fetch('/api/delete-folder', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ name: folderName })
        });

        const result = await response.json();
        if (result.success) {
            showMessage(result.message, 'success');
            loadDatabases();
        } else {
            showMessage(result.error || 'Failed to delete folder', 'danger');
        }
    } catch(e) {
        console.error(e);
        showMessage('Error deleting folder', 'danger');
    }
}



// --- Backup & Restore ---

window.performBackup = async function() {
    const pwd = document.getElementById('backupPassword').value;
    const feedback = document.getElementById('backupMessage');

    if (!pwd) {
        feedback.className = 'alert alert-danger';
        feedback.textContent = 'Password is required.';
        feedback.classList.remove('d-none');
        return;
    }

    feedback.className = 'alert alert-info';
    feedback.textContent = 'Encrypting and generating backup...';
    feedback.classList.remove('d-none');

    try {
        const response = await fetch('/api/connections/export', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ password: pwd })
        });

        const result = await response.json();

        if (result.success) {
            feedback.className = 'alert alert-success';
            feedback.textContent = 'Backup created successfully. Downloading...';

            // Trigger download
            const blob = new Blob([result.data], { type: 'text/plain' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = result.filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

            // Reset and close
            setTimeout(() => {
                document.getElementById('backupPassword').value = '';
                feedback.classList.add('d-none');
                bootstrap.Modal.getInstance(document.getElementById('backupModal')).hide();
            }, 2000);
        } else {
            feedback.className = 'alert alert-danger';
            feedback.textContent = result.error || 'Backup failed.';
        }
    } catch (e) {
        feedback.className = 'alert alert-danger';
        feedback.textContent = 'Error: ' + e.message;
    }
}

window.performRestore = async function() {
    const fileInput = document.getElementById('restoreFile');
    const pwd = document.getElementById('restorePassword').value;
    const feedback = document.getElementById('restoreMessage');

    if (!fileInput.files[0] || !pwd) {
        feedback.className = 'alert alert-danger';
        feedback.textContent = 'File and password are required.';
        feedback.classList.remove('d-none');
        return;
    }

    feedback.className = 'alert alert-info';
    feedback.textContent = 'Decrypting and restoring...';
    feedback.classList.remove('d-none');

    const reader = new FileReader();
    reader.onload = async function(e) {
        const content = e.target.result; // This is the text content

        try {
            const response = await fetch('/api/connections/import', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    password: pwd,
                    data: content
                })
            });

            const result = await response.json();

            if (result.success) {
                feedback.className = 'alert alert-success';
                feedback.textContent = result.message;

                setTimeout(() => {
                   window.location.reload(); // Reload to show new connections
                }, 1500);
            } else {
                feedback.className = 'alert alert-danger';
                feedback.textContent = result.error || 'Restore failed.';
            }
        } catch (err) {
            feedback.className = 'alert alert-danger';
            feedback.textContent = 'Error: ' + err.message;
        }
    };
    reader.readAsText(fileInput.files[0]);
}


let draggedDbKey = null;

function handleDragStart(event) {
    draggedDbKey = event.currentTarget.getAttribute('data-db-key');
    event.dataTransfer.effectAllowed = 'move';
    // Transparent image to unclutter view? Default is fine for now.
}

function handleDragOver(event) {
    event.preventDefault(); // Necessary to allow dropping
    event.dataTransfer.dropEffect = 'move';
    event.currentTarget.classList.add('drag-over');
}

function handleDragLeave(event) {
    event.currentTarget.classList.remove('drag-over');
}

// Drop on another Item -> Reorder
async function handleDrop(event) {
    event.preventDefault();
    event.stopPropagation();
    const target = event.currentTarget;
    target.classList.remove('drag-over');

    const targetDbKey = target.getAttribute('data-db-key');
    if (!draggedDbKey || draggedDbKey === targetDbKey) return;

    // Find both DB objects
    const draggedDb = databases[draggedDbKey];
    const targetDb = databases[targetDbKey];

    // Determine new group and order
    // If dropping on an item, adopt its group and insert before/after
    // Simple logic: Insert *before* the target
    const newGroup = targetDb.group || "";

    // We need to recalculate orders for the whole group
    const siblings = Object.values(databases).filter(d => (d.group || "") === newGroup && d.key !== draggedDbKey);
    siblings.sort((a, b) => (a.order || 0) - (b.order || 0));

    const targetIndex = siblings.findIndex(d => d.key === targetDbKey);
    // Insert dragged item at target index
    siblings.splice(targetIndex, 0, draggedDb);

    // Prepare batch update
    const updates = siblings.map((db, index) => ({
        key: db.key,
        group: newGroup,
        order: index
    }));

    // Also include the dragged item update (it's in siblings now)

    await saveReorder(updates);
}

function handleDragOverGroup(event) {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
}

// Drop on a Folder Header or Empty Area -> Move to Group
async function handleDropOnGroup(event, groupName) {
    event.preventDefault();
    event.stopPropagation();

    if (!draggedDbKey) return;
    const db = databases[draggedDbKey];

    // If already in group, do nothing (unless we want to append to end?)
    if ((db.group || "") === groupName) {
        return;
    }

    // Move to end of target group
    const targetGroupItems = Object.values(databases).filter(d => (d.group || "") === groupName && d.key !== draggedDbKey);
    const newOrder = targetGroupItems.length;

    const updates = [{
        key: draggedDbKey,
        group: groupName,
        order: newOrder
    }];

    await saveReorder(updates);
}

async function saveReorder(updates) {
    // Optimistic UI update
    updates.forEach(u => {
        if (databases[u.key]) {
            databases[u.key].group = u.group;
            databases[u.key].order = u.order;
        }
    });
    renderDatabaseList();

    try {
        await fetch('/api/connections/reorder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ updates })
        });
    } catch (e) {
        console.error("Reorder failed", e);
        // Revert? For now, just log.
    }
}

function toggleGroup(header) {
    const items = header.nextElementSibling;
    if (items) {
        items.classList.toggle('hidden');
        const icon = header.querySelector('i.fa-folder-open, i.fa-folder');
        if (icon) {
            icon.classList.toggle('fa-folder-open');
            icon.classList.toggle('fa-folder');
        }
    }
}

// Update database status
function updateDatabaseStatus(dbKey, status) {
    if (databases[dbKey]) {
        databases[dbKey].status = status;
        // Don't re-render whole list to avoid breaking drag state or scroll,
        // just find the indicator
        const item = document.querySelector(`.database-item[data-db-key="${dbKey}"] .status-light`);
        if (item) {
            item.className = `status-light ${status.connected ? 'online' : 'offline'}`;
            item.title = status.connected ? 'Online' : 'Offline';
        }
    }
}

// Select a database
async function selectDatabase(dbKey) {
    currentDatabase = dbKey;
    currentSchema = null;
    currentTable = null;

    renderDatabaseList();

    const db = databases[dbKey];
    const explorerTitle = document.getElementById('explorerTitle');
    explorerTitle.textContent = db.name;

    const explorerContent = document.getElementById('explorerContent');
    explorerContent.innerHTML = '<div class="loader-message"><i class="fas fa-spinner fa-spin"></i> Loading schemas...</div>';

    try {
        const response = await fetch(`/api/database/${dbKey}/schemas`);
        const data = await response.json();

        if (data.error) {
            showExplorerError(data.error);
            return;
        }

        renderSchemas(dbKey, data.schemas);
    } catch (error) {
        console.error('Error loading schemas:', error);
        showExplorerError('Failed to load schemas');
    }
}

// Render schemas
function renderSchemas(dbKey, schemas) {
    const explorerContent = document.getElementById('explorerContent');

    let html = '<div class="tree-item">';

    schemas.forEach(schema => {
        const schemaId = `${dbKey}-schema-${schema}`;
        html += `
            <div class="tree-row">
                <button class="tree-toggle" onclick="toggleSchemaTables('${dbKey}', '${schema}', this)">
                    <i class="fas fa-chevron-right"></i>
                </button>
                <span class="tree-node" onclick="selectSchema('${dbKey}', '${schema}')">
                    <i class="fas fa-folder"></i>
                    <span>${schema}</span>
                </span>
            </div>
            <div id="${schemaId}-tables" class="tree-children hidden"></div>
        `;
    });

    html += '</div>';
    explorerContent.innerHTML = html;
}

// Toggle schema tables visibility
async function toggleSchemaTables(dbKey, schema, toggleBtn) {
    const schemaId = `${dbKey}-schema-${schema}`;
    const tablesContainer = document.getElementById(`${schemaId}-tables`);

    if (!tablesContainer) return;

    const isHidden = tablesContainer.classList.contains('hidden');

    if (isHidden) {
        // Load tables
        loadSchemaTables(dbKey, schema);
        tablesContainer.classList.remove('hidden');
        toggleBtn.innerHTML = '<i class="fas fa-chevron-down"></i>';
    } else {
        tablesContainer.classList.add('hidden');
        toggleBtn.innerHTML = '<i class="fas fa-chevron-right"></i>';
    }
}

// Load tables and views for a schema
async function loadSchemaTables(dbKey, schema) {
    try {
        const response = await fetch(`/api/database/${dbKey}/schema/${schema}/tables`);
        const data = await response.json();

        if (data.error) {
            console.error('Error loading tables:', data.error);
            return;
        }

        const schemaId = `${dbKey}-schema-${schema}`;
        const tablesContainer = document.getElementById(`${schemaId}-tables`);

        let html = '';

        // Render tables
        if (data.tables && data.tables.length > 0) {
            html += '<div style="margin-bottom: 10px;">';
            html += '<div style="font-weight: 600; color: #666; padding: 5px 0; font-size: 0.85rem;">Tables</div>';
            data.tables.forEach(table => {
                html += `
                    <div class="tree-node" onclick="selectTable('${dbKey}', '${schema}', '${table}')">
                        <i class="fas fa-table"></i>
                        <span>${table}</span>
                    </div>
                `;
            });
            html += '</div>';
        }

        // Render views
        if (data.views && data.views.length > 0) {
            html += '<div>';
            html += '<div style="font-weight: 600; color: #666; padding: 5px 0; font-size: 0.85rem;">Views</div>';
            data.views.forEach(view => {
                html += `
                    <div class="tree-node" onclick="selectView('${dbKey}', '${schema}', '${view}')">
                        <i class="fas fa-eye"></i>
                        <span>${view}</span>
                    </div>
                `;
            });
            html += '</div>';
        }

        if (!html) {
            html = '<div class="text-muted" style="padding: 10px; font-size: 0.9rem;">No tables or views</div>';
        }

        tablesContainer.innerHTML = html;
    } catch (error) {
        console.error('Error loading schema tables:', error);
    }
}

// Select a schema
function selectSchema(dbKey, schema) {
    currentSchema = schema;
    currentTable = null;

    const editorTitle = document.getElementById('editorTitle');
    editorTitle.textContent = `SQL Editor - ${schema}`;

    const editorContent = document.getElementById('editorContent');
    editorContent.innerHTML = `
        <div class="sql-editor-container">
            <div class="editor-toolbar">
                <button class="btn btn-sm btn-primary" onclick="executeSQLQuery('${dbKey}', '${schema}')">
                    <i class="fas fa-play"></i> Execute
                </button>
                <button class="btn btn-sm btn-secondary" onclick="clearSQLEditor()">
                    <i class="fas fa-trash"></i> Clear
                </button>
            </div>
            <textarea class="sql-textarea" id="sqlEditor" placeholder="Enter SQL query here...

Example:
SELECT * FROM your_table LIMIT 10;"></textarea>
            <div id="queryResults"></div>
        </div>
    `;
}

// Select a table
async function selectTable(dbKey, schema, table) {
    currentTable = table;

    const editorTitle = document.getElementById('editorTitle');
    editorTitle.textContent = `Table: ${table}`;

    const editorContent = document.getElementById('editorContent');
    editorContent.innerHTML = '<div class="loader-message"><i class="fas fa-spinner fa-spin"></i> Loading table data...</div>';

    try {
        const response = await fetch(`/api/database/${dbKey}/schema/${schema}/table/${table}`);
        const data = await response.json();

        if (data.error) {
            showEditorError(data.error);
            return;
        }

        renderTablePreview(table, data);
    } catch (error) {
        console.error('Error loading table:', error);
        showEditorError('Failed to load table data');
    }
}

// Select a view (same as table)
async function selectView(dbKey, schema, view) {
    currentTable = view;

    const editorTitle = document.getElementById('editorTitle');
    editorTitle.textContent = `View: ${view}`;

    const editorContent = document.getElementById('editorContent');
    editorContent.innerHTML = '<div class="loader-message"><i class="fas fa-spinner fa-spin"></i> Loading view data...</div>';

    try {
        const response = await fetch(`/api/database/${dbKey}/schema/${schema}/table/${view}`);
        const data = await response.json();

        if (data.error) {
            showEditorError(data.error);
            return;
        }

        renderTablePreview(view, data);
    } catch (error) {
        console.error('Error loading view:', error);
        showEditorError('Failed to load view data');
    }
}

// Render table preview
function renderTablePreview(tableName, tableData) {
    const editorContent = document.getElementById('editorContent');
    const columns = tableData.columns || [];
    const rows = tableData.data || [];

    let html = '<div class="table-preview-container">';

    // Preview Data first (more important)
    if (rows.length > 0) {
        html += '<div>';
        html += `<div class="results-header">Preview Data (${rows.length} rows)</div>`;
        html += '<div class="table-scroll-wrapper">';
        html += '<table class="results-table">';

        // Table header
        html += '<thead><tr>';
        columns.forEach(col => {
            html += `<th>${col.name}</th>`;
        });
        html += '</tr></thead>';

        // Table body
        html += '<tbody>';
        rows.forEach(row => {
            html += '<tr>';
            columns.forEach(col => {
                const value = row[col.name];
                const displayValue = value === null ? '<em style="color: #999;">NULL</em>' : escapeHtml(String(value)).substring(0, 100);
                html += `<td>${displayValue}</td>`;
            });
            html += '</tr>';
        });
        html += '</tbody>';

        html += '</table>';
        html += '</div>';
        html += '</div>';
    } else {
        html += '<div class="text-muted" style="padding: 20px; text-align: center;">No data in table</div>';
    }

    // Column Information — collapsible, closed by default
    html += `
        <div class="columns-section">
            <button class="columns-toggle" onclick="this.parentElement.classList.toggle('open')">
                <i class="fas fa-chevron-right columns-toggle-icon"></i>
                <span>Columns & Types</span>
                <span class="columns-count">${columns.length}</span>
            </button>
            <div class="columns-body">`;
    columns.forEach(col => {
        html += `
                <div class="column-info">
                    <div class="column-name">${col.name}</div>
                    <div class="column-meta">
                        <span class="column-type">${col.type}</span>
                        <span class="column-nullable ${col.nullable ? 'yes' : 'no'}">${col.nullable ? 'NULLABLE' : 'NOT NULL'}</span>
                    </div>
                </div>`;
    });
    html += `
            </div>
        </div>`;

    html += '</div>';
    editorContent.innerHTML = html;
}

// Execute SQL query
async function executeSQLQuery(dbKey, schema) {
    const sqlEditor = document.getElementById('sqlEditor');
    const sql = sqlEditor.value.trim();

    if (!sql) {
        showMessage('Please enter a SQL query', 'warning');
        return;
    }

    const queryResults = document.getElementById('queryResults');
    queryResults.innerHTML = '<div class="loader-message"><i class="fas fa-spinner fa-spin"></i> Executing query...</div>';

    try {
        const response = await fetch(`/api/database/${dbKey}/execute`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ sql: sql })
        });

        const result = await response.json();

        if (result.success) {
            renderQueryResults(result);
        } else {
            showMessage(`Error: ${result.error}`, 'danger');
        }
    } catch (error) {
        console.error('Error executing query:', error);
        showMessage('Failed to execute query', 'danger');
    }
}

// Render query results
function renderQueryResults(result) {
    const queryResults = document.getElementById('queryResults');

    let html = '<div class="results-container">';

    if (result.data) {
        // SELECT query results
        const columns = result.columns || [];
        const rows = result.data || [];

        html += `<div class="results-header">Results (${rows.length} rows)</div>`;

        if (rows.length > 0) {
            html += '<table class="results-table">';

            // Table header
            html += '<thead><tr>';
            columns.forEach(col => {
                html += `<th>${col}</th>`;
            });
            html += '</tr></thead>';

            // Table body
            html += '<tbody>';
            rows.forEach(row => {
                html += '<tr>';
                columns.forEach(col => {
                    const value = row[col];
                    const displayValue = value === null ? '<em style="color: #999;">NULL</em>' : escapeHtml(String(value)).substring(0, 100);
                    html += `<td>${displayValue}</td>`;
                });
                html += '</tr>';
            });
            html += '</tbody>';

            html += '</table>';
        } else {
            html += '<div class="text-muted" style="padding: 20px;">No rows returned</div>';
        }
    } else {
        // INSERT, UPDATE, DELETE results
        html += `<div class="success-message">
            <i class="fas fa-check-circle"></i> ${result.message}
        </div>`;
    }

    html += '</div>';
    queryResults.innerHTML = html;
}

// Clear SQL editor
function clearSQLEditor() {
    const sqlEditor = document.getElementById('sqlEditor');
    if (sqlEditor) {
        sqlEditor.value = '';
        document.getElementById('queryResults').innerHTML = '';
    }
}

// Utility functions
function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, m => map[m]);
}

function showMessage(message, type = 'info') {
    const queryResults = document.getElementById('queryResults');
    const alertClass = type === 'danger' ? 'alert-danger' : type === 'success' ? 'alert-success' : 'alert-info';
    const icon = type === 'danger' ? 'fa-times-circle' : type === 'success' ? 'fa-check-circle' : 'fa-info-circle';

    const html = `
        <div class="alert ${alertClass} alert-dismissible fade show" role="alert">
            <i class="fas ${icon}"></i> ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;

    if (queryResults) {
        queryResults.innerHTML = html;
    }
}

function showError(message) {
    const html = `
        <div class="error-message">
            <i class="fas fa-times-circle"></i> ${message}
        </div>
    `;

    const explorerContent = document.getElementById('explorerContent');
    if (explorerContent) {
        explorerContent.innerHTML = html;
    }
}

function showExplorerError(message) {
    const html = `
        <div class="error-message">
            <i class="fas fa-times-circle"></i> ${message}
        </div>
    `;

    const explorerContent = document.getElementById('explorerContent');
    if (explorerContent) {
        explorerContent.innerHTML = html;
    }
}

function showEditorError(message) {
    const html = `
        <div class="error-message">
            <i class="fas fa-times-circle"></i> ${message}
        </div>
    `;

    const editorContent = document.getElementById('editorContent');
    if (editorContent) {
        editorContent.innerHTML = html;
    }
}

// ============================================================
// Panel Resizer — drag to resize explorer / editor panels
// ============================================================
(function initResizer() {
    const resizer = document.getElementById('panelResizer');
    const explorer = document.getElementById('explorerPanel');
    if (!resizer || !explorer) return;

    let startX = 0;
    let startWidth = 0;
    let dragging = false;

    function onMouseDown(e) {
        e.preventDefault();
        dragging = true;
        startX = e.clientX;
        startWidth = explorer.getBoundingClientRect().width;
        resizer.classList.add('active');
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
    }

    function onMouseMove(e) {
        if (!dragging) return;
        const dx = e.clientX - startX;
        const newWidth = Math.max(150, Math.min(startWidth + dx, window.innerWidth - 450));
        explorer.style.width = newWidth + 'px';
    }

    function onMouseUp() {
        dragging = false;
        resizer.classList.remove('active');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
    }

    resizer.addEventListener('mousedown', onMouseDown);
})();

// ============================================================
// User Profile & Management
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
    // Password Change
    const savePasswordBtn = document.getElementById('savePasswordBtn');
    if (savePasswordBtn) {
        savePasswordBtn.addEventListener('click', async () => {
            const current = document.getElementById('currentPassword').value;
            const newPass = document.getElementById('newPassword').value;
            const confirm = document.getElementById('confirmNewPassword').value;
            const msgDiv = document.getElementById('passwordChangeMessage');

            msgDiv.classList.add('d-none');
            msgDiv.className = 'alert d-none';

            if (newPass !== confirm) {
                msgDiv.textContent = 'New passwords do not match.';
                msgDiv.classList.remove('d-none');
                msgDiv.classList.add('alert-danger');
                return;
            }

            try {
                const button = savePasswordBtn;
                const originalText = button.innerHTML;
                button.disabled = true;
                button.innerHTML = '<i class=\'fas fa-spinner fa-spin\'></i> Saving...';

                const response = await fetch('/api/profile/change-password', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        old_password: current,
                        new_password: newPass
                    })
                });

                const result = await response.json();

                button.disabled = false;
                button.innerHTML = originalText;

                if (result.success) {
                    msgDiv.textContent = result.message;
                    msgDiv.classList.remove('d-none');
                    msgDiv.classList.add('alert-success');
                    document.getElementById('changePasswordForm').reset();
                    setTimeout(() => {
                        const modal = bootstrap.Modal.getInstance(document.getElementById('changePasswordModal'));
                        if (modal) modal.hide();
                        msgDiv.classList.add('d-none');
                    }, 1500);
                } else {
                    msgDiv.textContent = result.message;
                    msgDiv.classList.remove('d-none');
                    msgDiv.classList.add('alert-danger');
                }
            } catch (error) {
                console.error('Error changing password:', error);
                msgDiv.textContent = 'An error occurred. Please try again.';
                msgDiv.classList.remove('d-none');
                msgDiv.classList.add('alert-danger');
                if (savePasswordBtn) savePasswordBtn.disabled = false;
            }
        });
    }

    // Backup Connections (handled by simple link href, but we can verify)
    // The link has href='/api/connections/backup' and target='_blank'
    // so it should work natively without JS.

    // User Management Logic
    if (window.USER_PERMISSIONS.includes('manage_users')) {
        const userManagementModal = document.getElementById('userManagementModal');
        if (userManagementModal) {
            userManagementModal.addEventListener('show.bs.modal', () => {
                loadRoles().then(() => {
                    loadUsers();
                    loadGrants();
                });
            });
        }

        // Users Tab
        const btnShowAddUserForm = document.getElementById('btnShowAddUserForm');
        const addUserFormContainer = document.getElementById('addUserFormContainer');
        if (btnShowAddUserForm && addUserFormContainer) {
            btnShowAddUserForm.addEventListener('click', () => {
                addUserFormContainer.classList.toggle('d-none');
            });
        }

        const addUserForm = document.getElementById('addUserForm');
        if (addUserForm) {
            addUserForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const username = document.getElementById('newUsername').value;
                const password = document.getElementById('newUserPassword').value;
                const role = document.getElementById('newUserRole').value;

                try {
                    const response = await fetch('/api/users', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ username, password, role })
                    });
                    const result = await response.json();
                    if (result.success) {
                        showMessage(result.message, 'success');
                        addUserForm.reset();
                        addUserFormContainer.classList.add('d-none');
                        loadUsers();
                    } else {
                        showMessage(result.error || 'Failed to create user', 'danger');
                    }
                } catch (error) {
                    console.error('Error creating user:', error);
                    showMessage('Error creating user', 'danger');
                }
            });
        }

        // Roles Tab
        const btnShowAddRoleForm = document.getElementById('btnShowAddRoleForm');
        const addRoleFormContainer = document.getElementById('addRoleFormContainer');
        if (btnShowAddRoleForm && addRoleFormContainer) {
            btnShowAddRoleForm.addEventListener('click', () => {
                addRoleFormContainer.classList.toggle('d-none');
            });
        }

        const addRoleForm = document.getElementById('addRoleForm');
        if (addRoleForm) {
            addRoleForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const name = document.getElementById('newRoleName').value;
                const permissions = Array.from(document.querySelectorAll('.perm-checkbox:checked')).map(cb => cb.value);

                try {
                    const response = await fetch('/api/roles', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ name, permissions, description: 'Custom role' })
                    });
                    const result = await response.json();
                    if (result.success) {
                        showMessage(result.message, 'success');
                        addRoleForm.reset();
                        addRoleFormContainer.classList.add('d-none');
                        loadRoles();
                    } else {
                        showMessage(result.error || 'Failed to create role', 'danger');
                    }
                } catch (error) {
                    console.error('Error creating role:', error);
                    showMessage('Error creating role', 'danger');
                }
            });
        }

        // Grants Tab
        const btnShowAddGrantForm = document.getElementById('btnShowAddGrantForm');
        const addGrantFormContainer = document.getElementById('addGrantFormContainer');
        if (btnShowAddGrantForm && addGrantFormContainer) {
            btnShowAddGrantForm.addEventListener('click', () => {
                addGrantFormContainer.classList.toggle('d-none');
            });
        }

        const addGrantForm = document.getElementById('addGrantForm');
        if (addGrantForm) {
            addGrantForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const username = document.getElementById('grantUsername').value;
                const db_key = document.getElementById('grantDbKey').value;
                const role = document.getElementById('grantRole').value;

                try {
                    const response = await fetch('/api/grants', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ username, db_key, role })
                    });
                    const result = await response.json();
                    if (result.success) {
                        showMessage(result.message, 'success');
                        addGrantForm.reset();
                        addGrantFormContainer.classList.add('d-none');
                        loadGrants();
                    } else {
                        showMessage(result.error || 'Failed to create grant', 'danger');
                    }
                } catch (error) {
                    console.error('Error creating grant:', error);
                    showMessage('Error creating grant', 'danger');
                }
            });
        }
    }
});

let systemRoles = [];

async function loadRoles() {
    try {
        const response = await fetch('/api/roles');
        const result = await response.json();
        const tbody = document.getElementById('rolesTableBody');
        if (!tbody) return;

        systemRoles = result.roles || [];
        tbody.innerHTML = '';

        // Update role dropdowns
        const roleSelects = [document.getElementById('newUserRole'), document.getElementById('grantRole')];
        const roleOptions = systemRoles.map(r => `<option value="${r.name}">${r.name}</option>`).join('');
        roleSelects.forEach(select => {
            if (select) select.innerHTML = roleOptions;
        });

        if (systemRoles.length > 0) {
            systemRoles.forEach(role => {
                const perms = role.permissions.map(p => `<span class="badge bg-info text-dark me-1">${p}</span>`).join('');
                const deleteBtn = role.is_system ?
                    `<button class="btn btn-sm btn-outline-secondary" disabled title="System Role"><i class="fas fa-lock"></i></button>` :
                    `<button class="btn btn-sm btn-outline-danger" onclick="deleteRole('${role.name}')" title="Delete Role"><i class="fas fa-trash"></i></button>`;

                tbody.innerHTML += `
                    <tr>
                        <td><strong>${role.name}</strong> ${role.is_system ? '<span class="badge bg-secondary">System</span>' : ''}</td>
                        <td>${perms}</td>
                        <td class="text-end">${deleteBtn}</td>
                    </tr>
                `;
            });
        } else {
            tbody.innerHTML = '<tr><td colspan="3" class="text-center text-muted">No roles found</td></tr>';
        }
    } catch (error) {
        console.error('Error loading roles:', error);
    }
}

async function deleteRole(name) {
    if (!confirm(`Are you sure you want to delete role "${name}"?`)) return;
    try {
        const response = await fetch(`/api/roles/${name}`, { method: 'DELETE' });
        const result = await response.json();
        if (result.success) {
            showMessage(result.message, 'success');
            loadRoles();
        } else {
            showMessage(result.error || 'Failed to delete role', 'danger');
        }
    } catch (error) {
        console.error('Error deleting role:', error);
    }
}

async function loadGrants() {
    try {
        const response = await fetch('/api/grants');
        const result = await response.json();
        const tbody = document.getElementById('grantsTableBody');
        if (!tbody) return;

        tbody.innerHTML = '';
        if (result.grants && result.grants.length > 0) {
            result.grants.forEach(grant => {
                tbody.innerHTML += `
                    <tr>
                        <td><strong>${grant.username}</strong></td>
                        <td><code>${grant.db_key}</code></td>
                        <td><span class="badge bg-primary">${grant.role}</span></td>
                        <td class="text-end">
                            <button class="btn btn-sm btn-outline-danger" onclick="deleteGrant('${grant.username}', '${grant.db_key}')" title="Revoke Access">
                                <i class="fas fa-trash"></i>
                            </button>
                        </td>
                    </tr>
                `;
            });
        } else {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">No database grants found</td></tr>';
        }
    } catch (error) {
        console.error('Error loading grants:', error);
    }
}

async function deleteGrant(username, db_key) {
    if (!confirm(`Revoke access to ${db_key} for user ${username}?`)) return;
    try {
        const response = await fetch(`/api/grants/${username}/${db_key}`, { method: 'DELETE' });
        const result = await response.json();
        if (result.success) {
            showMessage(result.message, 'success');
            loadGrants();
        } else {
            showMessage(result.error || 'Failed to revoke grant', 'danger');
        }
    } catch (error) {
        console.error('Error revoking grant:', error);
    }
}

async function loadUsers() {
    try {
        const response = await fetch('/api/users');
        const result = await response.json();
        const tbody = document.getElementById('usersTableBody');
        if (!tbody) return;

        tbody.innerHTML = '';
        if (result.users && result.users.length > 0) {
            // Populate grant user dropdown
            const grantUserSelect = document.getElementById('grantUsername');
            if (grantUserSelect) {
                grantUserSelect.innerHTML = '<option value="" disabled selected>Select User</option>' +
                    result.users.map(u => `<option value="${u.username}">${u.username}</option>`).join('');
            }

            result.users.forEach(user => {
                const date = new Date(user.created_at).toLocaleString();
                const roleBadgeClass = user.role === 'admin' ? 'bg-danger' : (user.role === 'editor' ? 'bg-warning text-dark' : 'bg-secondary');
                const isOnline = window.onlineUsers.includes(user.username);
                const onlineIndicator = isOnline ? '<span class="status-light online d-inline-block ms-2" title="Online"></span>' : '<span class="status-light offline d-inline-block ms-2" title="Offline"></span>';

                const roleOptions = systemRoles.map(r =>
                    `<option value="${r.name}" ${user.role === r.name ? 'selected' : ''}>${r.name}</option>`
                ).join('');

                tbody.innerHTML += `
                    <tr>
                        <td><strong>${user.username}</strong>${onlineIndicator}</td>
                        <td>
                            <select class="form-select form-select-sm w-auto d-inline-block" onchange="updateUserRole('${user.username}', this.value)" ${user.username === 'admin' ? 'disabled' : ''}>
                                ${roleOptions}
                            </select>
                        </td>
                        <td><small class="text-muted">${date}</small></td>
                        <td class="text-end">
                            <button class="btn btn-sm btn-outline-secondary" onclick="resetUserPassword('${user.username}')" title="Reset Password">
                                <i class="fas fa-key"></i>
                            </button>
                            <button class="btn btn-sm btn-outline-danger" onclick="deleteUser('${user.username}')" title="Delete User" ${user.username === 'admin' ? 'disabled' : ''}>
                                <i class="fas fa-trash"></i>
                            </button>
                        </td>
                    </tr>
                `;
            });
        } else {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">No users found</td></tr>';
        }
    } catch (error) {
        console.error('Error loading users:', error);
    }
}

async function updateUserRole(username, newRole) {
    try {
        const response = await fetch(`/api/users/${username}/role`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ role: newRole })
        });
        const result = await response.json();
        if (result.success) {
            showMessage(result.message, 'success');
        } else {
            showMessage(result.error || 'Failed to update role', 'danger');
            loadUsers(); // reload to revert select
        }
    } catch (error) {
        console.error('Error updating role:', error);
        showMessage('Error updating role', 'danger');
        loadUsers();
    }
}

async function resetUserPassword(username) {
    const newPassword = prompt(`Enter new password for user "${username}":`);
    if (!newPassword) return;
    if (newPassword.length < 4) {
        alert('Password must be at least 4 characters.');
        return;
    }

    try {
        const response = await fetch(`/api/users/${username}/password`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password: newPassword })
        });
        const result = await response.json();
        if (result.success) {
            showMessage(result.message, 'success');
        } else {
            showMessage(result.error || 'Failed to reset password', 'danger');
        }
    } catch (error) {
        console.error('Error resetting password:', error);
        showMessage('Error resetting password', 'danger');
    }
}

async function deleteUser(username) {
    if (!confirm(`Are you sure you want to delete user "${username}"? This action cannot be undone.`)) {
        return;
    }

    try {
        const response = await fetch(`/api/users/${username}`, {
            method: 'DELETE'
        });
        const result = await response.json();
        if (result.success) {
            showMessage(result.message, 'success');
            loadUsers();
        } else {
            showMessage(result.error || 'Failed to delete user', 'danger');
        }
    } catch (error) {
        console.error('Error deleting user:', error);
        showMessage('Error deleting user', 'danger');
    }
}
