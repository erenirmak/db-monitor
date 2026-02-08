// Initialize Socket.IO connection
const socket = io();

// Global 401 handler — redirect to login if session expired
const _originalFetch = window.fetch;
window.fetch = async function (...args) {
    const response = await _originalFetch.apply(this, args);
    if (response.status === 401) {
        window.location.href = '/login';
        throw new Error('Session expired — redirecting to login');
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
socket.on('connect', function() {
    console.log('Connected to server');
    loadDatabases();
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
    const refreshBtn = document.getElementById('refreshBtn');
    const searchBtn = document.getElementById('searchBtn');
    const databaseTypeSelect = document.getElementById('databaseType');
    const testConnectionBtn = document.getElementById('testConnectionBtn');
    const saveConnectionBtn = document.getElementById('saveConnectionBtn');
    const searchInput = document.getElementById('searchInput');

    // Add Connection Button
    addConnectionBtn.addEventListener('click', function() {
        addConnectionModal = new bootstrap.Modal(document.getElementById('addConnectionModal'));
        resetConnectionForm();
        addConnectionModal.show();
    });

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
    saveConnectionBtn.addEventListener('click', saveConnection);
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
    document.getElementById('dynamicFieldsContainer').innerHTML = '';
    document.getElementById('connectionMessage').style.display = 'none';
    const extraJsonEl = document.getElementById('extraJson');
    if (extraJsonEl) extraJsonEl.value = '';
    currentConnectionForm = {};
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

    if (!connectionName) {
        showConnectionMessage('Please enter a connection name', 'error');
        return;
    }

    if (!connectionType) {
        showConnectionMessage('Please select a database type', 'error');
        return;
    }

    if (!validateExtraJson()) return;

    const connectionData = {
        name: connectionName,
        type: connectionType,
        fields: {},
        extra_json: getExtraJson()
    };

    // Collect form data
    const config = DATABASE_CONFIGS[connectionType];
    let isValid = true;
    
    config.fields.forEach(field => {
        const value = document.getElementById(`field_${field.name}`).value;
        if (field.required && !value) {
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
    event.stopPropagation();
    
    if (!confirm(`Disconnect from ${databases[dbKey].name}?`)) {
        return;
    }

    try {
        const response = await fetch(`/api/disconnect/${dbKey}`, {
            method: 'POST'
        });

        const result = await response.json();

        if (result.success) {
            showMessage('Connection removed', 'success');
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
        
        renderDatabaseList();
    } catch (error) {
        console.error('Error loading databases:', error);
        showError('Failed to load databases');
    }
}

// Render database list in sidebar
function renderDatabaseList() {
    const databaseList = document.getElementById('databaseList');
    
    if (Object.keys(databases).length === 0) {
        databaseList.innerHTML = '<div class="text-muted">No databases configured</div>';
        return;
    }
    
    let html = '';
    Object.keys(databases).forEach(dbKey => {
        const db = databases[dbKey];
        const status = db.status;
        const isOnline = status.connected;
        const statusClass = isOnline ? 'online' : 'offline';
        
        html += `
            <div class="database-item ${currentDatabase === dbKey ? 'active' : ''}" 
                 onclick="selectDatabase('${dbKey}')">
                <div class="database-item-name">
                    <i class="fas fa-database"></i>
                    <span>${db.name}</span>
                </div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <div class="status-light ${statusClass}" title="${isOnline ? 'Online' : 'Offline'}"></div>
                    <div class="database-item-actions">
                        <button class="btn btn-sm btn-danger" onclick="disconnectDatabase('${dbKey}', event)" title="Disconnect">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                </div>
            </div>
        `;
    });
    
    databaseList.innerHTML = html;
}

// Update database status
function updateDatabaseStatus(dbKey, status) {
    if (databases[dbKey]) {
        databases[dbKey].status = status;
        renderDatabaseList();
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
