// CORD App - Application State & Operations
let token = localStorage.getItem('cord_token');
let currentUser = null;
try {
  currentUser = JSON.parse(localStorage.getItem('cord_user'));
} catch (e) {}
let workspaces = [];
try {
  workspaces = JSON.parse(localStorage.getItem('cord_workspaces')) || [];
} catch (e) {}
let activeWorkspaceId = localStorage.getItem('cord_active_workspace') || 'default_workspace';

let activeView = 'tab-diagnostics';
let authMode = 'login'; // 'login' or 'signup'
let activeConnector = 'notion'; // 'notion', 'slack', 'jira', 'gdrive'

// Global DOM references
const authScreen = document.getElementById('auth-screen');
const mainDashboard = document.getElementById('main-dashboard');
const authForm = document.getElementById('auth-form');
const authEmail = document.getElementById('auth-email');
const authPassword = document.getElementById('auth-password');
const authSubmitBtn = document.getElementById('auth-submit-btn');
const authToggleLink = document.getElementById('auth-toggle-link');
const authErrorMsg = document.getElementById('auth-error-msg');

const workspaceSelect = document.getElementById('workspace-select');
const userDisplayEmail = document.getElementById('user-display-email');
const statusConsole = document.getElementById('status-console');
const queryInput = document.getElementById('query-input');

// Initialize application on page load
document.addEventListener('DOMContentLoaded', () => {
  setupTabs();
  checkAuth();
});

// Setup tab navigation clicks
function setupTabs() {
  document.querySelectorAll('.tab-item').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.tab-item').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      
      activeView = tab.getAttribute('data-tab');
      document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
      });
      document.getElementById(activeView).classList.add('active');
      
      logConsole(`View switched to: ${activeView}`, 'info');
      loadTabContentData();
    });
  });
}

// Log message helper
function logConsole(message, type = '', consoleId = 'status-console') {
  const consoleEl = document.getElementById(consoleId);
  if (!consoleEl) return;
  const line = document.createElement('div');
  line.className = `log-line ${type}`;
  const timestamp = new Date().toLocaleTimeString();
  line.textContent = `[${timestamp}] ${message}`;
  consoleEl.appendChild(line);
  consoleEl.scrollTop = consoleEl.scrollHeight;
}

// Verify authorization state
async function checkAuth() {
  if (token && currentUser) {
    authScreen.style.display = 'none';
    mainDashboard.style.display = 'block';
    userDisplayEmail.textContent = currentUser.email;
    
    // Refresh user's workspaces
    await fetchWorkspaces();
    populateWorkspaceSelect();
    loadTabContentData();
  } else {
    authScreen.style.display = 'flex';
    mainDashboard.style.display = 'none';
  }
}

// Toggle authentication forms signup/login
function toggleAuthMode(event) {
  event.preventDefault();
  authErrorMsg.style.display = 'none';
  if (authMode === 'login') {
    authMode = 'signup';
    authSubmitBtn.textContent = 'Sign Up';
    authToggleLink.textContent = 'Already have an account? Log In';
  } else {
    authMode = 'login';
    authSubmitBtn.textContent = 'Log In';
    authToggleLink.textContent = "Don't have an account? Sign Up";
  }
}

// Handle login or signup submission
async function handleAuthSubmit(event) {
  event.preventDefault();
  authErrorMsg.style.display = 'none';
  authSubmitBtn.disabled = true;
  
  const email = authEmail.value.trim();
  const password = authPassword.value;
  
  const endpoint = authMode === 'signup' ? '/api/auth/signup' : '/api/auth/login';
  
  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });
    
    const data = await response.json();
    
    if (!response.ok) {
      throw new Error(data.detail || 'Authentication failed.');
    }
    
    if (authMode === 'signup') {
      // Auto login after signup
      authMode = 'login';
      authSubmitBtn.disabled = false;
      authEmail.value = email;
      authPassword.value = password;
      logConsole('Account registered. Logging in automatically...', 'success');
      // Submit form programmatically
      authForm.dispatchEvent(new Event('submit'));
    } else {
      // Handle login success
      token = data.token;
      currentUser = data.user;
      workspaces = data.workspaces || [];
      activeWorkspaceId = data.user.default_workspace_id || 'default_workspace';
      
      localStorage.setItem('cord_token', token);
      localStorage.setItem('cord_user', JSON.stringify(currentUser));
      localStorage.setItem('cord_workspaces', JSON.stringify(workspaces));
      localStorage.setItem('cord_active_workspace', activeWorkspaceId);
      
      logConsole('Login successful.', 'success');
      
      // Clean form fields
      authEmail.value = '';
      authPassword.value = '';
      authSubmitBtn.disabled = false;
      
      await checkAuth();
    }
  } catch (err) {
    authErrorMsg.textContent = err.message;
    authErrorMsg.style.display = 'block';
    authSubmitBtn.disabled = false;
  }
}

// Log out user
function handleLogout() {
  token = null;
  currentUser = null;
  workspaces = [];
  activeWorkspaceId = 'default_workspace';
  
  localStorage.removeItem('cord_token');
  localStorage.removeItem('cord_user');
  localStorage.removeItem('cord_workspaces');
  localStorage.removeItem('cord_active_workspace');
  
  checkAuth();
}

// Fetch workspaces list
async function fetchWorkspaces() {
  try {
    const response = await fetch('/api/workspaces', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (response.ok) {
      const data = await response.json();
      workspaces = data.workspaces || [];
      localStorage.setItem('cord_workspaces', JSON.stringify(workspaces));
    }
  } catch (err) {
    console.error('Failed to load workspaces:', err);
  }
}

// Populate workspace dropdown
function populateWorkspaceSelect() {
  workspaceSelect.innerHTML = '';
  if (workspaces.length === 0) {
    workspaceSelect.innerHTML = `<option value="default_workspace">Default Workspace</option>`;
    return;
  }
  workspaces.forEach(ws => {
    const opt = document.createElement('option');
    opt.value = ws.workspace_id;
    opt.textContent = ws.name;
    opt.selected = ws.workspace_id === activeWorkspaceId;
    workspaceSelect.appendChild(opt);
  });
}

// Switch workspace
function switchWorkspace(workspaceId) {
  activeWorkspaceId = workspaceId;
  localStorage.setItem('cord_active_workspace', activeWorkspaceId);
  logConsole(`Switched active workspace scope to: ${activeWorkspaceId}`, 'info');
  loadTabContentData();
}

// Create Workspace Modal
const newWorkspaceModal = document.getElementById('new-workspace-modal');
function openNewWorkspaceModal() {
  document.getElementById('modal-ws-error').style.display = 'none';
  document.getElementById('new-ws-id').value = '';
  document.getElementById('new-ws-name').value = '';
  newWorkspaceModal.classList.add('active');
}

function closeNewWorkspaceModal() {
  newWorkspaceModal.classList.remove('active');
}

async function submitNewWorkspace() {
  const wsIdInput = document.getElementById('new-ws-id').value.trim();
  const wsNameInput = document.getElementById('new-ws-name').value.trim();
  const errorEl = document.getElementById('modal-ws-error');
  
  if (!wsIdInput || !wsNameInput) {
    errorEl.textContent = 'Please fill out all fields.';
    errorEl.style.display = 'block';
    return;
  }
  
  try {
    const response = await fetch('/api/workspaces', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({ workspace_id: wsIdInput, name: wsNameInput })
    });
    
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Failed to create workspace.');
    
    logConsole(`Created new workspace '${wsNameInput}' (${wsIdInput})`, 'success');
    closeNewWorkspaceModal();
    
    await fetchWorkspaces();
    activeWorkspaceId = wsIdInput;
    localStorage.setItem('cord_active_workspace', activeWorkspaceId);
    
    populateWorkspaceSelect();
    loadTabContentData();
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.style.display = 'block';
  }
}

// Load data depending on active tab view
function loadTabContentData() {
  if (activeView === 'tab-diagnostics') {
    // Clear outputs if empty
    resetDiagnosticsUI();
  } 
  else if (activeView === 'tab-recurring') {
    loadRecurringIssues();
  } 
  else if (activeView === 'tab-deployments') {
    loadDeployments();
  } 
  else if (activeView === 'tab-escalations') {
    loadEscalations();
  } 
  else if (activeView === 'tab-timeline') {
    loadTimeline();
  }
  else if (activeView === 'tab-integrations') {
    loadIntegrations();
  }

  else if (activeView === 'tab-evaluation') {
    loadEvaluationMetrics();
  }
}

// Reset diagnostics UI
function resetDiagnosticsUI() {
  document.getElementById('diagnostics-empty').style.display = 'flex';
  document.getElementById('diagnostics-results').style.display = 'none';
  document.getElementById('diagnostics-loader').style.display = 'none';
}

// Populate search input
function populateQuery(text) {
  queryInput.value = text;
  logConsole(`Quick query selected.`, 'info');
}

// Run Diagnostics Query
async function executeDiagnosticQuery() {
  const query = queryInput.value.trim();
  if (!query) {
    logConsole('Please write a query command first.', 'error');
    return;
  }
  
  const selectedEndpoint = document.querySelector('input[name="endpoint"]:checked').value;
  
  const emptyScreen = document.getElementById('diagnostics-empty');
  const loader = document.getElementById('diagnostics-loader');
  const resultsDiv = document.getElementById('diagnostics-results');
  const submitBtn = document.getElementById('btn-submit-query');
  
  emptyScreen.style.display = 'none';
  resultsDiv.style.display = 'none';
  loader.style.display = 'flex';
  submitBtn.disabled = true;
  
  logConsole(`Executing diagnostic query via ${selectedEndpoint}...`, 'info');
  const startTime = performance.now();
  
  try {
    const response = await fetch(selectedEndpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        query: query,
        limit: 5,
        workspace_id: activeWorkspaceId
      })
    });
    
    if (!response.ok) throw new Error(`HTTP Error Status ${response.status}`);
    
    const data = await response.json();
    const duration = ((performance.now() - startTime) / 1000).toFixed(2);
    
    logConsole(`Diagnostic complete. Elapsed time: ${duration}s`, 'success');
    renderDiagnosticResults(data, duration, selectedEndpoint);
  } catch (err) {
    logConsole(`Diagnostic query failed: ${err.message}`, 'error');
    resetDiagnosticsUI();
  } finally {
    loader.style.display = 'none';
    submitBtn.disabled = false;
  }
}

// Render query output
function renderDiagnosticResults(data, duration, endpoint) {
  const resultsDiv = document.getElementById('diagnostics-results');
  resultsDiv.style.display = 'block';
  
  // Render Summary Report
  const classBadge = document.getElementById('res-classification');
  classBadge.textContent = data.query_classification || data.classification || 'analysis';
  
  const durationText = document.getElementById('res-execution-time');
  durationText.textContent = `Time: ${duration}s`;
  
  const scorePct = document.getElementById('res-confidence-pct');
  const confidenceScore = data.confidence || (data.insight && data.insight.confidence) || 0.85;
  scorePct.textContent = `${Math.round(confidenceScore * 100)}%`;
  
  const summaryText = document.getElementById('res-summary');
  summaryText.innerHTML = data.insight || data.summary || data.explanation || 'No summary text returned.';
  
  const explanationText = document.getElementById('res-confidence-explanation');
  if (data.diagnostics && data.diagnostics.explanation) {
    explanationText.textContent = `Reasoning Trace: ${data.diagnostics.explanation}`;
    explanationText.style.display = 'block';
  } else if (data.diagnostics && data.diagnostics.confidence_factors) {
    explanationText.textContent = `Confidence Factors: ${data.diagnostics.confidence_factors.join(', ')}`;
    explanationText.style.display = 'block';
  } else {
    explanationText.style.display = 'none';
  }
  
  // Render Timeline Trails
  const timelineList = document.getElementById('timeline-events-list');
  timelineList.innerHTML = '';
  const events = (data.evidence && data.evidence.events) || [];
  if (events.length === 0) {
    timelineList.innerHTML = '<div style="color: var(--text-muted); font-size: 0.8rem; padding: 1rem 0;">No chronological events traced.</div>';
  } else {
    events.forEach(ev => {
      const item = document.createElement('div');
      item.className = `timeline-item ${ev.event_type || 'info'}`;
      item.innerHTML = `
        <span class="timeline-time">${ev.timestamp ? ev.timestamp.split('T')[0] : 'N/A'}</span>
        <div class="timeline-title">${ev.title}</div>
        <div class="timeline-desc">${ev.summary || ev.description || ''}</div>
      `;
      timelineList.appendChild(item);
    });
  }
  
  // Render Correlations Links
  const correlationsList = document.getElementById('correlations-links-list');
  correlationsList.innerHTML = '';
  const correlations = (data.evidence && data.evidence.correlations) || [];
  if (correlations.length === 0) {
    correlationsList.innerHTML = '<div style="color: var(--text-muted); font-size: 0.8rem; padding: 1rem 0;">No relational correlation links detected.</div>';
  } else {
    correlations.forEach(corr => {
      const item = document.createElement('div');
      item.className = 'correlation-item';
      item.innerHTML = `
        <div class="correlation-meta">
          <span class="correlation-type">${corr.type || corr.correlation_type}</span>
          <span class="correlation-score">Score: ${corr.score ? corr.score.toFixed(2) : '1.00'}</span>
        </div>
        <div class="correlation-reason">${corr.reason || ''}</div>
      `;
      correlationsList.appendChild(item);
    });
  }
  
  // Render Vector Source Chunks
  const evidenceList = document.getElementById('evidence-chunks-list');
  evidenceList.innerHTML = '';
  const chunks = (data.evidence && data.evidence.chunks) || data.results || [];
  if (chunks.length === 0) {
    evidenceList.innerHTML = '<div style="color: var(--text-muted); font-size: 0.85rem; padding: 1rem 0;">No vector documents linked.</div>';
  } else {
    chunks.forEach(chunk => {
      const item = document.createElement('div');
      item.className = 'evidence-item';
      const scoreVal = chunk.score ? `Score: ${chunk.score.toFixed(4)}` : '';
      const sourceVal = chunk.source || chunk.source_type || 'notion';
      const authorVal = chunk.author || (chunk.metadata && chunk.metadata.author) || 'system';
      const timeVal = chunk.timestamp || chunk.created_time || 'N/A';
      const titleVal = chunk.title || (chunk.metadata && chunk.metadata.title) || 'Untitled Document';
      
      item.innerHTML = `
        <div class="evidence-item-header">
          <span class="evidence-source">${sourceVal}</span>
          <span class="evidence-score">${scoreVal}</span>
        </div>
        <div class="evidence-title">${titleVal}</div>
        <div class="evidence-snippet">${chunk.content || chunk.snippet || ''}</div>
      `;
      item.addEventListener('click', () => {
        showDocumentModal(titleVal, sourceVal, authorVal, timeVal, chunk.content || chunk.snippet || '');
      });
      evidenceList.appendChild(item);
    });
  }
}

// Modal view evidence chunk details
const evidenceModal = document.getElementById('evidence-modal');
function showDocumentModal(title, source, author, timestamp, content) {
  document.getElementById('modal-doc-title').textContent = title;
  document.getElementById('modal-doc-source').textContent = `SOURCE: ${source.toUpperCase()}`;
  document.getElementById('modal-doc-author').textContent = `AUTHOR: ${author || 'System'}`;
  document.getElementById('modal-doc-time').textContent = `TIME: ${timestamp}`;
  document.getElementById('modal-doc-content').textContent = content;
  evidenceModal.classList.add('active');
}



// Workspace Ingestion Synchronizer with Circular Progress Bar
async function syncActiveWorkspace() {
  const syncBtn = document.getElementById('btn-workspace-sync');
  const loaderWrapper = document.getElementById('sync-loader-wrapper');
  const progressBar = document.getElementById('sync-progress-bar');
  const progressPct = document.getElementById('sync-progress-pct');
  const progressPhase = document.getElementById('sync-progress-phase');

  syncBtn.disabled = true;
  loaderWrapper.style.display = 'flex';
  
  // Reset progress circle (251.2 corresponds to 0% progress)
  progressBar.style.strokeDashoffset = '251.2';
  progressPct.textContent = '0%';
  progressPhase.textContent = 'INITIATING CRAWL...';
  
  logConsole(`Starting workspace synchronization for: ${activeWorkspaceId}...`, 'info');
  
  let currentProgress = 0;
  let targetProgress = 0;
  let phaseText = 'CONNECTING TO WORKSPACE...';
  
  const updateProgressUI = () => {
    progressPct.textContent = `${Math.round(currentProgress)}%`;
    const offset = 251.2 * (1 - currentProgress / 100);
    progressBar.style.strokeDashoffset = offset;
    progressPhase.textContent = phaseText;
  };

  const progressInterval = setInterval(() => {
    if (currentProgress < targetProgress) {
      currentProgress += 0.5;
      updateProgressUI();
    }
  }, 15);

  try {
    // Stage 1: Connecting (0% -> 20%)
    targetProgress = 20;
    phaseText = 'CRAWLING NOTION PAGES...';
    await new Promise(r => setTimeout(r, 800));

    // Stage 2: Notion crawling (20% -> 45%)
    targetProgress = 45;
    phaseText = 'CRAWLING SLACK CHANNELS...';
    await new Promise(r => setTimeout(r, 1000));

    // Stage 3: Slack crawling (45% -> 60%)
    targetProgress = 60;
    phaseText = 'SYNCING JIRA TICKETS & FILES...';
    
    // Trigger real backend sync API call
    const responsePromise = fetch(`/api/workspaces/${activeWorkspaceId}/sync`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      }
    });

    await new Promise(r => setTimeout(r, 800));
    
    // Stage 4: Aggregation and Chunking (60% -> 75%)
    targetProgress = 75;
    phaseText = 'GENERATING VECTOR EMBEDDINGS...';
    
    const response = await responsePromise;
    const data = await response.json();
    
    if (!response.ok) throw new Error(data.detail || 'Workspace sync failed.');

    // Stage 5: Ingesting into Qdrant & PG Graph (75% -> 90%)
    targetProgress = 90;
    phaseText = 'BUILDING SEMANTIC KNOWLEDGE GRAPH...';
    await new Promise(r => setTimeout(r, 1000));

    // Stage 6: Completion (90% -> 100%)
    targetProgress = 100;
    phaseText = 'SYNC COMPLETE!';
    
    // Wait for animation to finish
    await new Promise(r => {
      const checkDone = setInterval(() => {
        if (currentProgress >= 100) {
          clearInterval(checkDone);
          r();
        }
      }, 50);
    });

    logConsole(`Successfully synchronized workspace. ${data.documents_synced} documents ingested, ${data.chunks_created} vector chunks generated.`, 'success');
    logConsole(`Notion: ${data.details.notion} | Slack: ${data.details.slack} | Jira: ${data.details.jira} | GDrive: ${data.details.gdrive}`, 'info');

  } catch (err) {
    clearInterval(progressInterval);
    progressPhase.textContent = 'SYNC FAILED';
    progressPhase.style.color = 'var(--accent-red)';
    logConsole(`Workspace sync failed: ${err.message}`, 'error');
  } finally {
    clearInterval(progressInterval);
    setTimeout(() => {
      loaderWrapper.style.display = 'none';
      syncBtn.disabled = false;
      progressPhase.style.color = '';
    }, 3000);
  }
}

// Call Pilot Analytics Router helper
async function callPilotApi(endpoint) {
  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({ workspace_id: activeWorkspaceId, limit: 10 })
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } catch (err) {
    logConsole(`Failed to load ${endpoint}: ${err.message}`, 'error');
    return null;
  }
}

// Render loaders inside panels
function renderListLoader(containerId, message = 'Fetching Pilot Analytics...') {
  const container = document.getElementById(containerId);
  container.innerHTML = `
    <div style="padding: 3rem; text-align: center; color: var(--text-muted); width: 100%;">
      <span class="spinner"></span>
      <p style="margin-top: 0.5rem; font-size: 0.85rem;">${message}</p>
    </div>
  `;
}

// --- Tab 2: Recurring Issues ---
async function loadRecurringIssues() {
  const container = document.getElementById('recurring-issues-container');
  renderListLoader('recurring-issues-container');
  
  const data = await callPilotApi('/pilot/operational-issues');
  if (!data) {
    container.innerHTML = `<div class="empty-state">No recurring operational issues detected.</div>`;
    return;
  }
  
  document.getElementById('issues-count-badge').textContent = `${data.recurring_issues_count || 0} Active Clusters`;
  
  const issues = data.issues || [];
  if (issues.length === 0) {
    container.innerHTML = `<div class="empty-state">No recurring issues found. Go to the 'Connections' tab to sync workspace credentials.</div>`;
    return;
  }
  
  container.innerHTML = '';
  issues.forEach(issue => {
    const card = document.createElement('div');
    card.className = 'issue-cluster-card';
    const confObj = issue.confidence_diagnostics || {};
    const scoreVal = confObj.score ? Math.round(confObj.score * 100) : 85;
    const color = issue.severity === 'critical' ? 'var(--accent-red)' : 'var(--accent-amber)';
    const evidenceList = issue.evidence || [];
    
    card.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.75rem;">
        <div>
          <span style="font-size: 0.7rem; font-weight: 700; color: var(--accent-cyan); text-transform: uppercase;">${issue.category || 'Cluster'}</span>
          <h4 class="issue-cluster-title">${issue.title || 'Untitled Cluster'}</h4>
        </div>
        <div style="display: flex; gap: 0.5rem;">
          <span class="badge" style="color: ${color}; border-color: ${color};">${(issue.severity || 'medium').toUpperCase()}</span>
          <span class="badge">CONFIDENCE: ${scoreVal}%</span>
        </div>
      </div>
      
      <p class="issue-cluster-desc">${issue.summary || ''}</p>
      
      <div class="metadata-grid" style="margin-bottom: 1rem;">
        <div class="grid-field"><strong>Team</strong><span>${issue.assigned_team || 'N/A'}</span></div>
        <div class="grid-field"><strong>Assignee</strong><span>${issue.assignee || 'Unassigned'}</span></div>
        <div class="grid-field"><strong>Status</strong><span style="color: var(--accent-green);">${issue.status || 'Open'}</span></div>
      </div>
      
      <div>
        <h5 style="font-size: 0.75rem; text-transform: uppercase; color: var(--text-muted); margin-bottom: 0.4rem; font-weight: 700;">Supporting Evidence:</h5>
        <div style="display: flex; flex-direction: column; gap: 0.4rem;">
          ${evidenceList.map(ev => {
            const sourceStr = (ev.source || 'event').toUpperCase();
            const titleStr = ev.title || 'Untitled Signal';
            const snippetStr = (ev.snippet || ev.description || '').substring(0, 120);
            return `
              <div style="font-size: 0.8rem; background: rgba(0,0,0,0.1); padding: 0.5rem; border-radius: 4px; border: 1px solid var(--border-color);">
                <strong style="color: var(--accent-blue);">${sourceStr}</strong>: ${titleStr} - <span style="color: var(--text-muted); font-size: 0.75rem;">${snippetStr}...</span>
              </div>
            `;
          }).join('')}
        </div>
      </div>
    `;
    container.appendChild(card);
  });
}

// --- Tab 3: Deployments ---
async function loadDeployments() {
  const container = document.getElementById('deployments-container');
  renderListLoader('deployments-container');
  
  const data = await callPilotApi('/pilot/deployment-analysis');
  if (!data) {
    container.innerHTML = `<div class="empty-state">No deployment instability analyzed.</div>`;
    return;
  }
  
  document.getElementById('deployments-count-badge').textContent = `${data.deployments_analyzed || 0} Releases`;
  
  const deployments = data.deployments || [];
  if (deployments.length === 0) {
    container.innerHTML = `<div class="empty-state">No deployments traced. Go to the 'Connections' tab to sync workspace credentials.</div>`;
    return;
  }
  
  container.innerHTML = '';
  deployments.forEach(dep => {
    const card = document.createElement('div');
    card.className = 'deployment-card';
    const stabilityScore = dep.stability_score !== undefined ? dep.stability_score : 100;
    const scoreColor = stabilityScore >= 80 ? 'var(--accent-green)' : stabilityScore >= 50 ? 'var(--accent-amber)' : 'var(--accent-red)';
    const incidentsList = dep.linked_incidents || [];
    const confObj = dep.confidence_diagnostics || {};
    const scoreVal = confObj.score ? Math.round(confObj.score * 100) : 95;
    const triggerTitle = incidentsList.length > 0 ? incidentsList[0].title : 'System Healthy';
    
    card.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.75rem;">
        <div>
          <span style="font-size: 0.75rem; font-family: var(--font-mono); color: var(--text-muted);">${dep.timestamp ? dep.timestamp.split('T')[0] : 'N/A'}</span>
          <h4 class="deployment-title">${dep.title || 'Untitled Release'}</h4>
        </div>
        <div class="metric-block" style="padding: 0.5rem 1rem; border-radius: 4px; min-width: 140px;">
          <div class="metric-value" style="font-size: 1.4rem; color: ${scoreColor};">${stabilityScore}%</div>
          <div class="metric-label" style="font-size: 0.6rem;">Stability Score</div>
        </div>
      </div>
      
      <p class="deployment-desc">Released by <strong>${dep.author || 'Unknown'}</strong>. Stability analysis traces subsequent outages.</p>
      
      <div class="metadata-grid">
        <div class="grid-field"><strong>Post-Deploy Regressions</strong>
          <span>${incidentsList.length === 0 ? '<span style="color: var(--accent-green);">None Detected</span>' : `<span style="color: var(--accent-red);">${incidentsList.length} Regressions</span>`}</span>
        </div>
        <div class="grid-field"><strong>Trace Confidence</strong><span>${scoreVal}%</span></div>
        <div class="grid-field"><strong>Trigger Cause</strong><span>${triggerTitle}</span></div>
      </div>
    `;
    container.appendChild(card);
  });
}

// --- Tab 4: Escalations ---
async function loadEscalations() {
  const container = document.getElementById('escalations-container');
  renderListLoader('escalations-container');
  
  const data = await callPilotApi('/pilot/escalation-analysis');
  if (!data) {
    container.innerHTML = `<div class="empty-state">No incident escalations analyzed.</div>`;
    return;
  }
  
  document.getElementById('escalations-count-badge').textContent = `${data.escalations_tracked || 0} Routes`;
  
  const escalations = data.escalations || [];
  if (escalations.length === 0) {
    container.innerHTML = `<div class="empty-state">No escalations found.</div>`;
    return;
  }
  
  container.innerHTML = '';
  escalations.forEach(esc => {
    const card = document.createElement('div');
    card.className = 'escalation-card';
    const route = esc.escalation_route || [];
    const confObj = esc.confidence_diagnostics || {};
    const scoreVal = confObj.score ? Math.round(confObj.score * 100) : 90;
    
    card.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.75rem;">
        <div>
          <span style="font-size: 0.7rem; font-weight: 700; color: var(--accent-red); text-transform: uppercase;">${esc.incident_type || 'Escalation'}</span>
          <h4 class="escalation-title">${esc.title || 'Untitled Escalation'}</h4>
        </div>
        <span class="badge">${(esc.priority || 'medium').toUpperCase()}</span>
      </div>
      
      <p class="escalation-desc"><strong>Handoff Bottleneck:</strong> ${esc.bottleneck_identified || 'None'}</p>
      
      <div style="margin-bottom: 1rem;">
        <h5 style="font-size: 0.75rem; text-transform: uppercase; color: var(--text-muted); font-weight: 700; margin-bottom: 0.5rem;">Triage Path Flow:</h5>
        <div style="display: flex; flex-direction: column; gap: 0.5rem; padding-left: 0.5rem; border-left: 2px solid var(--border-color);">
          ${route.map(r => `
            <div style="font-size: 0.8rem; display: flex; justify-content: space-between; align-items: center;">
              <span>Step ${r.step || 1}: <strong>${r.role || 'Assignee'}</strong></span>
              <span style="color: var(--text-muted); font-family: var(--font-mono);">${r.duration_minutes || 0} mins</span>
            </div>
          `).join('')}
        </div>
      </div>
      
      <div class="metadata-grid">
        <div class="grid-field"><strong>Current Status</strong><span>${(esc.current_state || 'Open').toUpperCase()}</span></div>
        <div class="grid-field"><strong>Total Resolving Duration</strong><span>${esc.total_triage_minutes || 0} Minutes</span></div>
        <div class="grid-field"><strong>Triage Accuracy</strong><span>${scoreVal}%</span></div>
      </div>
    `;
    container.appendChild(card);
  });
}

// --- Tab 5: Timeline ---
async function loadTimeline() {
  const container = document.getElementById('pilot-timeline-container');
  renderListLoader('pilot-timeline-container');
  
  const data = await callPilotApi('/pilot/timeline-analysis');
  if (!data) {
    container.innerHTML = `<div class="empty-state">No timeline events found.</div>`;
    return;
  }
  
  document.getElementById('timeline-count-badge').textContent = `${data.timeline_events_count || 0} Events`;
  
  const timeline = data.timeline || [];
  if (timeline.length === 0) {
    container.innerHTML = `<div class="empty-state">Timeline is empty. Go to the 'Connections' tab to sync workspace credentials.</div>`;
    return;
  }
  
  container.innerHTML = '';
  timeline.forEach(ev => {
    const item = document.createElement('div');
    item.className = `timeline-item ${ev.event_type || 'info'}`;
    const dateVal = ev.timestamp ? ev.timestamp.replace('T', ' ').substring(0, 16) : 'N/A';
    
    item.innerHTML = `
      <span class="timeline-time">${dateVal}</span>
      <div class="timeline-title">${ev.title}</div>
      <div class="timeline-desc">${ev.summary}</div>
    `;
    container.appendChild(item);
  });
}

// --- Tab 6: Connections ---
async function loadIntegrations() {
  logConsole('Retrieving connector credential configuration statuses...', 'info');
  try {
    const response = await fetch(`/api/workspaces/${activeWorkspaceId}/connectors`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    
    const data = await response.json();
    
    // Update statuses
    data.connectors.forEach(conn => {
      const indicator = document.getElementById(`status-${conn.connector_type}`);
      if (indicator) {
        if (conn.connected) {
          indicator.textContent = 'CONNECTED';
          indicator.className = 'status-indicator active';
        } else {
          indicator.textContent = 'Not Configured';
          indicator.className = 'status-indicator';
        }
      }
    });
    
    // Render active connector form
    selectConnector(activeConnector);
  } catch (err) {
    logConsole(`Failed to load integrations status: ${err.message}`, 'error');
  }
}

// Toggle active connector selection
function selectConnector(type) {
  activeConnector = type;
  
  // Update class active styling
  document.querySelectorAll('.connector-item').forEach(item => {
    item.classList.remove('active');
  });
  const activeItem = document.getElementById(`conn-item-${type}`);
  if (activeItem) activeItem.classList.add('active');
  
  // Set text titles
  const titleEl = document.getElementById('connector-title');
  const descEl = document.getElementById('connector-desc');
  const msgEl = document.getElementById('connector-msg');
  msgEl.style.display = 'none';
  
  const formsContainer = document.getElementById('form-connector-fields');
  formsContainer.innerHTML = '';
  
  if (type === 'notion') {
    titleEl.textContent = 'Configure Notion API Integration';
    descEl.textContent = 'Connect a Notion integration token to crawl document pages recursively.';
    formsContainer.innerHTML = `
      <div class="form-group">
        <label for="notion-token">Internal Integration Token</label>
        <input type="password" id="notion-token" placeholder="secret_notion_...">
      </div>
      <div class="form-group">
        <label for="notion-page">Root Page / Database ID (Optional)</label>
        <input type="text" id="notion-page" placeholder="3c9db86dfc924765...">
      </div>
    `;
  } 
  else if (type === 'slack') {
    titleEl.textContent = 'Configure Slack Crawler';
    descEl.textContent = 'Ingest channel history and thread alerts securely using a Bot User token.';
    formsContainer.innerHTML = `
      <div class="form-group">
        <label for="slack-token">Bot User OAuth Token</label>
        <input type="password" id="slack-token" placeholder="xoxb-...">
      </div>
      <div class="form-group">
        <label for="slack-channels">Channel Whitelist (Comma-separated)</label>
        <input type="text" id="slack-channels" placeholder="#general, #alerts, #ops">
      </div>
    `;
  } 
  else if (type === 'jira') {
    titleEl.textContent = 'Configure Jira Server Link';
    descEl.textContent = 'Retrieve bugs, priority, assignees, and state history from specific Jira projects.';
    formsContainer.innerHTML = `
      <div class="form-group">
        <label for="jira-url">Jira Instance Host URL</label>
        <input type="text" id="jira-url" placeholder="https://company.atlassian.net">
      </div>
      <div class="form-group">
        <label for="jira-username">Username / Account Email</label>
        <input type="email" id="jira-username" placeholder="developer@company.com">
      </div>
      <div class="form-group">
        <label for="jira-token">Jira API Token</label>
        <input type="password" id="jira-token" placeholder="ATATT3xD...">
      </div>
    `;
  } 
  else if (type === 'gdrive') {
    titleEl.textContent = 'Configure Google Drive Credentials';
    descEl.textContent = 'Input your Google Cloud Service Account credentials JSON key file contents.';
    formsContainer.innerHTML = `
      <div class="form-group">
        <label for="gdrive-json">Google Service Account Credentials JSON</label>
        <textarea id="gdrive-json" style="height: 180px; font-family: var(--font-mono); font-size: 0.8rem;" placeholder='{ "type": "service_account", "project_id": "...", "private_key": "..." }'></textarea>
      </div>
    `;
  }
}

// Gather config settings
function getConnectorFormInputs() {
  const inputs = {};
  if (activeConnector === 'notion') {
    inputs.api_key = document.getElementById('notion-token').value.trim();
    inputs.start_page_id = document.getElementById('notion-page').value.trim();
  } 
  else if (activeConnector === 'slack') {
    inputs.token = document.getElementById('slack-token').value.trim();
    inputs.channels = document.getElementById('slack-channels').value.trim();
  } 
  else if (activeConnector === 'jira') {
    inputs.url = document.getElementById('jira-url').value.trim();
    inputs.username = document.getElementById('jira-username').value.trim();
    inputs.token = document.getElementById('jira-token').value.trim();
  } 
  else if (activeConnector === 'gdrive') {
    const rawJson = document.getElementById('gdrive-json').value.trim();
    try {
      if (rawJson) return JSON.parse(rawJson);
    } catch (e) {
      throw new Error('Invalid JSON key format.');
    }
  }
  return inputs;
}

// Test Active Connector Credentials
async function testActiveConnector() {
  const msgEl = document.getElementById('connector-msg');
  msgEl.style.display = 'none';
  
  let config;
  try {
    config = getConnectorFormInputs();
    // Validate empty credentials check
    let isEmpty = true;
    for (let key in config) {
      if (config[key]) isEmpty = false;
    }
    if (isEmpty) {
      msgEl.textContent = 'Credentials config fields cannot be completely empty.';
      msgEl.className = 'auth-message';
      msgEl.style.display = 'block';
      return;
    }
  } catch (err) {
    msgEl.textContent = `Configuration Error: ${err.message}`;
    msgEl.className = 'auth-message';
    msgEl.style.display = 'block';
    return;
  }
  
  logConsole(`Testing connection for ${activeConnector}...`, 'info');
  
  try {
    const response = await fetch('/api/connectors/test', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        connector_type: activeConnector,
        credentials_json: JSON.stringify(config)
      })
    });
    
    const data = await response.json();
    
    if (data.success) {
      msgEl.textContent = data.message;
      msgEl.className = 'auth-message success';
      logConsole(`Connection test passed: ${data.message}`, 'success');
    } else {
      msgEl.textContent = data.message;
      msgEl.className = 'auth-message';
      logConsole(`Connection test failed: ${data.message}`, 'error');
    }
    msgEl.style.display = 'block';
  } catch (err) {
    msgEl.textContent = `Server communication failed: ${err.message}`;
    msgEl.className = 'auth-message';
    msgEl.style.display = 'block';
  }
}

// Save Active Connector Credentials
async function saveActiveConnector() {
  const msgEl = document.getElementById('connector-msg');
  msgEl.style.display = 'none';
  
  let config;
  try {
    config = getConnectorFormInputs();
  } catch (err) {
    msgEl.textContent = `Configuration Error: ${err.message}`;
    msgEl.className = 'auth-message';
    msgEl.style.display = 'block';
    return;
  }
  
  logConsole(`Saving integration settings for ${activeConnector}...`, 'info');
  
  try {
    const response = await fetch(`/api/workspaces/${activeWorkspaceId}/connectors`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        connector_type: activeConnector,
        credentials_json: JSON.stringify(config)
      })
    });
    
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Save failed.');
    
    msgEl.textContent = data.message;
    msgEl.className = 'auth-message success';
    msgEl.style.display = 'block';
    logConsole(`Connector configurations saved for ${activeConnector}.`, 'success');
    
    // Reload active configuration statuses
    await loadIntegrations();
  } catch (err) {
    msgEl.textContent = `Failed to save configurations: ${err.message}`;
    msgEl.className = 'auth-message';
    msgEl.style.display = 'block';
    logConsole(`Save configurations failed: ${err.message}`, 'error');
  }
}

// --- Tab 7: Evaluation ---
async function loadEvaluationMetrics() {
  const precisionEl = document.getElementById('eval-precision');
  const recallEl = document.getElementById('eval-recall');
  const consistencyEl = document.getElementById('eval-consistency');
  const hallucinationEl = document.getElementById('eval-hallucination');
  const consoleEl = document.getElementById('eval-diagnostics-console');
  
  consoleEl.innerHTML = '<div class="log-line info">Running evaluation benchmarks...</div>';
  
  const data = await callPilotApi('/pilot/evaluate');
  if (!data) {
    precisionEl.textContent = '0.0%';
    recallEl.textContent = '0.0%';
    consistencyEl.textContent = '0.0%';
    hallucinationEl.textContent = '0.0%';
    logConsole('Evaluation run failed.', 'error', 'eval-diagnostics-console');
    return;
  }
  
  precisionEl.textContent = `${(data.retrieval_precision * 100).toFixed(1)}%`;
  recallEl.textContent = `${(data.retrieval_recall * 100).toFixed(1)}%`;
  consistencyEl.textContent = `${(data.evidence_consistency_score * 100).toFixed(1)}%`;
  hallucinationEl.textContent = `${(data.hallucination_rate * 100).toFixed(1)}%`;
  
  logConsole('Calibration metrics calculated.', 'success', 'eval-diagnostics-console');
  logConsole(`Precision: ${data.retrieval_precision} | Recall: ${data.retrieval_recall}`, 'info', 'eval-diagnostics-console');
  logConsole(`Consistency Score: ${data.evidence_consistency_score} (100% means zero references to missing source chunks)`, 'info', 'eval-diagnostics-console');
  logConsole(`Hallucination Rate: ${data.hallucination_rate} (0.0% means no invented references)`, 'info', 'eval-diagnostics-console');
  logConsole(`Evaluation Model: ${data.diagnostics.eval_model}`, 'info', 'eval-diagnostics-console');
}
