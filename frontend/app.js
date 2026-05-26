    // Constants & State
    let activeEndpoint = '/insights/root-causes';
    const workspaceInput = document.getElementById('workspace-id');
    const queryInput = document.getElementById('query-input');
    const statusConsole = document.getElementById('status-console');
    const activityPulse = document.getElementById('activity-pulse');

    // Setup endpoint selectors
    document.querySelectorAll('.endpoint-pill').forEach(pill => {
      pill.addEventListener('click', () => {
        document.querySelectorAll('.endpoint-pill').forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
        activeEndpoint = pill.getAttribute('data-endpoint');
        logConsole(`Endpoint switched to: ${activeEndpoint}`, 'info');
      });
    });

    // Populate quick queries
    document.querySelectorAll('.sample-query-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        queryInput.value = btn.getAttribute('data-query');
        logConsole(`Populated query text field.`, 'info');
      });
    });

    // Log helper
    function logConsole(message, type = '') {
      const line = document.createElement('div');
      line.className = `status-log-line ${type}`;
      const time = new Date().toLocaleTimeString();
      line.textContent = `[${time}] ${message}`;
      statusConsole.appendChild(line);
      statusConsole.scrollTop = statusConsole.scrollHeight;
    }

    // Default Query Run helper
    function runDefaultQuery() {
      queryInput.value = "Why did ServiceA fail after deployment?";
      document.getElementById('btn-submit-query').click();
    }

    // Modal toggling
    const modal = document.getElementById('evidence-modal');
    document.getElementById('modal-close-btn').addEventListener('click', () => {
      modal.style.display = 'none';
    });
    modal.addEventListener('click', (e) => {
      if (e.target === modal) {
        modal.style.display = 'none';
      }
    });

    function showDocumentModal(title, source, author, timestamp, content) {
      document.getElementById('modal-doc-title').textContent = title;
      document.getElementById('modal-doc-source').textContent = `SOURCE: ${source.toUpperCase()}`;
      document.getElementById('modal-doc-author').textContent = `AUTHOR: ${author || 'System'}`;
      document.getElementById('modal-doc-time').textContent = `TIME: ${timestamp}`;
      document.getElementById('modal-doc-content').textContent = content;
      modal.style.display = 'flex';
    }

    // Set interactive loader state
    function setLoading(isLoading) {
      if (isLoading) {
        activityPulse.classList.add('loading');
        document.getElementById('btn-submit-query').disabled = true;
        document.getElementById('btn-submit-query').textContent = "Processing Core Analysis...";
      } else {
        activityPulse.classList.remove('loading');
        document.getElementById('btn-submit-query').disabled = false;
        document.getElementById('btn-submit-query').textContent = "Run Diagnostic Query";
      }
    }

    // API Triggers
    document.getElementById('btn-submit-query').addEventListener('click', async () => {
      const query = queryInput.value.trim();
      const workspace_id = workspaceInput.value.trim() || 'default_workspace';
      
      if (!query) {
        logConsole("Error: Query text cannot be empty.", "error");
        alert("Please enter a diagnostic query.");
        return;
      }

      setLoading(true);
      logConsole(`Executing insight query on ${activeEndpoint}...`, 'info');

      try {
        const response = await fetch(activeEndpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query, limit: 10, workspace_id })
        });

        if (!response.ok) {
          throw new Error(`HTTP Error Status: ${response.status}`);
        }

        const data = await response.json();
        logConsole(`Query completed successfully in ${data.diagnostics?.execution_time_seconds || 0}s`, 'success');
        renderDashboardResults(data);
      } catch (err) {
        logConsole(`Query execution failed: ${err.message}`, 'error');
        console.error(err);
      } finally {
        setLoading(false);
      }
    });

    // Ingest Simulation Trigger
    document.getElementById('btn-demo-simulate').addEventListener('click', async () => {
      const workspace_id = workspaceInput.value.trim() || 'default_workspace';
      logConsole(`Triggering live demo incident simulation for workspace: ${workspace_id}...`, 'warning');
      
      try {
        const response = await fetch('/demo/simulate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ workspace_id })
        });
        
        if (!response.ok) throw new Error(`HTTP Error ${response.status}`);
        
        const data = await response.json();
        logConsole(`Simulation success: ${data.message}`, 'success');
        logConsole(`Simulated Notion, Slack, and Jira documents stored in Qdrant & SQLite.`, 'success');
      } catch (err) {
        logConsole(`Simulation failed: ${err.message}`, 'error');
      }
    });

    // Jira Sync Trigger
    document.getElementById('btn-jira-sync').addEventListener('click', async () => {
      const workspace_id = workspaceInput.value.trim() || 'default_workspace';
      logConsole(`Requesting Jira connector synchronization for workspace: ${workspace_id}...`, 'info');
      
      try {
        const response = await fetch('/connectors/jira/sync', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ workspace_id })
        });
        
        if (!response.ok) throw new Error(`HTTP Error ${response.status}`);
        
        const data = await response.json();
        logConsole(`Jira Integration Sync Complete. Synced ${data.synced_tickets_count} tickets successfully.`, 'success');
      } catch (err) {
        logConsole(`Jira Sync failed: ${err.message}`, 'error');
      }
    });

    // Render logic
    function renderDashboardResults(data) {
      // Hide Empty State
      document.getElementById('panel-empty-state').style.display = 'none';

      // 1. Render Summary Insights
      document.getElementById('insight-summary-card').style.display = 'block';
      document.getElementById('res-summary').textContent = data.insight?.summary || 'No summary insight returned.';
      document.getElementById('res-classification').textContent = data.query_type || 'Unknown query category';
      
      const confScore = Math.round((data.insight?.confidence_score || 0) * 100);
      document.getElementById('res-confidence-pct').textContent = `${confScore}%`;
      document.getElementById('res-confidence-fill').style.width = `${confScore}%`;
      document.getElementById('res-confidence-explanation').textContent = data.insight?.confidence_explanation || 'No confidence calculation diagnostics returned.';
      document.getElementById('res-execution-time').textContent = `Time: ${(data.diagnostics?.execution_time_seconds || 0).toFixed(4)}s`;

      // Show sections
      document.getElementById('timeline-correlations-section').style.display = 'grid';
      document.getElementById('evidence-section').style.display = 'block';

      // 2. Render Timeline Events
      const timelineCard = document.getElementById('timeline-card');
      const timelineList = document.getElementById('timeline-events-list');
      timelineList.innerHTML = '';
      
      const events = data.evidence?.events || [];
      if (events.length > 0) {
        timelineCard.style.display = 'block';
        events.forEach(ev => {
          const item = document.createElement('div');
          item.className = 'timeline-item';
          
          let dotType = 'general';
          if (ev.title?.toLowerCase().includes('deploy')) dotType = 'deploy';
          else if (ev.title?.toLowerCase().includes('outage') || ev.title?.toLowerCase().includes('fail') || ev.title?.toLowerCase().includes('bug')) dotType = 'incident';
          else if (ev.title?.toLowerCase().includes('escalat') || ev.title?.toLowerCase().includes('alert')) dotType = 'escalation';
          
          item.innerHTML = `
            <div class="timeline-dot ${dotType}"></div>
            <div class="timeline-content">
              <div class="timeline-meta">
                <span>${ev.event_type?.toUpperCase() || 'EVENT'}</span>
                <span>${new Date(ev.timestamp).toLocaleString()}</span>
              </div>
              <div class="timeline-title">${ev.title || 'Untitled Event'}</div>
              <div class="timeline-body">${ev.summary || ''}</div>
              <div class="timeline-tags">
                ${(ev.related_teams || []).map(team => `<span class="tag">${team}</span>`).join('')}
                ${(ev.entities || []).map(ent => `<span class="tag">${ent}</span>`).join('')}
              </div>
            </div>
          `;
          timelineList.appendChild(item);
        });
      } else {
        timelineCard.style.display = 'none';
      }

      // 3. Render SQLite Correlations
      const correlationsCard = document.getElementById('correlations-card');
      const correlationsList = document.getElementById('correlations-links-list');
      correlationsList.innerHTML = '';

      const correlations = data.evidence?.correlations || [];
      if (correlations.length > 0) {
        correlationsCard.style.display = 'block';
        correlations.forEach(corr => {
          // Format source ids cleanly
          const srcA = corr.source_a?.replace('doc_sim_', '')?.replace('doc_intel_', '') || 'Source A';
          const srcB = corr.source_b?.replace('doc_sim_', '')?.replace('doc_intel_', '') || 'Source B';
          
          const card = document.createElement('div');
          card.className = 'correlation-link-card';
          card.innerHTML = `
            <div style="flex-grow: 1;">
              <div class="correlation-nodes">
                <span>${srcA}</span>
                <span class="correlation-arrow">&harr;</span>
                <span>${srcB}</span>
              </div>
              <div class="correlation-reason">${corr.reason || 'No correlation justification given.'}</div>
            </div>
            <div>
              <span class="correlation-type-badge">${corr.correlation_type || 'link'}</span>
              <div style="font-size: 0.75rem; text-align: right; margin-top: 0.25rem; font-family: var(--font-mono); color: var(--accent-cyan);">
                S: ${corr.score ? corr.score.toFixed(2) : '1.00'}
              </div>
            </div>
          `;
          correlationsList.appendChild(card);
        });
      } else {
        correlationsCard.style.display = 'none';
      }

      // 4. Render Evidence Vector Chunks
      const evidenceList = document.getElementById('evidence-chunks-list');
      evidenceList.innerHTML = '';
      
      const chunks = data.evidence?.chunks || [];
      if (chunks.length > 0) {
        chunks.forEach(chunk => {
          const card = document.createElement('div');
          card.className = 'evidence-card';
          
          const source = chunk.source || 'document';
          const score = chunk.score || 0;
          const text = chunk.content || '';
          const title = chunk.title || chunk.metadata?.title || 'Knowledge Base Ref';
          const author = chunk.author || chunk.metadata?.author || 'System';
          const created = chunk.created_time || chunk.metadata?.created_time || 'N/A';
          
          card.innerHTML = `
            <div class="evidence-card-header">
              <span class="evidence-source">
                <span class="tag ${source}-tag">${source}</span>
              </span>
              <span class="evidence-score-badge">${score.toFixed(4)}</span>
            </div>
            <div class="evidence-text-preview">${text}</div>
            <div class="evidence-footer">
              <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 140px;" title="${title}">Doc: ${title}</span>
              <span>By ${author}</span>
            </div>
          `;
          
          card.addEventListener('click', () => {
            showDocumentModal(title, source, author, created, text);
          });
          
          evidenceList.appendChild(card);
        });
      } else {
        const noChunks = document.createElement('div');
        noChunks.className = 'empty-state';
        noChunks.style.gridColumn = '1 / -1';
        noChunks.textContent = 'No semantic vector documents returned for this search.';
        evidenceList.appendChild(noChunks);
      }
    }
