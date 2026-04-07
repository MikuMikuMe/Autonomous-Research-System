import { useEffect, useState } from 'react';
import { api, type Provider } from '../api';

export function ProviderStatus() {
  const [providers, setProviders] = useState<Provider[]>([]);

  useEffect(() => {
    api.getProviders().then(setProviders);
  }, []);

  if (providers.length === 0) return null;

  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-text-dim">LLM:</span>
      {providers.map(p => (
        <span
          key={p.name}
          className={`px-2 py-0.5 rounded ${
            p.available
              ? 'bg-success/20 text-success'
              : 'bg-surface-alt text-text-dim'
          }`}
        >
          {p.name}
        </span>
      ))}
    </div>
  );
}
