/**
 * SVANT Desktop Web Application Logic
 * Modern, clean, and beginner-accessible interface.
 */

document.addEventListener('DOMContentLoaded', () => {
  // Application State
  const state = {
    currentPage: 'dashboard',
    projects: [],
    activeProjectId: '',
    stats: null,
    files: [],
    selectedProjectForFiles: '',
    selectedCategoryForFiles: '',
    searchMode: 'keyword',
    projectStatuses: {},
    conversationId: null,
    chatHistory: [],
    settings: null,
    duplicateClusters: [],
  };

  // DOM Elements
  const navItems = document.querySelectorAll('.nav-item');
  const pageViews = document.querySelectorAll('.page-view');
  const pageTitle = document.getElementById('page-title');
  const pageSubtitle = document.getElementById('page-subtitle');
  const toastContainer = document.getElementById('toast-container');

  // Modals
  const modalAddProject = document.getElementById('modal-add-project');
  const modalFileDetail = document.getElementById('modal-file-detail');
  const modalCompareFiles = document.getElementById('modal-compare-files');

  // Formatters
  function formatBytes(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  function formatDate(isoStr) {
    if (!isoStr) return 'Never';
    try {
      const d = new Date(isoStr);
      return d.toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch (_) {
      return isoStr;
    }
  }

  // Toast Notifications
  function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(6px)';
      setTimeout(() => toast.remove(), 250);
    }, 3800);
  }

  // Helper: HTML Escaper
  function escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function escapeJs(str) {
    if (!str) return '';
    return str.replace(/'/g, "\\'").replace(/"/g, '\\"');
  }

  // Markdown Parser for Assistant Responses and Insight Modals
  function formatMarkdown(rawText) {
    if (rawText === null || rawText === undefined) return '';
    if (typeof rawText !== 'string') {
      if (typeof rawText === 'object') {
        if (typeof rawText.answer === 'string') rawText = rawText.answer;
        else if (typeof rawText.text === 'string') rawText = rawText.text;
        else if (typeof rawText.message === 'string') rawText = rawText.message;
        else if (typeof rawText.content === 'string') rawText = rawText.content;
        else rawText = JSON.stringify(rawText, null, 2);
      } else {
        rawText = String(rawText);
      }
    }
    const lines = rawText.split('\n');
    let html = '';
    let inList = false;
    let listType = 'ul';

    for (let i = 0; i < lines.length; i++) {
      let line = lines[i];

      // Code blocks ```code```
      if (line.startsWith('```')) {
        let codeContent = '';
        i++;
        while (i < lines.length && !lines[i].startsWith('```')) {
          codeContent += escapeHtml(lines[i]) + '\n';
          i++;
        }
        if (inList) { html += `</${listType}>`; inList = false; }
        html += `<pre><code>${codeContent}</code></pre>`;
        continue;
      }

      // Headings
      if (line.startsWith('### ')) {
        if (inList) { html += `</${listType}>`; inList = false; }
        html += `<h4>${formatInline(line.substring(4))}</h4>`;
        continue;
      }
      if (line.startsWith('## ')) {
        if (inList) { html += `</${listType}>`; inList = false; }
        html += `<h3>${formatInline(line.substring(3))}</h3>`;
        continue;
      }
      if (line.startsWith('# ')) {
        if (inList) { html += `</${listType}>`; inList = false; }
        html += `<h2>${formatInline(line.substring(2))}</h2>`;
        continue;
      }

      // Unordered lists
      if (line.match(/^[\*\-]\s+(.*)$/)) {
        const itemText = line.replace(/^[\*\-]\s+/, '');
        if (!inList || listType !== 'ul') {
          if (inList) html += `</${listType}>`;
          html += '<ul>';
          inList = true;
          listType = 'ul';
        }
        html += `<li>${formatInline(itemText)}</li>`;
        continue;
      }

      // Ordered lists
      if (line.match(/^\d+\.\s+(.*)$/)) {
        const itemText = line.replace(/^\d+\.\s+/, '');
        if (!inList || listType !== 'ol') {
          if (inList) html += `</${listType}>`;
          html += '<ol>';
          inList = true;
          listType = 'ol';
        }
        html += `<li>${formatInline(itemText)}</li>`;
        continue;
      }

      // Empty line closes lists
      if (!line.trim()) {
        if (inList) { html += `</${listType}>`; inList = false; }
        continue;
      }

      // Regular paragraph
      if (inList) { html += `</${listType}>`; inList = false; }
      html += `<p>${formatInline(line)}</p>`;
    }

    if (inList) { html += `</${listType}>`; }
    return html;
  }

  function formatInline(text) {
    let s = escapeHtml(text);
    // Bold **text**
    s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    // Italic *text*
    s = s.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    // Inline code `code`
    s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
    return s;
  }

  // Navigation Titles
  const pageTitles = {
    dashboard: { title: 'Project Overview', subtitle: 'Real-time summary of your local projects and files.' },
    projects: { title: 'Your Projects', subtitle: 'Tracked workspaces and repositories on your computer.' },
    files: { title: 'Project Files', subtitle: 'Explore scanned project files, text, and documents.' },
    search: { title: 'Search Your Projects', subtitle: 'Find information across code, documentation, and notes.' },
    security: { title: 'Security Problems', subtitle: 'Problems that could expose private keys, passwords, or risky settings.' },
    duplicates: { title: 'Duplicate Files', subtitle: 'Find files that have identical content and reclaim storage space.' },
    health: { title: 'Project Health', subtitle: 'See how healthy your project is and what you can improve.' },
    aichat: { title: 'SVANT Assistant', subtitle: 'Ask questions about your project in plain language.' },
    settings: { title: 'Settings', subtitle: 'Customize how SVANT works on your computer.' },
  };

  function switchPage(pageId) {
    state.currentPage = pageId;

    navItems.forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.page === pageId);
    });

    pageViews.forEach((view) => {
      view.classList.toggle('active', view.id === `page-${pageId}`);
    });

    const info = pageTitles[pageId] || { title: 'SVANT', subtitle: '' };
    pageTitle.textContent = info.title;
    pageSubtitle.textContent = info.subtitle;

    // Trigger page-specific data refresh
    if (pageId === 'dashboard') loadDashboardData();
    if (pageId === 'projects') loadProjectsView();
    if (pageId === 'files') loadFilesView();
    if (pageId === 'security') loadSecurityView();
    if (pageId === 'duplicates') loadDuplicatesView();
    if (pageId === 'health') loadHealthView();
    if (pageId === 'aichat') {
      updateAIStatusBadge();
      if (!state.projects.length) loadDashboardData();
    }
    if (pageId === 'settings') loadSettingsView();
  }

  navItems.forEach((btn) => {
    btn.addEventListener('click', () => {
      const pageId = btn.dataset.page;
      switchPage(pageId);
    });
  });

  // Backend Health Polling
  async function checkHealth() {
    try {
      const data = await API.getHealth();
      const dot = document.getElementById('status-dot');
      const label = document.getElementById('status-label');
      const dataDirTag = document.getElementById('data-dir-preview');

      if (data.status === 'ok') {
        dot.className = 'status-indicator live';
        label.textContent = 'SVANT is Active';
        dataDirTag.textContent = data.data_dir;
      }
    } catch (_) {
      const dot = document.getElementById('status-dot');
      const label = document.getElementById('status-label');
      dot.className = 'status-indicator error';
      label.textContent = 'SVANT Offline';
    }
  }

  // Load Dashboard Data
  async function loadDashboardData() {
    try {
      const [stats, projects] = await Promise.all([API.getStats(), API.getProjects()]);
      state.stats = stats;
      state.projects = projects;

      // Update counters
      document.getElementById('stat-projects').textContent = stats.total_projects;
      document.getElementById('stat-files').textContent = stats.total_files.toLocaleString();
      document.getElementById('stat-files-size').textContent = `${formatBytes(stats.total_size_bytes)} total space`;
      document.getElementById('stat-indexed').textContent = `${stats.total_indexed_files.toLocaleString()} files`;
      document.getElementById('stat-last-scan').textContent = stats.last_scanned_at
        ? `Last checked: ${formatDate(stats.last_scanned_at)}`
        : 'No scans completed yet';

      // Update badges
      document.getElementById('nav-project-count').textContent = stats.total_projects;
      document.getElementById('nav-file-count').textContent = stats.total_files;

      // Render mini project list
      const miniList = document.getElementById('dashboard-projects-list');
      if (projects.length === 0) {
        miniList.innerHTML = `<div class="empty-state">No projects added yet. Click "Track New Project" above to get started.</div>`;
      } else {
        const folderColors = ['purple', 'green', 'yellow', 'blue'];
        miniList.innerHTML = projects
          .slice(0, 5)
          .map(
            (p, idx) => `
          <div class="mini-project-item">
            <div class="mini-proj-icon ${folderColors[idx % 4]}">📁</div>
            <div class="mini-proj-info">
              <h4>${escapeHtml(p.name)}</h4>
              <p>${escapeHtml(p.root_path)}</p>
            </div>
            <div class="mini-proj-meta">
              <span class="badge">${p.file_count} files</span>
              <button class="btn btn-scan-pill btn-sm" onclick="window.triggerScan('${p.id}')">
                <svg class="btn-icon" viewBox="0 0 24 24"><path d="M4 4h4v2H6v2H4V4zm16 0h-4v2h2v2h2V4zM4 20h4v-2H6v-2H4v4zm16 0h-4v-2h2v-2h2v4zM8 8h8v8H8V8z"/></svg>
                <span>Scan</span>
              </button>
            </div>
          </div>
        `
          )
          .join('');
      }

      // Render Category distribution
      const catBox = document.getElementById('category-distribution');
      const categories = stats.categories || {};
      const entries = Object.entries(categories);

      const categoryLabels = {
        binary: 'Binary',
        config: 'Config',
        data: 'Data',
        document: 'Document',
        other: 'Other',
        source: 'Source',
      };

      if (entries.length === 0) {
        catBox.innerHTML = `<div class="empty-state">Add and check a project to see file types and distribution.</div>`;
      } else {
        const total = stats.total_files || 1;
        catBox.innerHTML = entries
          .map(([cat, data]) => {
            const pct = Math.round((data.count / total) * 100);
            const label = categoryLabels[cat] || cat;
            return `
            <div class="category-row cat-${cat}" data-cat="${cat}">
              <div class="category-meta">
                <span class="category-name"><span class="cat-dot cat-${cat}"></span>${label} (${data.count})</span>
                <span class="category-stats">${formatBytes(data.size)} · ${pct}%</span>
              </div>
              <div class="progress-track">
                <div class="progress-fill cat-${cat}" style="width: ${pct}%"></div>
              </div>
            </div>
          `;
          })
          .join('');
      }
    } catch (err) {
      showToast(`Failed to load project overview: ${err.message}`, 'error');
    }
  }

  // Projects View
  async function loadProjectsView() {
    try {
      const projects = await API.getProjects();
      state.projects = projects;

      // Fetch index status for all projects
      const statuses = await Promise.all(
        projects.map((p) =>
          API.getIndexStatus(p.id).catch(() => ({ status: 'not_indexed', total_chunks: 0, total_vectors: 0 }))
        )
      );
      state.projectStatuses = {};
      projects.forEach((p, idx) => {
        state.projectStatuses[p.id] = statuses[idx];
      });

      renderProjectsGrid(projects);
      updateProjectFilterDropdowns(projects);
    } catch (err) {
      showToast(`Error fetching projects: ${err.message}`, 'error');
    }
  }

  function renderProjectsGrid(projects) {
    const grid = document.getElementById('projects-grid');
    if (projects.length === 0) {
      grid.innerHTML = `
        <div class="empty-state-card" style="grid-column: 1/-1;">
          <div class="empty-icon">📁</div>
          <h3>No Projects Added Yet</h3>
          <p>Add your first local project folder to search code, check security, and inspect project health.</p>
        </div>
      `;
      return;
    }

    grid.innerHTML = projects
      .map((p) => {
        const idxInfo = state.projectStatuses[p.id] || { status: 'not_indexed', total_chunks: 0, total_vectors: 0 };
        const idxLabel = idxInfo.status === 'indexed'
          ? `Analyzed (${idxInfo.total_chunks} sections)`
          : idxInfo.status === 'indexing'
          ? 'Analyzing...'
          : 'Not Analyzed';
        const idxClass = idxInfo.status === 'indexed' ? 'document' : idxInfo.status === 'indexing' ? 'source' : 'binary';
        const isIndexing = idxInfo.status === 'indexing';

        return `
      <div class="project-card">
        <div class="project-card-header">
          <div>
            <div class="project-title">${escapeHtml(p.name)}</div>
            <div class="project-path" title="${escapeHtml(p.root_path)}">${escapeHtml(p.root_path)}</div>
          </div>
          <div style="display: flex; gap: 6px; align-items: center;">
            <span class="tag-cat ${p.status === 'ready' ? 'document' : 'binary'}">${p.status === 'ready' ? 'Ready' : p.status}</span>
            <span class="tag-cat ${idxClass}">${idxLabel}</span>
          </div>
        </div>

        <div class="project-stats-row">
          <div class="proj-stat-item">
            <span class="proj-stat-label">Files</span>
            <span class="proj-stat-val">${p.file_count.toLocaleString()}</span>
          </div>
          <div class="proj-stat-item">
            <span class="proj-stat-label">Size</span>
            <span class="proj-stat-val">${formatBytes(p.total_size_bytes)}</span>
          </div>
          <div class="proj-stat-item">
            <span class="proj-stat-label">Sections</span>
            <span class="proj-stat-val">${(idxInfo.total_vectors || 0).toLocaleString()}</span>
          </div>
          <div class="proj-stat-item">
            <span class="proj-stat-label">Last Check</span>
            <span class="proj-stat-val" style="font-size: 11.5px;">${formatDate(p.last_scanned_at)}</span>
          </div>
        </div>

        <div class="project-actions">
          <button class="btn btn-secondary btn-sm" onclick="window.viewProjectFiles('${p.id}')">View Files</button>
          <button class="btn btn-secondary btn-sm" onclick="window.triggerScan('${p.id}')" title="Read folder and extract text">Check Files</button>
          <button class="btn btn-primary btn-sm" onclick="window.triggerIndex('${p.id}')" ${isIndexing ? 'disabled' : ''} title="Prepare sections for search and AI">${isIndexing ? 'Analyzing...' : 'Update Search Info'}</button>
          <button class="btn btn-ghost btn-sm" onclick="window.triggerReindex('${p.id}')" ${isIndexing ? 'disabled' : ''} title="Rebuild search data from scratch">Reset Search Info</button>
          <button class="btn btn-danger btn-sm" onclick="window.confirmUntrack('${p.id}', '${escapeJs(p.name)}')">Remove</button>
        </div>
      </div>
    `;
      })
      .join('');
  }

  function updateProjectFilterDropdowns(projects) {
    if (!state.activeProjectId && projects.length > 0) {
      state.activeProjectId = projects[0].id;
    } else if (state.activeProjectId && !projects.some((p) => p.id === state.activeProjectId)) {
      state.activeProjectId = projects.length ? projects[0].id : '';
    }

    const fileSelect = document.getElementById('file-filter-project');
    const searchSelect = document.getElementById('search-project-select');
    const chatSelect = document.getElementById('chat-project-select');
    const healthSelect = document.getElementById('health-project-select');
    const secSelect = document.getElementById('security-project-select');
    const dupSelect = document.getElementById('duplicates-project-select');

    const optionsWithAll = [
      '<option value="">All Projects</option>',
      ...projects.map((p) => `<option value="${p.id}">${escapeHtml(p.name)}</option>`),
    ].join('');

    const optionsForTracked = [
      '<option value="">Across All Tracked Projects</option>',
      ...projects.map((p) => `<option value="${p.id}">${escapeHtml(p.name)}</option>`),
    ].join('');

    const specificOptions = projects.length > 0
      ? projects.map((p) => `<option value="${p.id}">${escapeHtml(p.name)}</option>`).join('')
      : '<option value="">No projects added yet</option>';

    if (fileSelect) {
      fileSelect.innerHTML = optionsWithAll;
      if (state.selectedProjectForFiles) fileSelect.value = state.selectedProjectForFiles;
    }
    if (searchSelect) {
      searchSelect.innerHTML = optionsForTracked;
      if (state.activeProjectId) searchSelect.value = state.activeProjectId;
    }
    if (chatSelect) {
      chatSelect.innerHTML = specificOptions;
      if (state.activeProjectId) chatSelect.value = state.activeProjectId;
    }
    if (healthSelect) {
      healthSelect.innerHTML = specificOptions;
      if (state.activeProjectId) healthSelect.value = state.activeProjectId;
    }
    if (secSelect) {
      secSelect.innerHTML = specificOptions;
      if (state.activeProjectId) secSelect.value = state.activeProjectId;
    }
    if (dupSelect) {
      dupSelect.innerHTML = specificOptions;
      if (state.activeProjectId) dupSelect.value = state.activeProjectId;
    }
  }

  // Scan Action
  window.triggerScan = async function (projectId) {
    showToast('Reading project files & extracting text...', 'info');
    try {
      const res = await API.scanProject(projectId);
      showToast(`Finished checking: ${res.total_scanned} files processed in ${res.duration_seconds}s`, 'success');
      loadDashboardData();
      if (state.currentPage === 'projects') loadProjectsView();
      if (state.currentPage === 'files') loadFilesView();
    } catch (err) {
      showToast(`Check failed: ${err.message}`, 'error');
    }
  };

  // Index Action
  window.triggerIndex = async function (projectId) {
    if (state.projectStatuses[projectId]?.status === 'indexing') {
      showToast('This project is already being analyzed.', 'warning');
      return;
    }
    state.projectStatuses[projectId] = {
      ...(state.projectStatuses[projectId] || {}),
      status: 'indexing',
    };
    if (state.currentPage === 'projects') renderProjectsGrid(state.projects);

    showToast('Analyzing project sections for search...', 'info');
    try {
      const res = await API.indexProject(projectId);
      showToast(
        `Search info updated: ${res.indexed_files} files (${res.total_chunks} sections analyzed) in ${res.duration_seconds}s`,
        'success'
      );
    } catch (err) {
      showToast(`Update failed: ${err.message}`, 'error');
    } finally {
      loadDashboardData();
      if (state.currentPage === 'projects') loadProjectsView();
    }
  };

  // Re-index Action
  window.triggerReindex = async function (projectId) {
    if (state.projectStatuses[projectId]?.status === 'indexing') {
      showToast('This project is already being analyzed.', 'warning');
      return;
    }
    if (!confirm('This will rebuild search information from scratch for this project. Your original files on your computer will not be touched. Proceed?')) return;
    state.projectStatuses[projectId] = {
      ...(state.projectStatuses[projectId] || {}),
      status: 'indexing',
    };
    if (state.currentPage === 'projects') renderProjectsGrid(state.projects);

    showToast('Rebuilding search information...', 'info');
    try {
      const res = await API.rebuildIndex(projectId);
      showToast(`Search info rebuilt: ${res.total_chunks} sections ready in ${res.duration_seconds}s`, 'success');
    } catch (err) {
      showToast(`Rebuild failed: ${err.message}`, 'error');
    } finally {
      loadDashboardData();
      if (state.currentPage === 'projects') loadProjectsView();
    }
  };

  // Remove Project
  window.confirmUntrack = async function (projectId, name) {
    const ok = confirm(`Remove "${name}" from SVANT?\n\nNote: Original files on your computer will NOT be deleted or touched.`);
    if (!ok) return;

    try {
      await API.deleteProject(projectId);
      if (state.activeProjectId === projectId) {
        state.activeProjectId = '';
      }
      if (state.selectedProjectForFiles === projectId) {
        state.selectedProjectForFiles = '';
      }
      showToast(`Removed "${name}" from SVANT. Files on your computer were untouched.`, 'info');
      loadProjectsView();
      loadDashboardData();
    } catch (err) {
      showToast(`Failed to remove project: ${err.message}`, 'error');
    }
  };

  // Explore Files for Project
  window.viewProjectFiles = function (projectId) {
    state.activeProjectId = projectId;
    state.selectedProjectForFiles = projectId;
    const select = document.getElementById('file-filter-project');
    if (select) select.value = projectId;
    switchPage('files');
  };

  // Files View
  async function loadFilesView() {
    const projectFilter = document.getElementById('file-filter-project')?.value || '';
    const categoryFilter = document.getElementById('file-filter-category')?.value || '';
    const searchFilter = document.getElementById('file-search-input')?.value || '';

    try {
      const files = await API.getFiles({
        projectId: projectFilter || undefined,
        category: categoryFilter || undefined,
        search: searchFilter || undefined,
      });
      state.files = files;
      renderFilesTable(files);
    } catch (err) {
      showToast(`Failed to fetch files: ${err.message}`, 'error');
    }
  }

  function renderFilesTable(files) {
    const tbody = document.getElementById('files-table-body');
    if (files.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="text-center empty-cell" style="padding: 32px; text-align: center; color: var(--text-dim);">No files matched the current filters.</td></tr>`;
      return;
    }

    const categoryLabels = {
      source: 'Source Code',
      document: 'Document',
      config: 'Config',
      data: 'Data',
      binary: 'Binary',
      other: 'Other',
    };

    tbody.innerHTML = files
      .map(
        (f) => `
      <tr>
        <td style="font-weight: 600;">${escapeHtml(f.filename)}</td>
        <td style="color: var(--text-muted);">${escapeHtml(f.project_name || 'Project')}</td>
        <td style="font-family: var(--font-mono); font-size: 11.5px; color: var(--text-dim);">${escapeHtml(f.relative_path)}</td>
        <td><span class="tag-cat ${f.category}">${categoryLabels[f.category] || f.category}</span></td>
        <td style="font-family: var(--font-mono); font-size: 11.5px;">${formatBytes(f.size_bytes)}</td>
        <td style="font-size: 11.5px; color: var(--text-dim);">${formatDate(f.modified_time)}</td>
        <td><span class="tag-cat ${f.indexed_status === 'indexed' ? 'document' : 'other'}">${f.indexed_status === 'indexed' ? 'Analyzed' : 'Not Analyzed'}</span></td>
        <td><button class="btn btn-ghost btn-sm" onclick="window.viewFileDetail('${f.id}')">View Details</button></td>
      </tr>
    `
      )
      .join('');
  }

  // File Detail Modal
  window.viewFileDetail = async function (fileId) {
    try {
      const detail = await API.getFileDetail(fileId);
      document.getElementById('modal-file-title').textContent = detail.filename;
      document.getElementById('meta-file-path').textContent = detail.path;
      document.getElementById('meta-file-size').textContent = `${formatBytes(detail.size_bytes)} (${detail.size_bytes} bytes)`;
      document.getElementById('meta-file-cat').textContent = `${detail.category} (${detail.extension})`;
      document.getElementById('meta-file-mtime').textContent = formatDate(detail.modified_time);
      document.getElementById('meta-file-extstatus').textContent = detail.extraction_status === 'completed' ? 'Successfully Extracted' : (detail.extraction_status || 'Not extracted');
      document.getElementById('meta-file-sha').textContent = detail.sha256 ? detail.sha256.substring(0, 16) + '...' : 'N/A';
      document.getElementById('preview-char-count').textContent = `${(detail.char_count || 0).toLocaleString()} characters extracted`;
      document.getElementById('modal-file-content').textContent = detail.content_preview || '(No text extracted or file is binary)';
      modalFileDetail.classList.add('active');
    } catch (err) {
      showToast(`Could not load file details: ${err.message}`, 'error');
    }
  };

  // Search View & Mode Switching
  state.searchMode = localStorage.getItem('svant_default_search') || 'hybrid';
  const modeTabs = document.querySelectorAll('.mode-tab');
  const searchModeExplainer = document.getElementById('search-mode-desc');

  const modeExplainers = {
    keyword: '<strong>Search by Words:</strong> Finds exact words and phrases in your files.',
    semantic: '<strong>Search by Meaning:</strong> Finds related ideas and concepts even when different words are used.',
    hybrid: '<strong>Smart Search:</strong> Combines exact words and meaning for the best overall results.',
  };

  const modePlaceholders = {
    keyword: 'Type exact words or phrases to search...',
    semantic: 'Search by meaning (e.g. "how are passwords stored?")...',
    hybrid: 'Type what you are looking for with smart search...',
  };

  // Sync initial tab and explainer with default preference
  modeTabs.forEach((t) => {
    t.classList.toggle('active', t.dataset.mode === state.searchMode);
  });
  const initialQInput = document.getElementById('search-query-input');
  if (initialQInput) initialQInput.placeholder = modePlaceholders[state.searchMode] || 'Type what you are looking for...';
  if (searchModeExplainer) searchModeExplainer.innerHTML = modeExplainers[state.searchMode] || '';

  modeTabs.forEach((tab) => {
    tab.addEventListener('click', () => {
      modeTabs.forEach((t) => t.classList.remove('active'));
      tab.classList.add('active');
      state.searchMode = tab.dataset.mode || 'hybrid';

      const qInput = document.getElementById('search-query-input');
      qInput.placeholder = modePlaceholders[state.searchMode] || 'Type what you are looking for...';
      if (searchModeExplainer) {
        searchModeExplainer.innerHTML = modeExplainers[state.searchMode] || '';
      }

      if (qInput.value.trim()) {
        runSearch();
      }
    });
  });

  async function runSearch() {
    const queryInput = document.getElementById('search-query-input');
    const projectSelect = document.getElementById('search-project-select');
    const container = document.getElementById('search-results-container');

    const query = queryInput.value.trim();
    if (!query) {
      showToast('Please type something to search for.', 'info');
      return;
    }

    const currentMode = state.searchMode || 'keyword';
    const friendlyModeLabels = {
      keyword: 'Search by Words',
      semantic: 'Search by Meaning',
      hybrid: 'Smart Search',
    };

    container.innerHTML = `
      <div class="search-initial-state">
        <div class="hint-icon">⚡</div>
        <h3>Searching files with ${friendlyModeLabels[currentMode]}...</h3>
      </div>
    `;

    try {
      const res = await API.search({
        query: query,
        projectId: projectSelect.value || undefined,
        mode: currentMode,
      });

      if (res.results.length === 0) {
        container.innerHTML = `
          <div class="search-initial-state">
            <div class="hint-icon">🔍</div>
            <h3>No Matches Found</h3>
            <p>No files matched "<strong>${escapeHtml(query)}</strong>" using ${friendlyModeLabels[currentMode]}. Try searching with different words or use Smart Search.</p>
          </div>
        `;
        return;
      }

      container.innerHTML = `
        <div style="font-size: 13px; color: var(--text-dim); margin-bottom: 8px;">
          Found ${res.total} matching sections (${friendlyModeLabels[currentMode]})
        </div>
        ${res.results
          .map((hit) => {
            const matchTag = hit.match_mode && hit.match_mode.includes('semantic')
              ? 'By Meaning'
              : (hit.match_mode && hit.match_mode.includes('hybrid') ? 'Smart Match' : 'By Words');

            const scoreBadge = hit.score !== undefined
              ? (hit.score > 0.75 ? 'Strong Match' : 'Good Match')
              : '';

            return `
          <div class="search-hit-card" onclick="window.viewFileDetail('${hit.file_id}')">
            <div class="search-hit-header">
              <span class="search-hit-title">${escapeHtml(hit.filename)}</span>
              <div style="display: flex; gap: 8px; align-items: center;">
                <span class="tag-cat document">${matchTag}</span>
                ${scoreBadge ? `<span class="health-meta-badge badge-low">${scoreBadge}</span>` : ''}
                <span class="search-hit-proj">${escapeHtml(hit.project_name)}</span>
              </div>
            </div>
            <div class="search-hit-path">${escapeHtml(hit.relative_path)}</div>
            <div class="search-snippet">${hit.snippet}</div>
          </div>
        `;
          })
          .join('')}
      `;
    } catch (err) {
      showToast(`Search error: ${err.message}`, 'error');
      container.innerHTML = `
        <div class="search-initial-state">
          <div class="hint-icon">⚠️</div>
          <h3>Search Problem</h3>
          <p>${escapeHtml(err.message)}</p>
        </div>
      `;
    }
  }

  // Event Listeners for Add Project Modal
  document.getElementById('btn-open-add-project').addEventListener('click', () => {
    modalAddProject.classList.add('active');
    document.getElementById('input-project-path').focus();
  });

  document.getElementById('btn-close-add-modal').addEventListener('click', () => {
    modalAddProject.classList.remove('active');
  });

  document.getElementById('btn-cancel-add-project').addEventListener('click', () => {
    modalAddProject.classList.remove('active');
  });

  document.getElementById('btn-close-detail-modal').addEventListener('click', () => {
    modalFileDetail.classList.remove('active');
  });

  document.getElementById('btn-close-detail').addEventListener('click', () => {
    modalFileDetail.classList.remove('active');
  });

  document.getElementById('btn-submit-add-project').addEventListener('click', async () => {
    const pathInput = document.getElementById('input-project-path');
    const nameInput = document.getElementById('input-project-name');
    const pathVal = pathInput.value.trim();
    const nameVal = nameInput.value.trim();

    if (!pathVal) {
      showToast('Please enter the folder location on your computer.', 'error');
      return;
    }

    try {
      const newProj = await API.createProject(pathVal, nameVal);
      showToast(`Added project "${newProj.name}" successfully!`, 'success');
      state.activeProjectId = newProj.id;
      modalAddProject.classList.remove('active');
      pathInput.value = '';
      nameInput.value = '';
      loadProjectsView();
      loadDashboardData();

      if (confirm(`Project "${newProj.name}" was added. Would you like to check its files now?`)) {
        window.triggerScan(newProj.id);
      }
    } catch (err) {
      showToast(`Could not add project: ${err.message}`, 'error');
    }
  });

  document.getElementById('btn-refresh-projects').addEventListener('click', () => {
    loadDashboardData();
  });

  document.getElementById('btn-filter-files').addEventListener('click', () => {
    loadFilesView();
  });

  document.getElementById('btn-run-search').addEventListener('click', runSearch);

  document.getElementById('search-query-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') runSearch();
  });

  document.getElementById('project-filter-input').addEventListener('input', (e) => {
    const term = e.target.value.toLowerCase();
    const filtered = state.projects.filter(
      (p) => p.name.toLowerCase().includes(term) || p.root_path.toLowerCase().includes(term)
    );
    renderProjectsGrid(filtered);
  });

  // ==========================================================================
  // SVANT Assistant Logic (AI Chat)
  // ==========================================================================

  async function updateAIStatusBadge() {
    const badge = document.getElementById('chat-provider-badge');
    if (!badge) return;
    try {
      const status = await API.getAIStatus();
      if (status.active_provider === 'gemini') {
        badge.textContent = `Gemini AI`;
        badge.className = 'badge-provider live';
      } else if (status.active_provider === 'mock') {
        badge.textContent = 'Test Mode';
        badge.className = 'badge-provider test';
      } else if (status.local_only_mode) {
        badge.textContent = 'Works on Your Computer';
        badge.className = 'badge-provider local';
      } else {
        badge.textContent = status.is_available ? 'Assistant Ready' : 'Assistant Offline';
        badge.className = 'badge-provider';
      }
    } catch (_) {
      badge.textContent = 'Assistant Ready';
      badge.className = 'badge-provider';
    }
  }

  async function sendChatMessage() {
    const input = document.getElementById('chat-input');
    const sendBtn = document.getElementById('btn-chat-send');
    const stream = document.getElementById('chat-stream');
    const projSelect = document.getElementById('chat-project-select');
    const modeSelect = document.getElementById('chat-mode-select');
    const topkSelect = document.getElementById('chat-topk-select');

    const text = input.value.trim();
    if (!text) return;

    // Remove welcome card if still visible
    const welcomeCard = document.getElementById('chat-welcome');
    if (welcomeCard) welcomeCard.remove();

    input.disabled = true;
    sendBtn.disabled = true;

    // User Bubble
    const userRow = document.createElement('div');
    userRow.className = 'chat-message-row user';
    userRow.innerHTML = `
      <div class="chat-bubble">
        <div>${escapeHtml(text)}</div>
      </div>
    `;
    stream.appendChild(userRow);
    stream.scrollTop = stream.scrollHeight;

    // Typing Indicator
    const typingRow = document.createElement('div');
    typingRow.className = 'chat-message-row assistant';
    typingRow.id = 'chat-typing-row';
    typingRow.innerHTML = `
      <div class="chat-bubble">
        <div class="typing-dots">
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
        </div>
      </div>
    `;
    stream.appendChild(typingRow);
    stream.scrollTop = stream.scrollHeight;

    try {
      const res = await API.chat({
        message: text,
        projectId: projSelect.value || undefined,
        searchMode: modeSelect.value || 'hybrid',
        topK: parseInt(topkSelect.value, 10) || 5,
        conversationId: state.conversationId || undefined,
        history: state.chatHistory && state.chatHistory.length > 0 ? state.chatHistory : undefined,
      });

      typingRow.remove();

      if (res.conversation_id) {
        state.conversationId = res.conversation_id;
      }

      let answerText = '';
      if (typeof res.answer === 'string') {
        answerText = res.answer;
      } else if (res.answer && typeof res.answer === 'object') {
        answerText = res.answer.text || res.answer.content || res.answer.summary || res.answer.message || JSON.stringify(res.answer, null, 2);
      } else if (typeof res === 'string') {
        answerText = res;
      } else if (res && typeof res === 'object') {
        answerText = res.text || res.message || res.summary || 'SVANT generated an answer for your project.';
      } else {
        answerText = 'SVANT generated an answer for your project.';
      }

      state.chatHistory.push({ role: 'user', content: text });
      state.chatHistory.push({ role: 'assistant', content: answerText });
      if (state.chatHistory.length > 10) {
        state.chatHistory = state.chatHistory.slice(-10);
      }

      const sources = res.sources || res.citations || [];
      const redactionCount = res.redactions !== undefined ? res.redactions : (res.redactions_count || 0);

      const redactionHtml = redactionCount > 0
        ? `<span class="redaction-indicator" title="Private information was found and masked before processing">🛡️ ${redactionCount} Private Values Protected</span>`
        : '';

      const citationsHtml = sources.length > 0
        ? `
        <div class="citations-box">
          <div class="citations-header">
            <span>Where we found this:</span>
            <span class="citations-count-badge">${sources.length} file section${sources.length > 1 ? 's' : ''}</span>
          </div>
          <div class="citations-list">
            ${sources.map((c) => {
              const loc = c.location || (c.start_line && c.end_line ? `Lines ${c.start_line}–${c.end_line}` : `Section #${(c.chunk_index !== undefined ? c.chunk_index : 0)}`);
              const snippetText = c.snippet_preview || c.snippet || '';
              return `
                <div class="citation-card" onclick="window.viewFileDetail('${c.file_id}')" title="Click to view file: ${escapeHtml(c.relative_path || c.filename)}">
                  <div class="citation-top">
                    <div>
                      <span class="citation-filename">📄 ${escapeHtml(c.filename)}</span>
                      <span class="citation-location">(${loc})</span>
                    </div>
                  </div>
                  <div class="citation-snippet">${escapeHtml(snippetText)}</div>
                </div>
              `;
            }).join('')}
          </div>
        </div>
        `
        : '';

      const modeLabels = {
        hybrid: 'Smart Search',
        semantic: 'Search by Meaning',
        keyword: 'Search by Words',
      };

      const assistantRow = document.createElement('div');
      assistantRow.className = 'chat-message-row assistant';
      assistantRow.innerHTML = `
        <div class="chat-bubble">
          <div class="bubble-header">
            <span class="assistant-tag">✨ SVANT Assistant</span>
            ${redactionHtml}
          </div>
          <div class="assistant-text">${formatMarkdown(answerText)}</div>
          ${citationsHtml}
          <div class="bubble-meta-footer">
            <span>Search: ${modeLabels[res.mode] || 'Smart Search'}</span>
            <span>·</span>
            <span>${res.context_count !== undefined ? res.context_count : sources.length} sections used</span>
            <span>·</span>
            <span>Grounded in project files</span>
          </div>
        </div>
      `;
      stream.appendChild(assistantRow);
      input.value = '';
    } catch (err) {
      typingRow.remove();
      const rawError = err && err.message ? String(err.message) : 'Unknown connection or processing error';
      const cleanError = rawError.replace(/\[object Object\]/g, 'Validation error or unexpected data format');
      const escapedQuestion = escapeHtml(text).replace(/'/g, "\\'");

      const errorRow = document.createElement('div');
      errorRow.className = 'chat-message-row assistant';
      errorRow.innerHTML = `
        <div class="chat-bubble error-bubble" style="border-color: var(--pastel-pink-border); background-color: var(--pastel-pink-bg);">
          <div class="bubble-header">
            <span class="assistant-tag" style="color: var(--pastel-pink-text); font-weight: 700;">⚠️ SVANT couldn't answer that right now.</span>
          </div>
          <div class="assistant-text" style="color: var(--pastel-pink-text); margin-bottom: 8px;">
            We encountered a problem while generating an answer for your project. Please make sure a project is selected and analyzed, then try again.
          </div>
          <div style="margin-top: 10px; margin-bottom: 6px;">
            <button class="btn btn-secondary btn-sm" id="btn-chat-retry-${Date.now()}" onclick="window.retryChatMessage('${escapedQuestion}')" style="background-color: var(--bg-card); border-color: var(--pastel-pink-border); color: var(--pastel-pink-text); cursor: pointer;">
              🔄 Try again
            </button>
          </div>
          <details class="tech-details-accordion" style="margin-top: 8px; font-size: 11.5px; color: var(--text-muted);">
            <summary style="cursor: pointer; font-weight: 600;">Technical details</summary>
            <div style="margin-top: 6px; padding: 8px 10px; background-color: rgba(0, 0, 0, 0.04); border-radius: var(--radius-xs); font-family: var(--font-mono); font-size: 11px; white-space: pre-wrap; word-break: break-word;">${escapeHtml(cleanError)}</div>
          </details>
        </div>
      `;
      stream.appendChild(errorRow);
    } finally {
      input.disabled = false;
      sendBtn.disabled = false;
      input.focus();
      stream.scrollTop = stream.scrollHeight;
    }
  }

  window.retryChatMessage = function (text) {
    const input = document.getElementById('chat-input');
    if (input) {
      input.value = text;
      sendChatMessage();
    }
  };

  const chatSendBtn = document.getElementById('btn-chat-send');
  if (chatSendBtn) chatSendBtn.addEventListener('click', sendChatMessage);

  const chatInput = document.getElementById('chat-input');
  if (chatInput) {
    chatInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendChatMessage();
      }
    });
  }

  const chatClearBtn = document.getElementById('btn-clear-chat');
  if (chatClearBtn) {
    chatClearBtn.addEventListener('click', () => {
      state.conversationId = null;
      state.chatHistory = [];
      const stream = document.getElementById('chat-stream');
      stream.innerHTML = `
        <div class="chat-welcome-card" id="chat-welcome">
          <div class="welcome-glyph">✨</div>
          <h2>Welcome to your SVANT Assistant</h2>
          <p>Ask questions about your codebase, documentation, and project health in plain English. Every answer is based strictly on your project's files with clear source notes.</p>
          <div class="chat-feature-pills">
            <span class="chat-pill">🔒 Private Information Protected (stays on your computer)</span>
            <span class="chat-pill">📑 Clear notes showing where answers were found</span>
            <span class="chat-pill">💡 Explanations anyone can understand</span>
            <span class="chat-pill">🛡️ Honest "I don't know" if the files don't have the answer</span>
          </div>
        </div>
      `;
      showToast('Conversation cleared', 'info');
    });
  }

  document.querySelectorAll('.prompt-chip').forEach((chip) => {
    chip.addEventListener('click', () => {
      const q = chip.getAttribute('data-query');
      const input = document.getElementById('chat-input');
      if (input && q) {
        input.value = q;
        sendChatMessage();
      }
    });
  });

  // =====================================================================
  // HEALTH, SECURITY, DUPLICATES & AI INSIGHTS
  // =====================================================================

  let currentRecommendationsData = null;
  let activeTierFilter = 'all';

  function populateSelect(selectElem, currentVal) {
    if (!selectElem) return;
    const existingVal = currentVal || (state.activeProjectId && state.projects.some((p) => p.id === state.activeProjectId) ? state.activeProjectId : selectElem.value);
    selectElem.innerHTML = '';
    state.projects.forEach((p) => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = `${p.name} (${p.root_path})`;
      selectElem.appendChild(opt);
    });
    if (existingVal && state.projects.some((p) => p.id === existingVal)) {
      selectElem.value = existingVal;
    } else if (state.projects.length) {
      selectElem.value = state.projects[0].id;
      if (!state.activeProjectId) state.activeProjectId = state.projects[0].id;
    }
  }

  function syncActiveProjectSelects(newVal) {
    state.activeProjectId = newVal;
    const selectIds = [
      'health-project-select',
      'security-project-select',
      'duplicates-project-select',
      'chat-project-select',
    ];
    selectIds.forEach((id) => {
      const el = document.getElementById(id);
      if (el && el.value !== newVal && Array.from(el.options).some((o) => o.value === newVal)) {
        el.value = newVal;
      }
    });
    const searchEl = document.getElementById('search-project-select');
    if (searchEl && searchEl.value !== newVal && Array.from(searchEl.options).some((o) => o.value === newVal)) {
      searchEl.value = newVal;
    }
  }

  // --- HEALTH VIEW ---
  async function loadHealthView() {
    const projSelect = document.getElementById('health-project-select');
    populateSelect(projSelect);
    const projectId = projSelect ? projSelect.value : null;
    if (!projectId) {
      const emptyState = document.getElementById('health-empty-state');
      if (emptyState) {
        emptyState.style.display = 'block';
        emptyState.innerHTML = `
          <div class="empty-icon">📁</div>
          <h3>No Projects Added Yet</h3>
          <p>Add a project folder first to inspect project health.</p>
        `;
      }
      document.getElementById('health-content').style.display = 'none';
      return;
    }

    const emptyState = document.getElementById('health-empty-state');
    if (emptyState) {
      emptyState.innerHTML = `
        <div class="empty-icon">📊</div>
        <h3>Project Health Not Checked Yet</h3>
        <p>Select a project and click "Check Project Health" to review code quality, security, tests, and documentation.</p>
      `;
    }

    try {
      const health = await API.getProjectHealth(projectId);
      if (emptyState) emptyState.style.display = 'none';
      const content = document.getElementById('health-content');
      content.style.display = 'block';

      // Grade badge & score
      const gradeBadge = document.getElementById('health-grade-badge');
      gradeBadge.textContent = health.grade;
      gradeBadge.className = `grade-badge-large grade-${health.grade}`;

      document.getElementById('health-score-number').textContent = health.overall_score;
      document.getElementById('health-summary-text').textContent = health.summary;
      document.getElementById('health-timestamp').textContent = `Last checked: ${formatDate(health.analyzed_at)}`;

      document.getElementById('health-count-crit').textContent = `${health.critical_count} Fix Now`;
      document.getElementById('health-count-high').textContent = `${health.high_count} Fix Soon`;
      document.getElementById('health-count-med').textContent = `${health.medium_count} Important`;
      document.getElementById('health-count-low').textContent = `${health.low_count} Minor`;

      // Components Grid
      const compGrid = document.getElementById('health-components-grid');
      compGrid.innerHTML = '';

      const friendlyCompNames = {
        security: 'Security & Secrets',
        testing: 'Tests & Quality',
        hygiene: 'Project Cleanliness',
        documentation: 'Documentation & Guides',
        dependencies: 'Libraries Used',
        structure: 'Code Organization',
      };

      if (health.component_scores) {
        Object.entries(health.component_scores).forEach(([catKey, comp]) => {
          const compCard = document.createElement('div');
          compCard.className = 'component-card';
          let colorClass = 'score-green';
          if (comp.score < 60) colorClass = 'score-red';
          else if (comp.score < 80) colorClass = 'score-yellow';
          else if (comp.score < 90) colorClass = 'score-blue';

          const compTitle = friendlyCompNames[catKey.toLowerCase()] || comp.category || catKey;

          compCard.innerHTML = `
            <div class="comp-header">
              <span class="comp-name">${escapeHtml(compTitle)}</span>
              <span class="comp-weight"><strong>${comp.score} / 100</strong></span>
            </div>
            <div class="comp-score-bar">
              <div class="comp-score-fill ${colorClass}" style="width: ${comp.score}%;"></div>
            </div>
            <div class="comp-rationale">${escapeHtml(comp.rationale)}</div>
          `;
          compGrid.appendChild(compCard);
        });
      }

      loadRecommendations(projectId);
    } catch (_) {
      document.getElementById('health-empty-state').style.display = 'block';
      document.getElementById('health-content').style.display = 'none';
    }
  }

  async function loadRecommendations(projectId) {
    try {
      const recs = await API.getProjectRecommendations(projectId);
      currentRecommendationsData = recs;
      renderRecommendationsList();
    } catch (err) {
      console.error('Error fetching recommendations:', err);
    }
  }

  function renderRecommendationsList() {
    const recsContainer = document.getElementById('health-recommendations-list');
    if (!recsContainer || !currentRecommendationsData) return;
    recsContainer.innerHTML = '';

    const tiers = currentRecommendationsData.recommendations_by_tier || {};
    let allItems = [];
    if (activeTierFilter === 'all') {
      allItems = [
        ...(tiers.fix_first || []),
        ...(tiers.should_fix || []),
        ...(tiers.nice_to_improve || []),
        ...(tiers.informational || []),
      ];
    } else {
      allItems = tiers[activeTierFilter] || [];
    }

    if (!allItems.length) {
      recsContainer.innerHTML = `
        <div class="empty-state-card">
          <div class="empty-icon">✅</div>
          <h3>No Open Issues Here</h3>
          <p>Great job! There are no unresolved issues matching this category.</p>
        </div>
      `;
      return;
    }

    allItems.forEach((f) => {
      const card = createFindingCard(f, document.getElementById('health-project-select').value, () => {
        loadHealthView();
      });
      recsContainer.appendChild(card);
    });
  }

  function createFindingCard(finding, projectId, onStatusUpdate) {
    const card = document.createElement('div');
    card.className = `finding-card severity-${finding.severity}`;

    const sevBadgeClass = `badge-${finding.severity === 'critical' ? 'crit' : finding.severity === 'high' ? 'high' : finding.severity === 'medium' ? 'med' : 'low'}`;
    const sevLabel = finding.severity === 'critical' ? 'Fix Now' : (finding.severity === 'high' ? 'Fix Soon' : (finding.severity === 'medium' ? 'Important' : 'Minor'));

    const evidenceHtml = finding.evidence
      ? `<div class="finding-evidence"><code>${escapeHtml(finding.evidence)}</code></div>`
      : '';

    card.innerHTML = `
      <div class="finding-top-row">
        <div class="finding-title-group">
          <span class="health-meta-badge ${sevBadgeClass}">${sevLabel}</span>
          <span class="finding-title">${escapeHtml(finding.title)}</span>
          <span class="finding-path">${escapeHtml(finding.relative_path || 'Project Root')}</span>
        </div>
        <div class="finding-actions">
          <select class="form-control select-status-toggle" style="font-size: 11.5px; padding: 4px 8px;">
            <option value="open" ${finding.status === 'open' ? 'selected' : ''}>Open</option>
            <option value="acknowledged" ${finding.status === 'acknowledged' ? 'selected' : ''}>Acknowledged</option>
            <option value="resolved" ${finding.status === 'resolved' ? 'selected' : ''}>Resolved</option>
            <option value="ignored" ${finding.status === 'ignored' ? 'selected' : ''}>Ignored</option>
          </select>
          <button class="btn btn-secondary btn-sm btn-explain-finding" title="Ask SVANT to explain this problem in plain English">
            <span>💡 Explain Problem</span>
          </button>
        </div>
      </div>
      <div class="finding-desc">${escapeHtml(finding.description)}</div>
      ${evidenceHtml}
      <div class="finding-rec">
        <strong>What to do:</strong> ${escapeHtml(finding.recommendation)}
      </div>
    `;

    const statusSelect = card.querySelector('.select-status-toggle');
    statusSelect.addEventListener('change', async () => {
      try {
        await API.updateFindingStatus(projectId, finding.id, statusSelect.value);
        showToast(`Problem marked as ${statusSelect.value}`, 'success');
        if (onStatusUpdate) onStatusUpdate();
      } catch (err) {
        showToast(`Failed to update status: ${err.message}`, 'error');
      }
    });

    const explainBtn = card.querySelector('.btn-explain-finding');
    explainBtn.addEventListener('click', async () => {
      showAIModal(`Explaining Problem: ${finding.title}`, 'Analyzing what happened and drafting easy-to-follow steps to fix it...');
      try {
        const res = await API.aiExplainFinding(projectId, finding.id);
        renderAIModalContent(res.content);
      } catch (err) {
        renderAIModalContent(`Could not explain problem: ${err.message}`);
      }
    });

    return card;
  }

  // --- SECURITY VIEW ---
  async function loadSecurityView() {
    const projSelect = document.getElementById('security-project-select');
    populateSelect(projSelect);
    const projectId = projSelect ? projSelect.value : null;
    if (!projectId) {
      document.getElementById('sec-count-crit').textContent = '0 Fix Now';
      document.getElementById('sec-count-high').textContent = '0 Fix Soon';
      document.getElementById('sec-count-total').textContent = '0 Total';
      const listContainer = document.getElementById('security-findings-list');
      if (listContainer) {
        listContainer.innerHTML = `
          <div class="empty-state-card">
            <div class="empty-icon">📁</div>
            <h3>No Projects Added Yet</h3>
            <p>Add a project folder first to check for security problems.</p>
          </div>
        `;
      }
      return;
    }

    const sevFilter = document.getElementById('security-severity-filter').value;
    const statusFilter = document.getElementById('security-status-filter').value;

    try {
      const findings = await API.getProjectFindings(projectId, {
        category: 'security',
        severity: sevFilter || undefined,
        status: statusFilter || undefined,
      });

      const critCount = findings.filter((f) => f.severity === 'critical' && f.status === 'open').length;
      const highCount = findings.filter((f) => f.severity === 'high' && f.status === 'open').length;
      document.getElementById('sec-count-crit').textContent = `${critCount} Fix Now`;
      document.getElementById('sec-count-high').textContent = `${highCount} Fix Soon`;
      document.getElementById('sec-count-total').textContent = `${findings.length} Total`;

      const listContainer = document.getElementById('security-findings-list');
      listContainer.innerHTML = '';

      if (!findings.length) {
        listContainer.innerHTML = `
          <div class="empty-state-card">
            <div class="empty-icon">🛡️</div>
            <h3>No Security Problems Found</h3>
            <p>Your project is clean. Zero exposed passwords or risky settings match this filter.</p>
          </div>
        `;
        return;
      }

      findings.forEach((f) => {
        const card = createFindingCard(f, projectId, () => {
          loadSecurityView();
        });
        listContainer.appendChild(card);
      });
    } catch (err) {
      console.error('Error loading security findings:', err);
    }
  }

  // --- DUPLICATES VIEW ---
  async function loadDuplicatesView() {
    const projSelect = document.getElementById('duplicates-project-select');
    populateSelect(projSelect);
    const projectId = projSelect ? projSelect.value : null;

    const totalClustersEl = document.getElementById('dup-total-clusters');
    const exactClustersEl = document.getElementById('dup-exact-clusters');
    const similarClustersEl = document.getElementById('dup-similar-clusters');
    const wastedStorageEl = document.getElementById('dup-wasted-storage');
    const totalCopiesEl = document.getElementById('dup-total-copies');
    const listContainer = document.getElementById('duplicates-clusters-list');

    const resetCounters = () => {
      if (totalClustersEl) totalClustersEl.textContent = '0';
      if (exactClustersEl) exactClustersEl.textContent = '0';
      if (similarClustersEl) similarClustersEl.textContent = '0';
      if (wastedStorageEl) wastedStorageEl.textContent = '0 B';
      if (totalCopiesEl) totalCopiesEl.textContent = '0';
    };

    // Case 3: No Project Selected
    if (!projectId) {
      resetCounters();
      if (listContainer) {
        listContainer.innerHTML = `
          <div class="empty-state-card">
            <div class="empty-icon">📁</div>
            <h3>No Project Selected</h3>
            <p>Please select a project from the dropdown above to inspect duplicate files.</p>
          </div>
        `;
      }
      return;
    }

    // Check project scan status
    const currentProj = state.projects.find((p) => p.id === projectId);
    // Case 4: Analysis Not Run Yet / No Files Scanned
    if (currentProj && (currentProj.file_count === 0 || !currentProj.last_scanned_at)) {
      resetCounters();
      if (listContainer) {
        listContainer.innerHTML = `
          <div class="empty-state-card">
            <div class="empty-icon">⚡</div>
            <h3>Project Files Not Checked Yet</h3>
            <p>This project hasn't been scanned for files yet. Check project files to detect duplicates and reclaim storage.</p>
            <button class="btn btn-primary mt-3" onclick="window.triggerScan('${projectId}')">
              <span>⚡ Check Project Files Now</span>
            </button>
          </div>
        `;
      }
      return;
    }

    // Case 5: Loading State
    if (listContainer) {
      listContainer.innerHTML = `
        <div class="empty-state-card">
          <div class="empty-icon">⏳</div>
          <h3>Checking for Duplicate Files...</h3>
          <p>Analyzing file content and calculating text similarity for ${escapeHtml(currentProj ? currentProj.name : 'your project')}...</p>
        </div>
      `;
    }

    try {
      const clusters = await API.getProjectDuplicates(projectId);
      state.duplicateClusters = clusters || [];

      // Case 2: No Duplicates Found
      if (!clusters || !clusters.length) {
        resetCounters();
        if (listContainer) {
          listContainer.innerHTML = `
            <div class="empty-state-card">
              <div class="empty-icon">✨</div>
              <h3>No Duplicate Files Detected</h3>
              <p>Every file in this project has unique content. Zero exact or near-duplicate files found.</p>
            </div>
          `;
        }
        return;
      }

      // Case 1: Duplicates Found
      const totalClusters = clusters.length;
      let totalWasted = 0;
      let totalCopies = 0;
      let exactCount = 0;
      let similarCount = 0;

      clusters.forEach((c) => {
        totalWasted += c.wasted_bytes || 0;
        const count = c.count || c.file_count || (c.files ? c.files.length : 0);
        totalCopies += Math.max(0, count - 1);
        if (c.duplicate_type === 'similar') {
          similarCount++;
        } else {
          exactCount++;
        }
      });

      if (totalClustersEl) totalClustersEl.textContent = totalClusters;
      if (exactClustersEl) exactClustersEl.textContent = exactCount;
      if (similarClustersEl) similarClustersEl.textContent = similarCount;
      if (wastedStorageEl) wastedStorageEl.textContent = formatBytes(totalWasted);
      if (totalCopiesEl) totalCopiesEl.textContent = totalCopies;

      listContainer.innerHTML = '';

      clusters.forEach((cl, clusterIdx) => {
        const card = document.createElement('div');
        card.className = 'dup-cluster-card';

        const isExact = (cl.duplicate_type !== 'similar');
        const badgeHtml = isExact
          ? `<span class="badge-dup exact">100% Exact Match</span>`
          : `<span class="badge-dup similar">${cl.similarity_pct || 90}% Similar</span>`;

        const titleText = isExact
          ? `${cl.count} identical copies`
          : `${cl.count} highly similar files`;

        const subtitleText = cl.difference_summary || cl.reason || (isExact ? 'Identical SHA-256 content' : 'Similar code structure');

        const fileItems = (cl.files || []).map((f) => {
          const roleClass = f.role === 'original' ? 'original' : (f.role === 'variant' ? 'variant' : 'copy');
          const roleLabel = f.role === 'original' ? 'Original' : (f.role === 'variant' ? 'Variant' : 'Copy');
          return `
            <div class="dup-file-item">
              <div class="dup-file-item-left">
                <span class="role-pill ${roleClass}">${roleLabel}</span>
                <span class="dup-file-path" title="${escapeHtml(f.relative_path || f.filename)}">${escapeHtml(f.relative_path || f.filename)}</span>
              </div>
              <div class="dup-file-item-right">
                <span>${formatBytes(f.size_bytes)}</span>
                <span>${formatDate(f.modified_time)}</span>
                <button class="btn btn-ghost btn-xs" onclick="window.viewFileDetail('${f.id}')">View Details</button>
              </div>
            </div>
          `;
        }).join('');

        const canCompare = cl.files && cl.files.length >= 2;
        const compareBtnHtml = canCompare
          ? `<button class="btn btn-secondary btn-sm" onclick="window.openCompareModal(${clusterIdx})"><span>🔍 Compare Files</span></button>`
          : '';

        card.innerHTML = `
          <div class="dup-cluster-header">
            <div class="dup-cluster-header-left">
              ${badgeHtml}
              <div>
                <strong>${escapeHtml(titleText)}</strong>
                <div class="dup-stats" style="font-size:12px; margin-top:2px;">${escapeHtml(subtitleText)}</div>
              </div>
            </div>
            <div class="dup-cluster-header-right">
              <div class="dup-stats">
                Space you could save: <strong>${formatBytes(cl.wasted_bytes)}</strong>
              </div>
              ${compareBtnHtml}
            </div>
          </div>
          <div class="dup-file-list">${fileItems}</div>
        `;
        listContainer.appendChild(card);
      });
    } catch (err) {
      console.error('Error loading duplicates:', err);
      // Case 6: Error State
      resetCounters();
      if (listContainer) {
        listContainer.innerHTML = `
          <div class="empty-state-card">
            <div class="empty-icon">⚠️</div>
            <h3>Could Not Check for Duplicates</h3>
            <p>${escapeHtml(err.message)}</p>
            <button class="btn btn-secondary mt-3" onclick="loadDuplicatesView()">
              <span>🔄 Try Again</span>
            </button>
          </div>
        `;
      }
    }
  }

  // --- FILE COMPARISON MODAL ---
  window.openCompareModal = async function(clusterIndex) {
    if (!modalCompareFiles) return;
    const cluster = (state.duplicateClusters || [])[clusterIndex];
    if (!cluster || !cluster.files || cluster.files.length < 2) return;

    const fileA = cluster.files[0];
    const fileB = cluster.files[1];

    const isExact = (cluster.duplicate_type !== 'similar');
    const badgeEl = document.getElementById('modal-compare-badge');
    if (badgeEl) {
      badgeEl.className = isExact ? 'badge-dup exact' : 'badge-dup similar';
      badgeEl.textContent = isExact ? '100% Exact Match' : `${cluster.similarity_pct || 90}% Similar`;
    }

    const titleEl = document.getElementById('modal-compare-title');
    if (titleEl) {
      titleEl.textContent = `Compare: ${fileA.filename} vs ${fileB.filename}`;
    }

    const subEl = document.getElementById('modal-compare-subtitle');
    if (subEl) {
      subEl.textContent = cluster.difference_summary || cluster.reason || 'Side-by-side content and metadata comparison';
    }

    const bannerEl = document.getElementById('modal-compare-banner');
    if (bannerEl) {
      bannerEl.textContent = isExact
        ? 'These files contain 100% identical content. You can safely keep the original and remove duplicate copies to reclaim storage.'
        : `These files share ${cluster.similarity_pct || 90}% content with minor modifications. Compare both versions below to review differences.`;
    }

    // Set file A metadata
    const tagA = document.getElementById('compare-tag-a');
    if (tagA) {
      tagA.textContent = fileA.role === 'original' ? 'Original / Primary' : 'Variant';
      tagA.className = `role-pill ${fileA.role === 'original' ? 'original' : 'variant'}`;
    }
    const nameA = document.getElementById('compare-file-a-name');
    if (nameA) nameA.textContent = fileA.relative_path || fileA.filename;
    const metaA = document.getElementById('compare-file-a-meta');
    if (metaA) metaA.textContent = `${formatBytes(fileA.size_bytes)} · Modified ${formatDate(fileA.modified_time)}`;

    // Set file B metadata
    const tagB = document.getElementById('compare-tag-b');
    if (tagB) {
      tagB.textContent = fileB.role === 'variant' ? `Variant (${cluster.similarity_pct || 90}% match)` : 'Duplicate Copy';
      tagB.className = `role-pill ${fileB.role === 'variant' ? 'variant' : 'copy'}`;
    }
    const nameB = document.getElementById('compare-file-b-name');
    if (nameB) nameB.textContent = fileB.relative_path || fileB.filename;
    const metaB = document.getElementById('compare-file-b-meta');
    if (metaB) metaB.textContent = `${formatBytes(fileB.size_bytes)} · Modified ${formatDate(fileB.modified_time)}`;

    const contentA = document.getElementById('compare-file-a-content');
    const contentB = document.getElementById('compare-file-b-content');
    if (contentA) contentA.textContent = 'Loading text preview...';
    if (contentB) contentB.textContent = 'Loading text preview...';

    modalCompareFiles.classList.add('active');

    try {
      const [detailA, detailB] = await Promise.all([
        API.getFileDetail(fileA.id),
        API.getFileDetail(fileB.id),
      ]);
      if (contentA) contentA.textContent = detailA.content_preview || '(No text extracted or file is binary)';
      if (contentB) contentB.textContent = detailB.content_preview || '(No text extracted or file is binary)';
    } catch (err) {
      if (contentA) contentA.textContent = `Error loading content: ${err.message}`;
      if (contentB) contentB.textContent = `Error loading content: ${err.message}`;
    }
  };

  // --- SETTINGS VIEW ---
  async function loadSettingsView() {
    try {
      const cfg = await API.getSettings();
      state.settings = cfg;

      const dirEl = document.getElementById('settings-storage-dir');
      if (dirEl) dirEl.textContent = cfg.data_dir;

      const dbFileEl = document.getElementById('settings-db-file');
      if (dbFileEl) dbFileEl.textContent = cfg.db_path.split(/[\/\\]/).pop();

      const tagsEl = document.getElementById('settings-excluded-tags');
      if (tagsEl && cfg.excluded_dirs) {
        tagsEl.innerHTML = cfg.excluded_dirs
          .map((d) => `<span class="tag-item">${escapeHtml(d)}</span>`)
          .join('');
      }

      const modeBadge = document.getElementById('settings-ai-mode-badge');
      const modeDesc = document.getElementById('settings-ai-mode-desc');
      if (modeBadge) {
        if (cfg.ai_provider === 'gemini' && cfg.gemini_configured) {
          modeBadge.textContent = 'Gemini AI';
          modeBadge.className = 'badge-provider live';
          if (modeDesc) modeDesc.textContent = `Answers generated using Google Gemini (${cfg.gemini_model}) with local privacy protection.`;
        } else if (cfg.ai_provider === 'mock') {
          modeBadge.textContent = 'Test Mode';
          modeBadge.className = 'badge-provider test';
          if (modeDesc) modeDesc.textContent = 'Using test provider for offline development.';
        } else {
          modeBadge.textContent = 'Works on Your Computer';
          modeBadge.className = 'badge-provider local';
          if (modeDesc) modeDesc.textContent = 'Project information stays 100% on your computer without sending data to the cloud.';
        }
      }

      const appVerEl = document.getElementById('settings-app-ver');
      if (appVerEl) appVerEl.textContent = cfg.version;

      const embedModelEl = document.getElementById('settings-embed-model');
      if (embedModelEl) embedModelEl.textContent = cfg.embedding_model;

      // Sync theme buttons in settings view
      const currentTheme = localStorage.getItem('svant_theme') || 'light';
      document.querySelectorAll('.theme-option-btn').forEach((btn) => {
        btn.classList.toggle('active', btn.getAttribute('data-theme-choice') === currentTheme);
      });

      // Sync default search selector in settings view
      const searchPrefSelect = document.getElementById('setting-default-search');
      if (searchPrefSelect) {
        searchPrefSelect.value = localStorage.getItem('svant_default_search') || 'hybrid';
      }
    } catch (err) {
      console.error('Error loading settings:', err);
    }
  }

  // --- AI MODAL HELPER ---
  const modalAIInsight = document.getElementById('modal-ai-insight');
  const modalAITitle = document.getElementById('modal-ai-title');
  const modalAIBody = document.getElementById('modal-ai-body');
  let currentAIMarkdown = '';

  function showAIModal(title, initialText) {
    if (!modalAIInsight) return;
    modalAITitle.textContent = title;
    currentAIMarkdown = initialText;
    modalAIBody.innerHTML = `<p>${escapeHtml(initialText)}</p>`;
    modalAIInsight.classList.add('active');
  }

  function renderAIModalContent(markdown) {
    currentAIMarkdown = markdown;
    modalAIBody.innerHTML = formatMarkdown(markdown);
  }

  const closeAIModalBtn = document.getElementById('btn-close-ai-modal');
  if (closeAIModalBtn) {
    closeAIModalBtn.addEventListener('click', () => {
      modalAIInsight.classList.remove('active');
    });
  }

  const copyAIInsightBtn = document.getElementById('btn-copy-ai-insight');
  if (copyAIInsightBtn) {
    copyAIInsightBtn.addEventListener('click', () => {
      navigator.clipboard.writeText(currentAIMarkdown);
      showToast('Copied to clipboard!', 'success');
    });
  }

  const discussChatBtn = document.getElementById('btn-discuss-in-chat');
  if (discussChatBtn) {
    discussChatBtn.addEventListener('click', () => {
      modalAIInsight.classList.remove('active');
      switchPage('aichat');
      const chatInput = document.getElementById('chat-input');
      if (chatInput) {
        chatInput.value = `Can you explain the key findings and next steps from the recent report?`;
        chatInput.focus();
      }
    });
  }

  // --- EVENT LISTENERS FOR HEALTH / SECURITY / DUPLICATES ---
  const healthSelect = document.getElementById('health-project-select');
  if (healthSelect) {
    healthSelect.addEventListener('change', () => {
      syncActiveProjectSelects(healthSelect.value);
      loadHealthView();
    });
  }

  const securitySelect = document.getElementById('security-project-select');
  if (securitySelect) {
    securitySelect.addEventListener('change', () => {
      syncActiveProjectSelects(securitySelect.value);
      loadSecurityView();
    });
  }
  const secSevFilter = document.getElementById('security-severity-filter');
  if (secSevFilter) secSevFilter.addEventListener('change', loadSecurityView);
  const secStatusFilter = document.getElementById('security-status-filter');
  if (secStatusFilter) secStatusFilter.addEventListener('change', loadSecurityView);

  const dupSelect = document.getElementById('duplicates-project-select');
  if (dupSelect) {
    dupSelect.addEventListener('change', () => {
      syncActiveProjectSelects(dupSelect.value);
      loadDuplicatesView();
    });
  }

  const chatSelect = document.getElementById('chat-project-select');
  if (chatSelect) {
    chatSelect.addEventListener('change', () => {
      syncActiveProjectSelects(chatSelect.value);
    });
  }

  const fileFilterSelect = document.getElementById('file-filter-project');
  if (fileFilterSelect) {
    fileFilterSelect.addEventListener('change', () => {
      if (fileFilterSelect.value) {
        syncActiveProjectSelects(fileFilterSelect.value);
      }
      loadFilesView();
    });
  }

  const recFilterGroup = document.getElementById('recommendation-tier-filter');
  if (recFilterGroup) {
    recFilterGroup.addEventListener('click', (e) => {
      if (e.target.classList.contains('pill')) {
        recFilterGroup.querySelectorAll('.pill').forEach((p) => p.classList.remove('active'));
        e.target.classList.add('active');
        activeTierFilter = e.target.dataset.tier;
        renderRecommendationsList();
      }
    });
  }

  // Run Health Analysis button
  const runAnalysisBtn = document.getElementById('btn-run-analysis');
  if (runAnalysisBtn) {
    runAnalysisBtn.addEventListener('click', async () => {
      const projSelect = document.getElementById('health-project-select');
      const projectId = projSelect ? projSelect.value : null;
      if (!projectId) return showToast('Please select a project first.', 'error');

      runAnalysisBtn.disabled = true;
      runAnalysisBtn.innerHTML = '<span>⏳ Checking Health...</span>';
      showToast('Checking project health, tests, and security...', 'info');

      try {
        const res = await API.analyzeProject(projectId);
        showToast(`Health check complete! Grade ${res.grade} (${res.overall_score}/100)`, 'success');
        await loadHealthView();
      } catch (err) {
        showToast(`Health check failed: ${err.message}`, 'error');
      } finally {
        runAnalysisBtn.disabled = false;
        runAnalysisBtn.innerHTML = '<span>⚡ Check Project Health</span>';
      }
    });
  }

  // Run Security Scan button
  const secScanBtn = document.getElementById('btn-security-scan');
  if (secScanBtn) {
    secScanBtn.addEventListener('click', async () => {
      const projSelect = document.getElementById('security-project-select');
      const projectId = projSelect ? projSelect.value : null;
      if (!projectId) return showToast('Please select a project first.', 'error');

      secScanBtn.disabled = true;
      secScanBtn.innerHTML = '<span>⏳ Checking for Problems...</span>';
      try {
        await API.analyzeProject(projectId);
        showToast('Security check completed successfully!', 'success');
        await loadSecurityView();
      } catch (err) {
        showToast(`Security check failed: ${err.message}`, 'error');
      } finally {
        secScanBtn.disabled = false;
        secScanBtn.innerHTML = '<span>🛡️ Check for Security Problems</span>';
      }
    });
  }

  // Refresh Duplicates button
  const refreshDupBtn = document.getElementById('btn-refresh-duplicates');
  if (refreshDupBtn) {
    refreshDupBtn.addEventListener('click', async () => {
      refreshDupBtn.disabled = true;
      refreshDupBtn.innerHTML = '<span>⏳ Checking...</span>';
      try {
        await loadDuplicatesView();
        showToast('Duplicate files check completed', 'info');
      } catch (err) {
        showToast(`Check failed: ${err.message}`, 'error');
      } finally {
        refreshDupBtn.disabled = false;
        refreshDupBtn.innerHTML = '<span>🔄 Look for Duplicates</span>';
      }
    });
  }

  // Compare Files Modal Close Listeners
  const btnCloseCompareModal = document.getElementById('btn-close-compare-modal');
  if (btnCloseCompareModal) {
    btnCloseCompareModal.addEventListener('click', () => {
      if (modalCompareFiles) modalCompareFiles.classList.remove('active');
    });
  }
  const btnCloseCompareBottom = document.getElementById('btn-close-compare-bottom');
  if (btnCloseCompareBottom) {
    btnCloseCompareBottom.addEventListener('click', () => {
      if (modalCompareFiles) modalCompareFiles.classList.remove('active');
    });
  }
  if (modalCompareFiles) {
    modalCompareFiles.addEventListener('click', (e) => {
      if (e.target === modalCompareFiles) modalCompareFiles.classList.remove('active');
    });
  }

  // AI Summarize button
  const aiSummarizeBtn = document.getElementById('btn-ai-summarize');
  if (aiSummarizeBtn) {
    aiSummarizeBtn.addEventListener('click', async () => {
      const projSelect = document.getElementById('health-project-select');
      const projectId = projSelect ? projSelect.value : null;
      if (!projectId) return showToast('Please select a project first.', 'error');

      showAIModal('Project Summary', 'Writing a clear, plain-English summary of your project...');
      try {
        const res = await API.aiSummarizeProject(projectId);
        renderAIModalContent(res.content);
      } catch (err) {
        renderAIModalContent(`Could not generate summary: ${err.message}`);
      }
    });
  }

  // AI Plan button
  const aiPlanBtn = document.getElementById('btn-ai-plan');
  if (aiPlanBtn) {
    aiPlanBtn.addEventListener('click', async () => {
      const projSelect = document.getElementById('health-project-select');
      const projectId = projSelect ? projSelect.value : null;
      if (!projectId) return showToast('Please select a project first.', 'error');

      showAIModal('Step-by-Step Fix Plan', 'Organizing recommended steps to fix project problems in order of priority...');
      try {
        const res = await API.aiImprovementPlan(projectId);
        renderAIModalContent(res.content);
      } catch (err) {
        renderAIModalContent(`Could not generate plan: ${err.message}`);
      }
    });
  }

  // AI Onboarding button
  const aiOnboardBtn = document.getElementById('btn-ai-onboarding');
  if (aiOnboardBtn) {
    aiOnboardBtn.addEventListener('click', async () => {
      const projSelect = document.getElementById('health-project-select');
      const projectId = projSelect ? projSelect.value : null;
      if (!projectId) return showToast('Please select a project first.', 'error');

      showAIModal('Get Started Guide', 'Creating a beginner-friendly guide to get started with this project...');
      try {
        const res = await API.aiOnboardingProject(projectId);
        renderAIModalContent(res.content);
      } catch (err) {
        renderAIModalContent(`Could not generate guide: ${err.message}`);
      }
    });
  }

  // --- THEME & SETTINGS MANAGEMENT ---
  function applyTheme(choice) {
    let resolvedTheme = choice;
    if (choice === 'system') {
      resolvedTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    document.documentElement.setAttribute('data-theme', resolvedTheme);

    document.querySelectorAll('.theme-option-btn').forEach((btn) => {
      btn.classList.toggle('active', btn.getAttribute('data-theme-choice') === choice);
    });
  }

  function initThemeAndPreferences() {
    const savedTheme = localStorage.getItem('svant_theme') || 'light';
    applyTheme(savedTheme);

    // Watch OS system preference changes
    try {
      const darkMediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
      darkMediaQuery.addEventListener('change', () => {
        if ((localStorage.getItem('svant_theme') || 'light') === 'system') {
          applyTheme('system');
        }
      });
    } catch (_) {}

    // Theme switcher buttons
    document.querySelectorAll('.theme-option-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const choice = btn.getAttribute('data-theme-choice');
        if (!choice) return;
        localStorage.setItem('svant_theme', choice);
        applyTheme(choice);
        const labels = { light: 'Light Theme', dark: 'Dark Theme', system: 'System Theme' };
        showToast(`Theme switched to ${labels[choice] || choice}`, 'info');
      });
    });

    // Default search method preference
    const searchPrefSelect = document.getElementById('setting-default-search');
    if (searchPrefSelect) {
      const savedSearch = localStorage.getItem('svant_default_search') || 'hybrid';
      searchPrefSelect.value = savedSearch;
      state.searchMode = savedSearch;

      searchPrefSelect.addEventListener('change', (e) => {
        const val = e.target.value;
        localStorage.setItem('svant_default_search', val);
        state.searchMode = val;

        // Sync Search page mode tabs
        document.querySelectorAll('.mode-tab').forEach((t) => {
          t.classList.toggle('active', t.dataset.mode === val);
        });

        // Sync AI Chat mode dropdown
        const chatModeSelect = document.getElementById('chat-mode-select');
        if (chatModeSelect) chatModeSelect.value = val;

        const modeNames = { hybrid: 'Smart Search', semantic: 'Search by Meaning', keyword: 'Search by Words' };
        showToast(`Default search preference saved: ${modeNames[val] || val}`, 'success');
      });
    }

    // Set AI Assistant search mode selector to default
    const chatModeSelect = document.getElementById('chat-mode-select');
    if (chatModeSelect) {
      chatModeSelect.value = localStorage.getItem('svant_default_search') || 'hybrid';
    }
  }

  // Initial load
  initThemeAndPreferences();
  checkHealth();
  loadDashboardData();
  updateAIStatusBadge();
  setInterval(checkHealth, 15000);
});
