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
  else if (activeView === 'tab-workflows') {
    loadWorkflows();
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
let diagnosticsChatHistory = [];

function resetDiagnosticsUI() {
  document.getElementById('diagnostics-empty').style.display = 'flex';
  document.getElementById('diagnostics-results').style.display = 'none';
  document.getElementById('diagnostics-loader').style.display = 'none';
  
  // Reset conversational chat state and DOM
  diagnosticsChatHistory = [];
  const chatHistoryContainer = document.getElementById('diagnostics-chat-history');
  if (chatHistoryContainer) {
    chatHistoryContainer.innerHTML = `
      <div class="chat-message assistant">
        <div class="chat-message-bubble">
          Hello! I am your CORD Diagnostics Assistant. Ask me any follow-up questions about the system state or retrieved evidence above.
        </div>
      </div>
    `;
  }
}

// Chat input handlers
function handleChatInputKey(event) {
  if (event.key === 'Enter') {
    event.preventDefault();
    sendChatDiagnosticsMessage();
  }
}

async function sendChatDiagnosticsMessage() {
  const inputEl = document.getElementById('diagnostics-chat-input');
  const chatHistoryEl = document.getElementById('diagnostics-chat-history');
  const sendBtn = document.getElementById('btn-submit-chat');
  
  const text = inputEl.value.trim();
  if (!text) return;
  
  // Lock fields
  inputEl.disabled = true;
  sendBtn.disabled = true;
  
  // Render user prompt bubble
  const userMsgDiv = document.createElement('div');
  userMsgDiv.className = 'chat-message user';
  userMsgDiv.innerHTML = `
    <div class="chat-message-bubble">${escapeHtml(text)}</div>
    <div class="chat-message-meta">You</div>
  `;
  chatHistoryEl.appendChild(userMsgDiv);
  chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
  
  inputEl.value = '';
  logConsole(`Sending follow-up diagnostics query: "${text}"`, 'info');
  
  // Add loading spinner bubble
  const assistantLoadingDiv = document.createElement('div');
  assistantLoadingDiv.className = 'chat-message assistant loading-bubble';
  assistantLoadingDiv.innerHTML = `
    <div class="chat-message-bubble">
      <span class="spinner" style="margin-bottom: 0; width: 12px; height: 12px; border-width: 1px; vertical-align: middle; display: inline-block;"></span>
      <span style="margin-left: 0.5rem; font-size: 0.85rem; color: var(--text-muted);">Thinking...</span>
    </div>
  `;
  chatHistoryEl.appendChild(assistantLoadingDiv);
  chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
  
  try {
    const response = await fetch('/insights/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        query: text,
        workspace_id: activeWorkspaceId,
        history: diagnosticsChatHistory,
        limit: 3
      })
    });
    
    if (!response.ok) throw new Error(`HTTP Error Status ${response.status}`);
    
    const data = await response.json();
    assistantLoadingDiv.remove();
    
    // Render assistant response
    const assistantMsgDiv = document.createElement('div');
    assistantMsgDiv.className = 'chat-message assistant';
    
    const replyText = data.response || 'No response returned from the diagnostics assistant.';
    
    // Add citation source badges if available
    let sourceBadges = '';
    const chunks = (data.evidence && data.evidence.chunks) || [];
    if (chunks.length > 0) {
      const sourceNames = [...new Set(chunks.map(c => c.source || 'doc'))];
      sourceBadges = `<div style="margin-top: 0.5rem; display: flex; gap: 0.25rem; flex-wrap: wrap;">
        ${sourceNames.map(name => `<span class="badge" style="font-size: 0.6rem;">${name.toUpperCase()}</span>`).join('')}
      </div>`;
    }
    
    assistantMsgDiv.innerHTML = `
      <div class="chat-message-bubble">
        ${formatChatMessageText(replyText)}
        ${sourceBadges}
      </div>
      <div class="chat-message-meta">CORD Assistant</div>
    `;
    chatHistoryEl.appendChild(assistantMsgDiv);
    chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
    
    // Append to conversation history
    diagnosticsChatHistory.push({ role: 'user', content: text });
    diagnosticsChatHistory.push({ role: 'assistant', content: replyText });
    
    logConsole('Diagnostics chat assistant replied successfully.', 'success');
  } catch (err) {
    assistantLoadingDiv.remove();
    logConsole(`Diagnostics chat assistant query failed: ${err.message}`, 'error');
    
    const errorMsgDiv = document.createElement('div');
    errorMsgDiv.className = 'chat-message assistant';
    errorMsgDiv.innerHTML = `
      <div class="chat-message-bubble" style="color: var(--accent-red); border-color: rgba(239, 68, 68, 0.2); background-color: rgba(239, 68, 68, 0.05);">
        Failed to get response: ${err.message}
      </div>
      <div class="chat-message-meta">System Error</div>
    `;
    chatHistoryEl.appendChild(errorMsgDiv);
    chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
  } finally {
    inputEl.disabled = false;
    sendBtn.disabled = false;
    inputEl.focus();
  }
}

// Utility formatting helpers
function escapeHtml(text) {
  const map = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  };
  return text.replace(/[&<>"']/g, function(m) { return map[m]; });
}

function formatChatMessageText(text) {
  let formatted = escapeHtml(text);
  formatted = formatted.replace(/\n/g, '<br>');
  formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  formatted = formatted.replace(/`(.*?)`/g, '<code style="font-family: var(--font-mono); font-size: 0.85rem; background: rgba(0,0,0,0.15); padding: 0.1rem 0.3rem; border-radius: 3px;">$1</code>');
  return formatted;
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
  const rawClass = data.query_type || 
                   (data.query_classification && typeof data.query_classification === 'object' ? data.query_classification.query_type : data.query_classification) || 
                   (data.classification && typeof data.classification === 'object' ? data.classification.query_type : data.classification) || 
                   'analysis';
  classBadge.textContent = rawClass;
  
  const durationText = document.getElementById('res-execution-time');
  durationText.textContent = `Time: ${duration}s`;
  
  const scorePct = document.getElementById('res-confidence-pct');
  const confidenceScore = data.confidence || (data.insight && (data.insight.confidence_score || data.insight.confidence)) || 0.85;
  scorePct.textContent = `${Math.round(confidenceScore * 100)}%`;
  
  const summaryText = document.getElementById('res-summary');
  const summaryVal = (data.insight && typeof data.insight === 'object') ? data.insight.summary : (data.insight || data.summary || data.explanation || 'No summary text returned.');
  summaryText.innerHTML = summaryVal;
  
  const explanationText = document.getElementById('res-confidence-explanation');
  if (data.insight && data.insight.confidence_explanation) {
    explanationText.textContent = data.insight.confidence_explanation;
    explanationText.style.display = 'block';
  } else if (data.diagnostics && data.diagnostics.explanation) {
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
  let events = (data.evidence && data.evidence.events) || [];
  
  // Deduplicate events to keep timeline clean
  const seenEvents = new Set();
  events = events.filter(ev => {
    const key = `${ev.title}_${ev.summary || ev.description || ''}`;
    if (seenEvents.has(key)) return false;
    seenEvents.add(key);
    return true;
  });

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
  let correlations = (data.evidence && data.evidence.correlations) || [];
  
  // Deduplicate correlations by type & reason details
  const seenCorrelations = new Set();
  correlations = correlations.filter(corr => {
    const key = `${corr.type || corr.correlation_type}_${corr.reason || ''}`;
    if (seenCorrelations.has(key)) return false;
    seenCorrelations.add(key);
    return true;
  });

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

// Seed Demo Workspace
async function seedDemoWorkspace() {
  const seedBtn = document.getElementById('btn-seed-demo');
  if (!seedBtn) return;
  seedBtn.disabled = true;
  seedBtn.textContent = 'Seeding...';
  
  logConsole('Triggering Demo Workspace Seeding pipeline...', 'info');
  
  try {
    const response = await fetch('/api/demo/seed', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      }
    });
    
    if (!response.ok) throw new Error(`HTTP Error Status ${response.status}`);
    
    const data = await response.json();
    logConsole('Demo workspace seeded successfully! Fetching workspaces list...', 'success');
    
    // Refresh user's workspaces
    await fetchWorkspaces();
    populateWorkspaceSelect();
    
    // Change to demo_workspace
    activeWorkspaceId = 'demo_workspace';
    localStorage.setItem('cord_active_workspace', activeWorkspaceId);
    workspaceSelect.value = activeWorkspaceId;
    
    logConsole('Switched active workspace to seeded demo_workspace.', 'success');
    loadTabContentData();
  } catch (err) {
    logConsole(`Demo workspace seeding failed: ${err.message}`, 'error');
    alert(`Demo Seeding Failed: ${err.message}`);
  } finally {
    seedBtn.disabled = false;
    seedBtn.textContent = 'Seed Demo Project';
  }
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
  
  logConsole(`Evaluation Model: ${data.diagnostics.eval_model}`, 'info', 'eval-diagnostics-console');
}


// --- Tab: Workflows ---
let currentWorkflowsFilter = 'all';
let selectedWorkflowId = null;
let currentWorkflowsList = [];

async function loadWorkflows() {
  const container = document.getElementById('workflows-container');
  container.innerHTML = '<div class="empty-state">Loading workflows...</div>';
  
  // Set up filter states payload
  const payload = {};
  if (currentWorkflowsFilter !== 'all') {
    payload.states = [currentWorkflowsFilter];
  }
  
  const data = await callWorkflowApi('/pilot/workflows', payload);
  if (!data || !data.workflows) {
    container.innerHTML = '<div class="empty-state">Failed to load workflows.</div>';
    document.getElementById('workflows-count-badge').textContent = '0 Active';
    return;
  }
  
  currentWorkflowsList = data.workflows;
  document.getElementById('workflows-count-badge').textContent = `${currentWorkflowsList.length} Workflows`;
  
  renderWorkflows(currentWorkflowsList);
  
  // Auto-select active workflow if it exists in the list
  if (selectedWorkflowId) {
    const stillExists = currentWorkflowsList.find(w => w.id === selectedWorkflowId);
    if (stillExists) {
      selectWorkflow(stillExists);
    } else {
      clearActiveWorkflowView();
    }
  } else {
    clearActiveWorkflowView();
  }
}

function filterWorkflows(state) {
  currentWorkflowsFilter = state;
  
  // Highlight correct filter pill
  document.querySelectorAll('.filter-bar button').forEach(btn => {
    btn.classList.remove('active-filter-pill');
  });
  const activePill = document.getElementById(`wf-filter-${state}`);
  if (activePill) {
    activePill.classList.add('active-filter-pill');
  }
  
  loadWorkflows();
}

function renderWorkflows(workflows) {
  const container = document.getElementById('workflows-container');
  if (workflows.length === 0) {
    container.innerHTML = '<div class="empty-state">No workflows found.</div>';
    return;
  }
  
  container.innerHTML = '';
  workflows.forEach(wf => {
    const card = document.createElement('div');
    card.className = `workflow-card ${wf.id === selectedWorkflowId ? 'active-wf-card' : ''}`;
    card.onclick = () => selectWorkflow(wf);
    
    const formattedDate = new Date(wf.created_at).toLocaleString();
    const priorityClass = `workflow-priority-${wf.priority}`;
    
    card.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
        <span style="font-size: 0.75rem; font-weight: 700; text-transform: uppercase;" class="${priorityClass}">
          ${wf.priority.toUpperCase()}
        </span>
        <span class="badge" style="font-size: 0.7rem; border-color: var(--border-color);">${wf.state.replace('_', ' ').toUpperCase()}</span>
      </div>
      <h4 style="margin: 0 0 0.5rem 0; font-size: 0.95rem; line-height: 1.3;">${escapeHtml(wf.title)}</h4>
      <div style="display: flex; justify-content: space-between; font-size: 0.75rem; color: var(--text-secondary);">
        <span>Type: ${wf.workflow_type.replace('_', ' ')}</span>
        <span>${formattedDate}</span>
      </div>
    `;
    container.appendChild(card);
  });
}

function clearActiveWorkflowView() {
  selectedWorkflowId = null;
  document.getElementById('active-workflow-view').style.display = 'none';
  document.getElementById('no-active-workflow-view').style.display = 'flex';
}

async function selectWorkflow(wf) {
  selectedWorkflowId = wf.id;
  
  // Highlight active card
  loadWorkflowsListHighlightOnly();

  document.getElementById('no-active-workflow-view').style.display = 'none';
  document.getElementById('active-workflow-view').style.display = 'block';
  
  document.getElementById('active-wf-title').textContent = wf.title;
  document.getElementById('active-wf-type-status').innerHTML = `
    <strong>Type:</strong> ${wf.workflow_type.replace('_', ' ')} | <strong>State:</strong> <span class="badge">${wf.state.toUpperCase()}</span>
  `;
  
  const assigneesText = wf.assigned_entities && wf.assigned_entities.length > 0
    ? wf.assigned_entities.map(e => `${e.name} (${e.type})`).join(', ')
    : 'None';
  document.getElementById('active-wf-assignees').textContent = assigneesText;
  document.getElementById('active-wf-priority').textContent = wf.priority.toUpperCase();
  document.getElementById('active-wf-created').textContent = new Date(wf.created_at).toLocaleString();
  
  // Load Recommendations
  const recsContainer = document.getElementById('active-wf-recommendations');
  recsContainer.innerHTML = '';
  const recommendations = wf.metadata && wf.metadata.recommendations
    ? wf.metadata.recommendations
    : ["No recommendations generated for this workflow type."];
  recommendations.forEach(rec => {
    const li = document.createElement('li');
    li.style.marginBottom = '0.5rem';
    li.textContent = rec;
    recsContainer.appendChild(li);
  });
  
  // Load Transition Log Trail
  const trailContainer = document.getElementById('active-wf-trail');
  trailContainer.innerHTML = '';
  const transitions = (wf.metadata && wf.metadata.state_transitions) || [];
  if (transitions.length === 0) {
    trailContainer.innerHTML = '<div style="font-size: 0.8rem; color: var(--text-muted);">No state transitions logged.</div>';
  } else {
    transitions.forEach(t => {
      const stepDiv = document.createElement('div');
      stepDiv.style.fontSize = '0.8rem';
      stepDiv.style.marginBottom = '0.75rem';
      const fromStr = t.from_state ? t.from_state.replace('_', ' ').toUpperCase() : 'INIT';
      const toStr = t.to_state.replace('_', ' ').toUpperCase();
      const transitionTime = new Date(t.timestamp).toLocaleString();
      stepDiv.innerHTML = `
        <div style="display: flex; justify-content: space-between; margin-bottom: 0.15rem;">
          <span><strong>${fromStr}</strong> &rarr; <strong>${toStr}</strong></span>
          <span style="color: var(--text-muted); font-size: 0.75rem;">${transitionTime}</span>
        </div>
        <div style="color: var(--text-secondary); font-style: italic;">"${escapeHtml(t.notes || 'No description provided.')}"</div>
      `;
      trailContainer.appendChild(stepDiv);
    });
    trailContainer.scrollTop = trailContainer.scrollHeight;
  }
  
  // Load Linked Assets (Events and Insights)
  const assetsContainer = document.getElementById('active-wf-assets');
  assetsContainer.innerHTML = '';
  const relatedEvents = wf.related_events || [];
  const relatedInsights = wf.related_insights || [];
  
  if (relatedEvents.length === 0 && relatedInsights.length === 0) {
    assetsContainer.innerHTML = '<div style="font-size: 0.8rem; color: var(--text-muted);">No operational assets linked.</div>';
  } else {
    relatedEvents.forEach(evtId => {
      const row = document.createElement('div');
      row.style.background = 'rgba(255, 255, 255, 0.02)';
      row.style.border = '1px solid var(--border-color)';
      row.style.borderRadius = '4px';
      row.style.padding = '0.5rem';
      row.style.fontSize = '0.8rem';
      row.style.display = 'flex';
      row.style.justifyContent = 'space-between';
      row.style.alignItems = 'center';
      row.innerHTML = `
        <span>⚡ <strong>Event:</strong> <span style="font-family: var(--font-mono); font-size: 0.75rem;">${evtId}</span></span>
        <button class="btn btn-outline btn-sm" onclick="showAssetDetails('event', '${evtId}')" style="padding: 0.15rem 0.4rem; font-size: 0.7rem;">View</button>
      `;
      assetsContainer.appendChild(row);
    });
    
    relatedInsights.forEach(insId => {
      const row = document.createElement('div');
      row.style.background = 'rgba(255, 255, 255, 0.02)';
      row.style.border = '1px solid var(--border-color)';
      row.style.borderRadius = '4px';
      row.style.padding = '0.5rem';
      row.style.fontSize = '0.8rem';
      row.style.display = 'flex';
      row.style.justifyContent = 'space-between';
      row.style.alignItems = 'center';
      row.innerHTML = `
        <span>💡 <strong>Insight:</strong> <span style="font-family: var(--font-mono); font-size: 0.75rem;">${insId}</span></span>
        <button class="btn btn-outline btn-sm" onclick="showAssetDetails('insight', '${insId}')" style="padding: 0.15rem 0.4rem; font-size: 0.7rem;">View</button>
      `;
      assetsContainer.appendChild(row);
    });
  }
  
  // Populate the Events dropdown list
  populateLinkableEventsDropdown();
}

function loadWorkflowsListHighlightOnly() {
  document.querySelectorAll('.workflow-card').forEach((c, idx) => {
    const wf = currentWorkflowsList[idx];
    if (wf && wf.id === selectedWorkflowId) {
      c.classList.add('active-wf-card');
    } else {
      c.classList.remove('active-wf-card');
    }
  });
}

async function populateLinkableEventsDropdown() {
  const selectEl = document.getElementById('linkable-events-select');
  selectEl.innerHTML = '<option value="">Loading events...</option>';
  
  const data = await callPilotApi('/pilot/timeline-analysis');
  if (!data || !data.timeline || data.timeline.length === 0) {
    selectEl.innerHTML = '<option value="">No linkable events in workspace</option>';
    return;
  }
  
  selectEl.innerHTML = '';
  data.timeline.forEach(evt => {
    const opt = document.createElement('option');
    opt.value = evt.id;
    opt.textContent = `[${evt.event_type.toUpperCase()}] ${evt.title.substring(0, 45)}...`;
    selectEl.appendChild(opt);
  });
}

async function linkAssetToActiveWorkflow() {
  if (!selectedWorkflowId) return;
  const selectEl = document.getElementById('linkable-events-select');
  const eventId = selectEl.value;
  if (!eventId) {
    alert("Please select a workspace event to link.");
    return;
  }
  
  logConsole(`Linking event ${eventId} to workflow ${selectedWorkflowId}...`, 'info');
  
  const updated = await callWorkflowApi(`/pilot/workflows/${selectedWorkflowId}/link`, {
    related_events: [eventId]
  });
  
  if (updated) {
    logConsole('Event successfully linked to workflow.', 'success');
    // Refresh the details view
    selectWorkflow(updated);
  } else {
    logConsole('Failed to link event to workflow.', 'error');
  }
}

async function transitionActiveWorkflow(targetState) {
  if (!selectedWorkflowId) return;
  const notesEl = document.getElementById('transition-notes');
  const notesText = notesEl.value.trim();
  
  logConsole(`Transitioning workflow to: ${targetState}...`, 'info');
  
  const updated = await callWorkflowApi(`/pilot/workflows/${selectedWorkflowId}/transition`, {
    state: targetState,
    user_notes: notesText || `State changed to ${targetState}.`
  });
  
  if (updated) {
    logConsole(`Workflow state transitioned to: ${targetState}.`, 'success');
    notesEl.value = '';
    // Refresh active workflow and parent list
    selectWorkflow(updated);
    loadWorkflows();
  } else {
    logConsole(`Failed to transition workflow state to: ${targetState}.`, 'error');
  }
}

async function submitCreateWorkflow() {
  const titleEl = document.getElementById('create-wf-title');
  const typeEl = document.getElementById('create-wf-type');
  const priorityEl = document.getElementById('create-wf-priority');
  const assigneeEl = document.getElementById('create-wf-assignee');
  
  const title = titleEl.value.trim();
  const type = typeEl.value;
  const priority = priorityEl.value;
  const assignee = assigneeEl.value.trim();
  
  if (!title) {
    alert("Please enter a workflow title.");
    return;
  }
  
  logConsole(`Initiating custom workflow: "${title}"...`, 'info');
  
  const payload = {
    title: title,
    workflow_type: type,
    state: 'pending_review',
    priority: priority,
    assigned_entities: assignee ? [{ name: assignee, type: 'team' }] : [],
    related_events: [],
    related_insights: [],
    metadata: {
      recommendations: [
        "Initialize verification checklist logs.",
        "Cluster related telemetry alarms and developer context logs."
      ]
    }
  };
  
  const newWf = await callWorkflowApi('/pilot/workflows/create', payload);
  if (newWf) {
    logConsole('Workflow initiated successfully.', 'success');
    titleEl.value = '';
    assigneeEl.value = '';
    
    // Select the new workflow
    selectedWorkflowId = newWf.id;
    // Reload workflows list
    await loadWorkflows();
    // Show details
    selectWorkflow(newWf);
  } else {
    logConsole('Failed to initiate custom workflow.', 'error');
  }
}

// Utility post helper specifically for workflow actions
async function callWorkflowApi(endpoint, body = {}) {
  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({ workspace_id: activeWorkspaceId, ...body })
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } catch (err) {
    logConsole(`Failed to call ${endpoint}: ${err.message}`, 'error');
    return null;
  }
}

// Helper to view linked asset details in existing modal
async function showAssetDetails(type, assetId) {
  const modal = document.getElementById('evidence-modal');
  const modalTitle = document.getElementById('modal-doc-title');
  const modalSource = document.getElementById('modal-doc-source');
  const modalAuthor = document.getElementById('modal-doc-author');
  const modalTime = document.getElementById('modal-doc-time');
  const modalContent = document.getElementById('modal-doc-content');
  
  modalTitle.textContent = `Linked Asset Details`;
  modalSource.textContent = `ID: ${assetId}`;
  modalAuthor.textContent = `TYPE: ${type.toUpperCase()}`;
  modalTime.textContent = `TIME: Loaded Context`;
  
  modalContent.textContent = `Loading asset details for ID ${assetId}...`;
  modal.style.display = 'flex';
  
  // Try to retrieve actual event or insight details from timeline or list
  try {
    if (type === 'event') {
      const data = await callPilotApi('/pilot/timeline-analysis');
      if (data && data.timeline) {
        const found = data.timeline.find(e => e.id === assetId);
        if (found) {
          modalTitle.textContent = found.title;
          modalSource.textContent = `SOURCE: ${found.event_type.toUpperCase()}`;
          modalTime.textContent = `TIMESTAMP: ${found.timestamp}`;
          modalContent.textContent = JSON.stringify(found, null, 2);
          return;
        }
      }
    }
    modalContent.textContent = `Asset details retrieved:
ID: ${assetId}
Type: ${type}
Workspace: ${activeWorkspaceId}

Use the search bar or timeline explorers to trace further causal paths.`;
  } catch (err) {
    modalContent.textContent = `Error loading details: ${err.message}`;
  }
}
