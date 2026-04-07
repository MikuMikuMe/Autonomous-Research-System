import { useState } from 'react';

interface Props {
  onStart: (mode: 'goal' | 'report', goal: string, options: {
    claims_source?: string;
    max_iterations?: number;
    threshold?: number;
  }) => void;
  disabled?: boolean;
}

export function ResearchInput({ onStart, disabled }: Props) {
  const [mode, setMode] = useState<'goal' | 'report'>('goal');
  const [goal, setGoal] = useState('');
  const [iterations, setIterations] = useState(10);
  const [threshold, setThreshold] = useState(0.9);
  const [showAdvanced, setShowAdvanced] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!goal.trim()) return;
    onStart(mode, goal.trim(), {
      max_iterations: iterations,
      threshold,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="bg-surface rounded-xl p-6 border border-border">
      <h2 className="text-lg font-semibold mb-4">Start Research</h2>

      {/* Mode selector */}
      <div className="flex gap-2 mb-4">
        <button
          type="button"
          onClick={() => setMode('goal')}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            mode === 'goal'
              ? 'bg-primary text-white'
              : 'bg-surface-alt text-text-dim hover:text-text'
          }`}
        >
          Goal-Oriented
        </button>
        <button
          type="button"
          onClick={() => setMode('report')}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            mode === 'report'
              ? 'bg-primary text-white'
              : 'bg-surface-alt text-text-dim hover:text-text'
          }`}
        >
          Deep-Dive Report
        </button>
      </div>

      {/* Description */}
      <p className="text-sm text-text-dim mb-3">
        {mode === 'goal'
          ? 'Iteratively research toward a quantifiable goal. The system converges when claims are verified.'
          : 'Produce a comprehensive research report on a topic with thorough literature review.'}
      </p>

      {/* Goal input */}
      <textarea
        value={goal}
        onChange={e => setGoal(e.target.value)}
        placeholder={
          mode === 'goal'
            ? 'Enter your research goal, e.g. "Prove that transformer models outperform RNNs for time series forecasting"'
            : 'Enter the topic for deep-dive research, e.g. "Recent advances in quantum error correction"'
        }
        rows={3}
        className="w-full bg-surface-alt border border-border rounded-lg px-4 py-3 text-text placeholder:text-text-dim/50 focus:outline-none focus:border-primary resize-none mb-4"
      />

      {/* Advanced options */}
      <button
        type="button"
        onClick={() => setShowAdvanced(!showAdvanced)}
        className="text-sm text-text-dim hover:text-text mb-3 flex items-center gap-1"
      >
        <span className={`transition-transform ${showAdvanced ? 'rotate-90' : ''}`}>▶</span>
        Advanced Options
      </button>

      {showAdvanced && (
        <div className="grid grid-cols-2 gap-4 mb-4 p-4 bg-surface-alt rounded-lg">
          <div>
            <label className="block text-sm text-text-dim mb-1">Max Iterations</label>
            <input
              type="number"
              min={1}
              max={20}
              value={iterations}
              onChange={e => setIterations(Number(e.target.value))}
              className="w-full bg-surface border border-border rounded px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="block text-sm text-text-dim mb-1">Convergence Threshold</label>
            <input
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={threshold}
              onChange={e => setThreshold(Number(e.target.value))}
              className="w-full bg-surface border border-border rounded px-3 py-2 text-sm"
            />
          </div>
        </div>
      )}

      <button
        type="submit"
        disabled={disabled || !goal.trim()}
        className="w-full bg-primary hover:bg-primary-dark disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium py-3 rounded-lg transition-colors"
      >
        {disabled ? 'Research Running...' : mode === 'goal' ? 'Start Goal Research' : 'Start Deep-Dive Report'}
      </button>
    </form>
  );
}
