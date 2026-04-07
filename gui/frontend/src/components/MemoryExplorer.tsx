import { useEffect, useState } from 'react';
import { api, type KnowledgeEntry, type Pitfall } from '../api';

export function MemoryExplorer() {
  const [activeTab, setActiveTab] = useState<'knowledge' | 'pitfalls' | 'journey'>('knowledge');
  const [knowledge, setKnowledge] = useState<KnowledgeEntry[]>([]);
  const [pitfalls, setPitfalls] = useState<Pitfall[]>([]);
  const [journey, setJourney] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    const [k, p, j] = await Promise.all([
      api.getKnowledge(),
      api.getPitfalls(),
      api.getMemoryJourney(),
    ]);
    setKnowledge(k);
    setPitfalls(p);
    setJourney(j);
  }

  const tabs = [
    { key: 'knowledge' as const, label: `Knowledge (${knowledge.length})` },
    { key: 'pitfalls' as const, label: `Pitfalls (${pitfalls.length})` },
    { key: 'journey' as const, label: 'Journey' },
  ];

  return (
    <div className="bg-surface rounded-xl border border-border overflow-hidden">
      <div className="flex border-b border-border">
        {tabs.map(tab => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-4 py-3 text-sm font-medium transition-colors ${
              activeTab === tab.key
                ? 'text-primary border-b-2 border-primary'
                : 'text-text-dim hover:text-text'
            }`}
          >
            {tab.label}
          </button>
        ))}
        <button
          onClick={loadData}
          className="ml-auto px-3 py-2 text-xs text-text-dim hover:text-text"
          title="Refresh"
        >
          ↻ Refresh
        </button>
      </div>

      <div className="p-6 max-h-[500px] overflow-y-auto">
        {activeTab === 'knowledge' && <KnowledgeTab entries={knowledge} />}
        {activeTab === 'pitfalls' && <PitfallsTab items={pitfalls} />}
        {activeTab === 'journey' && <JourneyTab data={journey} />}
      </div>
    </div>
  );
}

function KnowledgeTab({ entries }: { entries: KnowledgeEntry[] }) {
  if (entries.length === 0) {
    return <EmptyState text="No knowledge entries yet. Start a research session to build the knowledge base." />;
  }

  return (
    <div className="space-y-3">
      {entries.map((entry, i) => (
        <div key={i} className="bg-surface-alt rounded-lg p-4">
          <div className="flex items-start justify-between mb-2">
            <p className="text-sm flex-1">{entry.claim}</p>
            <span className={`ml-2 px-2 py-0.5 rounded text-xs font-medium ${
              entry.verdict === 'support' ? 'bg-green-900/30 text-success' :
              entry.verdict === 'contradict' ? 'bg-red-900/30 text-danger' :
              'bg-yellow-900/30 text-warning'
            }`}>
              {entry.verdict}
            </span>
          </div>
          <div className="flex items-center gap-4 text-xs text-text-dim">
            <span>Confidence: {(entry.confidence * 100).toFixed(0)}%</span>
            <span>{entry.supporting_papers?.length || 0} papers</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function PitfallsTab({ items }: { items: Pitfall[] }) {
  if (items.length === 0) {
    return <EmptyState text="No pitfalls recorded yet." />;
  }

  return (
    <div className="space-y-3">
      {items.map((item, i) => (
        <div key={i} className="bg-surface-alt rounded-lg p-4">
          <div className="flex items-start gap-3">
            <span className={`px-2 py-0.5 rounded text-xs font-medium shrink-0 ${
              item.severity === 'critical' ? 'bg-danger text-white' :
              item.severity === 'high' ? 'bg-danger/70 text-white' :
              'bg-warning text-black'
            }`}>
              {item.severity}
            </span>
            <div className="flex-1">
              <p className="text-sm">{item.description}</p>
              <span className="text-xs text-text-dim">Occurred {item.frequency}x</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function JourneyTab({ data }: { data: Record<string, unknown> | null }) {
  if (!data) {
    return <EmptyState text="No research journey data available." />;
  }

  return (
    <pre className="bg-surface-alt rounded-lg p-4 text-xs overflow-auto max-h-96">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="text-center py-12 text-text-dim">
      <div className="text-3xl mb-2">🧠</div>
      <p className="text-sm">{text}</p>
    </div>
  );
}
