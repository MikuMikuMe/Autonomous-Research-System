import type { WSMessage } from '../hooks/useWebSocket';

interface Props {
  messages: WSMessage[];
  running: boolean;
  iteration: number;
  maxIterations: number;
  verifiedRatio: number;
  converged: boolean;
}

export function ProgressTracker({
  messages,
  running,
  iteration,
  maxIterations,
  verifiedRatio,
  converged,
}: Props) {
  const progressPct = maxIterations > 0 ? (iteration / maxIterations) * 100 : 0;
  const logs = messages
    .filter(m => m.type === 'agent_log' || m.type === 'research_log')
    .slice(-50);

  return (
    <div className="bg-surface rounded-xl border border-border overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b border-border flex items-center justify-between">
        <h2 className="font-semibold">Research Progress</h2>
        <div className="flex items-center gap-3">
          {running && (
            <span className="flex items-center gap-2 text-sm text-info">
              <span className="w-2 h-2 bg-info rounded-full animate-pulse" />
              Running
            </span>
          )}
          {converged && (
            <span className="text-sm text-success font-medium">✓ Converged</span>
          )}
          {!running && !converged && iteration > 0 && (
            <span className="text-sm text-warning">Completed (not converged)</span>
          )}
        </div>
      </div>

      {/* Progress bar */}
      <div className="px-6 pt-4">
        <div className="flex justify-between text-sm text-text-dim mb-1">
          <span>Iteration {iteration} / {maxIterations}</span>
          <span>Verified: {(verifiedRatio * 100).toFixed(0)}%</span>
        </div>
        <div className="w-full bg-surface-alt rounded-full h-2 mb-1">
          <div
            className="h-2 rounded-full transition-all duration-500 bg-primary"
            style={{ width: `${Math.min(progressPct, 100)}%` }}
          />
        </div>
        <div className="w-full bg-surface-alt rounded-full h-1.5 mb-4">
          <div
            className="h-1.5 rounded-full transition-all duration-500 bg-success"
            style={{ width: `${Math.min(verifiedRatio * 100, 100)}%` }}
          />
        </div>
      </div>

      {/* Log output */}
      <div className="px-6 pb-4">
        <div className="bg-[#13131f] rounded-lg p-4 max-h-64 overflow-y-auto font-mono text-xs leading-relaxed">
          {logs.length === 0 ? (
            <span className="text-text-dim">Waiting for research to start...</span>
          ) : (
            logs.map((msg, i) => (
              <div key={i} className="text-text-dim">
                {msg.line as string || JSON.stringify(msg)}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
