import { useState, useCallback, useMemo } from 'react';
import { useWebSocket } from './hooks/useWebSocket';
import { ResearchInput } from './components/ResearchInput';
import { ProgressTracker } from './components/ProgressTracker';
import { ResultsViewer } from './components/ResultsViewer';
import { MemoryExplorer } from './components/MemoryExplorer';
import { ProviderStatus } from './components/ProviderStatus';
import { IdeaVerifier } from './components/IdeaVerifier';

type View = 'research' | 'results' | 'memory' | 'idea';

export default function App() {
  const { connected, messages, send, clearMessages } = useWebSocket();
  const [running, setRunning] = useState(false);
  const [activeView, setActiveView] = useState<View>('research');

  // Derive state from messages
  const researchState = useMemo(() => {
    let iteration = 0;
    const maxIterations = 10;
    let verifiedRatio = 0;
    let converged = false;

    for (const msg of messages) {
      if (msg.type === 'research_finished') {
        converged = (msg.converged as boolean) || false;
        iteration = (msg.iterations as number) || iteration;
      }
      if (msg.type === 'agent_log' && typeof msg.line === 'string') {
        const iterMatch = msg.line.match(/iteration\s+(\d+)/i);
        if (iterMatch) iteration = parseInt(iterMatch[1]);
        const ratioMatch = msg.line.match(/verified.?ratio[:\s]+([0-9.]+)/i);
        if (ratioMatch) verifiedRatio = parseFloat(ratioMatch[1]);
      }
    }

    return { iteration, maxIterations, verifiedRatio, converged };
  }, [messages]);

  const handleStart = useCallback(
    (mode: 'goal' | 'report', goal: string, options: {
      claims_source?: string;
      max_iterations?: number;
      threshold?: number;
    }) => {
      clearMessages();
      setRunning(true);
      send({
        action: 'start_research',
        mode,
        goal,
        ...options,
      });
    },
    [send, clearMessages]
  );

  // Detect when research finishes
  useMemo(() => {
    const finished = messages.find(
      m => m.type === 'research_finished' || m.type === 'research_error'
    );
    if (finished && running) setRunning(false);
  }, [messages, running]);

  const navItems: { key: View; label: string; icon: string }[] = [
    { key: 'research', label: 'Research', icon: '🔬' },
    { key: 'results', label: 'Results', icon: '📊' },
    { key: 'memory', label: 'Memory', icon: '🧠' },
    { key: 'idea', label: 'Idea Verify', icon: '💡' },
  ];

  return (
    <div className="min-h-screen flex flex-col">
      {/* Navigation */}
      <header className="bg-surface border-b border-border">
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-lg font-bold tracking-tight">
              <span className="text-primary">Autonomous</span> Research System
            </h1>
            <span className={`w-2 h-2 rounded-full ${connected ? 'bg-success' : 'bg-danger'}`}
              title={connected ? 'Connected' : 'Disconnected'}
            />
          </div>

          <nav className="flex items-center gap-1">
            {navItems.map(item => (
              <button
                key={item.key}
                onClick={() => setActiveView(item.key)}
                className={`px-3 py-1.5 rounded-lg text-sm transition-colors flex items-center gap-1.5 ${
                  activeView === item.key
                    ? 'bg-primary/10 text-primary'
                    : 'text-text-dim hover:text-text hover:bg-surface-alt'
                }`}
              >
                <span>{item.icon}</span>
                {item.label}
              </button>
            ))}
          </nav>

          <ProviderStatus />
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-6 py-6 space-y-6">
        {activeView === 'research' && (
          <>
            <ResearchInput onStart={handleStart} disabled={running} />
            {(running || messages.length > 0) && (
              <ProgressTracker
                messages={messages}
                running={running}
                iteration={researchState.iteration}
                maxIterations={researchState.maxIterations}
                verifiedRatio={researchState.verifiedRatio}
                converged={researchState.converged}
              />
            )}
          </>
        )}

        {activeView === 'results' && <ResultsViewer />}
        {activeView === 'memory' && <MemoryExplorer />}
        {activeView === 'idea' && <IdeaVerifier />}
      </main>

      {/* Footer */}
      <footer className="border-t border-border py-3 text-center text-xs text-text-dim">
        Autonomous Research System — Iterative AI-Powered Research
      </footer>
    </div>
  );
}
