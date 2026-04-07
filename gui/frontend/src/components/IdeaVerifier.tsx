import { useState } from 'react';
import { api } from '../api';

export function IdeaVerifier() {
  const [text, setText] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [iterations, setIterations] = useState(3);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!text.trim()) return;
    setLoading(true);
    setResults(null);
    try {
      const resp = await api.submitIdea(text.trim(), files, iterations);
      if (resp.session_id) {
        setSessionId(resp.session_id);
        pollResults(resp.session_id);
      }
    } catch (err) {
      setResults({ error: String(err) });
      setLoading(false);
    }
  };

  const pollResults = async (sid: string) => {
    for (let i = 0; i < 60; i++) {
      await new Promise(r => setTimeout(r, 3000));
      const data = await api.getIdeaResults(sid);
      if (data.verdict || data.error || data.final_report) {
        setResults(data);
        setLoading(false);
        return;
      }
    }
    setResults({ error: 'Timed out waiting for results' });
    setLoading(false);
  };

  return (
    <div className="bg-surface rounded-xl border border-border overflow-hidden">
      <div className="px-6 py-4 border-b border-border">
        <h2 className="font-semibold">Idea Verification</h2>
        <p className="text-sm text-text-dim mt-1">
          Submit a research idea for iterative verification and flaw detection.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="p-6 space-y-4">
        <textarea
          value={text}
          onChange={e => setText(e.target.value)}
          placeholder="Describe your research idea..."
          rows={4}
          className="w-full bg-surface-alt border border-border rounded-lg px-4 py-3 text-text placeholder:text-text-dim/50 focus:outline-none focus:border-primary resize-none"
        />

        <div className="flex items-center gap-4">
          <label className="text-sm text-text-dim">
            Max Iterations:
            <input
              type="number"
              min={1}
              max={5}
              value={iterations}
              onChange={e => setIterations(Number(e.target.value))}
              className="ml-2 w-16 bg-surface-alt border border-border rounded px-2 py-1 text-sm"
            />
          </label>

          <label className="text-sm text-text-dim cursor-pointer">
            <input
              type="file"
              multiple
              accept="image/*"
              onChange={e => setFiles(Array.from(e.target.files || []))}
              className="hidden"
            />
            <span className="px-3 py-1.5 bg-surface-alt border border-border rounded hover:bg-border/50 transition-colors">
              📎 {files.length > 0 ? `${files.length} file(s)` : 'Attach images'}
            </span>
          </label>
        </div>

        <button
          type="submit"
          disabled={loading || !text.trim()}
          className="w-full bg-primary hover:bg-primary-dark disabled:opacity-50 text-white font-medium py-3 rounded-lg transition-colors"
        >
          {loading ? 'Verifying...' : 'Verify Idea'}
        </button>
      </form>

      {/* Results */}
      {results && (
        <div className="px-6 pb-6">
          <div className="bg-surface-alt rounded-lg p-4">
            <h3 className="text-sm font-medium mb-2">
              {sessionId && <span className="text-text-dim">Session: {sessionId}</span>}
            </h3>
            <pre className="text-xs overflow-auto max-h-64">
              {JSON.stringify(results, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
