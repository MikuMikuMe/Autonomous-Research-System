// API client for the Autonomous Research System backend

const API_BASE = '';

export interface ResearchStartParams {
  mode: 'goal' | 'report';
  goal: string;
  claims_source?: string;
  max_iterations?: number;
  threshold?: number;
}

export interface Provider {
  name: string;
  available: boolean;
}

export interface KnowledgeEntry {
  claim: string;
  verdict: string;
  confidence: number;
  supporting_papers: string[];
}

export interface Pitfall {
  description: string;
  frequency: number;
  severity: string;
}

export interface JourneySummary {
  [key: string]: unknown;
}

export const api = {
  async startResearch(params: ResearchStartParams) {
    const body: Record<string, string> = {
      mode: params.mode,
      goal: params.goal,
    };
    if (params.claims_source) body.claims_source = params.claims_source;
    if (params.max_iterations !== undefined) body.max_iterations = String(params.max_iterations);
    if (params.threshold !== undefined) body.threshold = String(params.threshold);

    const resp = await fetch(`${API_BASE}/api/research/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams(body),
    });
    return resp.json();
  },

  async getResearchReport() {
    const resp = await fetch(`${API_BASE}/api/outputs/research`);
    if (!resp.ok) return null;
    return resp.json();
  },

  async getCrossValidation() {
    const resp = await fetch(`${API_BASE}/api/outputs/cross_validation`);
    if (!resp.ok) return null;
    return resp.json();
  },

  async getFlaws() {
    const resp = await fetch(`${API_BASE}/api/outputs/flaws`);
    if (!resp.ok) return null;
    return resp.json();
  },

  async getVerification() {
    const resp = await fetch(`${API_BASE}/api/outputs/verification`);
    if (!resp.ok) return null;
    return resp.json();
  },

  async getProviders(): Promise<Provider[]> {
    try {
      const resp = await fetch(`${API_BASE}/api/providers`);
      const data = await resp.json();
      return data.providers || [];
    } catch {
      return [];
    }
  },

  async getMemoryJourney(): Promise<JourneySummary | null> {
    try {
      const resp = await fetch(`${API_BASE}/api/memory/journey`);
      if (!resp.ok) return null;
      return resp.json();
    } catch {
      return null;
    }
  },

  async getKnowledge(): Promise<KnowledgeEntry[]> {
    try {
      const resp = await fetch(`${API_BASE}/api/memory/knowledge`);
      const data = await resp.json();
      return data.entries || [];
    } catch {
      return [];
    }
  },

  async getPitfalls(): Promise<Pitfall[]> {
    try {
      const resp = await fetch(`${API_BASE}/api/memory/pitfalls`);
      const data = await resp.json();
      return data.pitfalls || [];
    } catch {
      return [];
    }
  },

  async submitIdea(text: string, files: File[], maxIterations: number = 3) {
    const form = new FormData();
    form.append('text', text);
    form.append('max_iterations', String(maxIterations));
    files.forEach(f => form.append('files', f));
    const resp = await fetch(`${API_BASE}/api/idea/verify`, { method: 'POST', body: form });
    return resp.json();
  },

  async getIdeaResults(sessionId: string) {
    const resp = await fetch(`${API_BASE}/api/idea/results/${sessionId}`);
    return resp.json();
  },

  async getIdeaSessions() {
    try {
      const resp = await fetch(`${API_BASE}/api/idea/sessions`);
      return resp.json();
    } catch {
      return [];
    }
  },
};
