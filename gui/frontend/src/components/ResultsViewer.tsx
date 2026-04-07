import { useEffect, useState } from 'react';
import { api } from '../api';

interface FlawItem {
  description: string;
  severity: string;
  category?: string;
  suggested_fix?: string;
}

interface CrossValidationItem {
  claim: string;
  verdict: string;
  confidence?: number;
  supporting_papers?: string[];
}

export function ResultsViewer() {
  const [activeTab, setActiveTab] = useState<'report' | 'cross_val' | 'flaws' | 'verification'>('report');
  const [report, setReport] = useState<Record<string, unknown> | null>(null);
  const [crossVal, setCrossVal] = useState<CrossValidationItem[]>([]);
  const [flaws, setFlaws] = useState<FlawItem[]>([]);
  const [verification, setVerification] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 5000);
    return () => clearInterval(interval);
  }, []);

  async function loadData() {
    const [r, cv, f, v] = await Promise.all([
      api.getResearchReport(),
      api.getCrossValidation(),
      api.getFlaws(),
      api.getVerification(),
    ]);
    if (r) setReport(r);
    if (cv) {
      const items = cv.results || cv.claims || cv;
      setCrossVal(Array.isArray(items) ? items : []);
    }
    if (f) {
      const items = f.flaws || f;
      setFlaws(Array.isArray(items) ? items : []);
    }
    if (v) setVerification(v);
  }

  const tabs = [
    { key: 'report' as const, label: 'Report' },
    { key: 'cross_val' as const, label: 'Cross-Validation' },
    { key: 'flaws' as const, label: `Flaws (${flaws.length})` },
    { key: 'verification' as const, label: 'Verification' },
  ];

  return (
    <div className="bg-surface rounded-xl border border-border overflow-hidden">
      {/* Tabs */}
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
      </div>

      <div className="p-6">
        {activeTab === 'report' && <ReportTab report={report} />}
        {activeTab === 'cross_val' && <CrossValidationTab items={crossVal} />}
        {activeTab === 'flaws' && <FlawsTab items={flaws} />}
        {activeTab === 'verification' && <VerificationTab data={verification} />}
      </div>
    </div>
  );
}

function ReportTab({ report }: { report: Record<string, unknown> | null }) {
  if (!report) return <EmptyState text="No research report yet. Start a research session." />;

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-4">
        <StatCard label="Iterations" value={String(report.iterations_completed ?? '-')} />
        <StatCard
          label="Converged"
          value={report.converged ? 'Yes' : 'No'}
          color={report.converged ? 'text-success' : 'text-warning'}
        />
        <StatCard label="Mode" value={String(report.mode ?? '-')} />
      </div>
      <pre className="bg-surface-alt rounded-lg p-4 text-xs overflow-auto max-h-96">
        {JSON.stringify(report, null, 2)}
      </pre>
    </div>
  );
}

function CrossValidationTab({ items }: { items: CrossValidationItem[] }) {
  if (items.length === 0) return <EmptyState text="No cross-validation results yet." />;

  return (
    <div className="space-y-3">
      {items.map((item, i) => (
        <div key={i} className="bg-surface-alt rounded-lg p-4">
          <div className="flex items-start justify-between mb-2">
            <p className="text-sm font-medium flex-1">{item.claim}</p>
            <VerdictBadge verdict={item.verdict} />
          </div>
          {item.confidence !== undefined && (
            <div className="flex items-center gap-2 text-xs text-text-dim">
              <span>Confidence: {(item.confidence * 100).toFixed(0)}%</span>
              <div className="flex-1 bg-surface rounded-full h-1.5">
                <div
                  className="h-1.5 rounded-full bg-primary"
                  style={{ width: `${item.confidence * 100}%` }}
                />
              </div>
            </div>
          )}
          {item.supporting_papers && item.supporting_papers.length > 0 && (
            <div className="mt-2 text-xs text-text-dim">
              {item.supporting_papers.length} supporting paper(s)
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function FlawsTab({ items }: { items: FlawItem[] }) {
  if (items.length === 0) return <EmptyState text="No flaws detected." />;

  const severityOrder = ['critical', 'high', 'medium', 'low'];
  const sorted = [...items].sort(
    (a, b) => severityOrder.indexOf(a.severity) - severityOrder.indexOf(b.severity)
  );

  return (
    <div className="space-y-3">
      {sorted.map((flaw, i) => (
        <div key={i} className="bg-surface-alt rounded-lg p-4">
          <div className="flex items-start gap-3">
            <SeverityBadge severity={flaw.severity} />
            <div className="flex-1">
              <p className="text-sm">{flaw.description}</p>
              {flaw.category && (
                <span className="inline-block mt-1 text-xs text-text-dim bg-surface px-2 py-0.5 rounded">
                  {flaw.category}
                </span>
              )}
              {flaw.suggested_fix && (
                <p className="mt-2 text-xs text-text-dim">
                  <strong>Fix:</strong> {flaw.suggested_fix}
                </p>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function VerificationTab({ data }: { data: Record<string, unknown> | null }) {
  if (!data) return <EmptyState text="No verification results yet." />;

  return (
    <pre className="bg-surface-alt rounded-lg p-4 text-xs overflow-auto max-h-96">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}

function StatCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="bg-surface-alt rounded-lg p-4 text-center">
      <div className="text-xs text-text-dim mb-1">{label}</div>
      <div className={`text-xl font-bold ${color || 'text-text'}`}>{value}</div>
    </div>
  );
}

function VerdictBadge({ verdict }: { verdict: string }) {
  const colors: Record<string, string> = {
    support: 'bg-success/20 text-success',
    contradict: 'bg-danger/20 text-danger',
    neutral: 'bg-warning/20 text-warning',
  };
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${colors[verdict] || 'bg-surface text-text-dim'}`}>
      {verdict}
    </span>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const colors: Record<string, string> = {
    critical: 'bg-danger text-white',
    high: 'bg-danger/70 text-white',
    medium: 'bg-warning text-black',
    low: 'bg-info/30 text-info',
  };
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium shrink-0 ${colors[severity] || 'bg-surface text-text-dim'}`}>
      {severity}
    </span>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="text-center py-12 text-text-dim">
      <div className="text-3xl mb-2">📭</div>
      <p className="text-sm">{text}</p>
    </div>
  );
}
