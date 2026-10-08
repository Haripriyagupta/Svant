/**
 * SVANT Frontend API Client
 * Interfaces directly with the Python backend REST API.
 */

const API = {
  baseUrl: window.location.origin,

  async request(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    try {
      const response = await fetch(url, {
        headers: {
          'Content-Type': 'application/json',
          ...options.headers,
        },
        ...options,
      });

      if (!response.ok) {
        let errMessage = `HTTP error ${response.status}`;
        try {
          const errorJson = await response.json();
          if (errorJson.detail) {
            if (typeof errorJson.detail === 'string') {
              errMessage = errorJson.detail;
            } else if (Array.isArray(errorJson.detail)) {
              errMessage = errorJson.detail
                .map((d) => {
                  if (typeof d === 'string') return d;
                  if (d && typeof d === 'object') {
                    const loc = Array.isArray(d.loc) ? d.loc.filter((l) => l !== 'body').join('.') : '';
                    return loc ? `${d.msg || 'Invalid input'} (${loc})` : (d.msg || JSON.stringify(d));
                  }
                  return String(d);
                })
                .join('; ');
            } else if (typeof errorJson.detail === 'object') {
              errMessage = errorJson.detail.message || errorJson.detail.msg || JSON.stringify(errorJson.detail);
            }
          } else if (errorJson.error) {
            errMessage = typeof errorJson.error === 'string' ? errorJson.error : JSON.stringify(errorJson.error);
          } else if (errorJson.message) {
            errMessage = typeof errorJson.message === 'string' ? errorJson.message : JSON.stringify(errorJson.message);
          }
        } catch (_) {}
        throw new Error(errMessage);
      }

      return await response.json();
    } catch (err) {
      console.error(`API Error on ${endpoint}:`, err);
      throw err;
    }
  },

  getHealth() {
    return this.request('/health');
  },

  getSettings() {
    return this.request('/api/settings');
  },

  getStats() {
    return this.request('/api/stats');
  },

  getProjects() {
    return this.request('/api/projects');
  },

  createProject(path, name) {
    return this.request('/api/projects', {
      method: 'POST',
      body: JSON.stringify({ path, name: name || undefined }),
    });
  },

  scanProject(projectId) {
    return this.request(`/api/projects/${projectId}/scan`, {
      method: 'POST',
    });
  },

  indexProject(projectId, forceRebuild = false) {
    return this.request(`/api/projects/${projectId}/index`, {
      method: 'POST',
      body: JSON.stringify({ force_rebuild: forceRebuild }),
    });
  },

  getIndexStatus(projectId) {
    return this.request(`/api/projects/${projectId}/index/status`);
  },

  rebuildIndex(projectId) {
    return this.request(`/api/projects/${projectId}/index/rebuild`, {
      method: 'POST',
    });
  },

  deleteProject(projectId) {
    return this.request(`/api/projects/${projectId}`, {
      method: 'DELETE',
    });
  },

  getFiles({ projectId, category, extension, search, limit = 100, offset = 0 } = {}) {
    const params = new URLSearchParams();
    if (projectId) params.append('project_id', projectId);
    if (category) params.append('category', category);
    if (extension) params.append('extension', extension);
    if (search) params.append('search', search);
    params.append('limit', limit.toString());
    params.append('offset', offset.toString());
    return this.request(`/api/files?${params.toString()}`);
  },

  getFileDetail(fileId) {
    return this.request(`/api/files/${fileId}`);
  },

  search({ query, projectId, mode = 'keyword' } = {}) {
    const params = new URLSearchParams();
    params.append('q', query);
    if (projectId) params.append('project_id', projectId);
    params.append('mode', mode);
    return this.request(`/api/search?${params.toString()}`);
  },

  getAIStatus() {
    return this.request('/api/chat/status');
  },

  chat({ message, projectId, searchMode = 'hybrid', topK = 5, provider, conversationId, history } = {}) {
    return this.request('/api/chat', {
      method: 'POST',
      body: JSON.stringify({
        message,
        project_id: projectId || undefined,
        search_mode: searchMode,
        top_k: topK,
        provider: provider || undefined,
        conversation_id: conversationId || undefined,
        history: history || undefined,
      }),
    });
  },

  // Project Intelligence, Health, Security & AI Assistant
  analyzeProject(projectId) {
    return this.request(`/api/projects/${projectId}/analyze`, {
      method: 'POST',
    });
  },

  getProjectHealth(projectId) {
    return this.request(`/api/projects/${projectId}/health`);
  },

  getProjectSummary(projectId) {
    return this.request(`/api/projects/${projectId}/summary`);
  },

  getProjectFindings(projectId, { category, severity, status, priorityTier } = {}) {
    const params = new URLSearchParams();
    if (category) params.append('category', category);
    if (severity) params.append('severity', severity);
    if (status) params.append('status', status);
    if (priorityTier) params.append('priority_tier', priorityTier);
    const qs = params.toString();
    return this.request(`/api/projects/${projectId}/findings${qs ? '?' + qs : ''}`);
  },

  updateFindingStatus(projectId, findingId, status) {
    return this.request(`/api/projects/${projectId}/findings/${findingId}`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    });
  },

  getProjectRecommendations(projectId) {
    return this.request(`/api/projects/${projectId}/recommendations`);
  },

  getProjectStatistics(projectId) {
    return this.request(`/api/projects/${projectId}/statistics`);
  },

  getProjectDuplicates(projectId) {
    return this.request(`/api/projects/${projectId}/duplicates`);
  },

  aiSummarizeProject(projectId, provider) {
    const qs = provider ? `?provider=${encodeURIComponent(provider)}` : '';
    return this.request(`/api/projects/${projectId}/ai/summarize${qs}`, {
      method: 'POST',
    });
  },

  aiImprovementPlan(projectId, provider) {
    const qs = provider ? `?provider=${encodeURIComponent(provider)}` : '';
    return this.request(`/api/projects/${projectId}/ai/plan${qs}`, {
      method: 'POST',
    });
  },

  aiOnboardingProject(projectId, provider) {
    const qs = provider ? `?provider=${encodeURIComponent(provider)}` : '';
    return this.request(`/api/projects/${projectId}/ai/onboarding${qs}`, {
      method: 'POST',
    });
  },

  aiExplainFinding(projectId, findingId, provider) {
    const qs = provider ? `?provider=${encodeURIComponent(provider)}` : '';
    return this.request(`/api/projects/${projectId}/ai/explain-finding/${findingId}${qs}`, {
      method: 'POST',
    });
  },
};

