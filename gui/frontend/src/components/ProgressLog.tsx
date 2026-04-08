import React, { useEffect, useRef } from "react";
import type { LogEntry } from "../types";

interface Props {
  logs: LogEntry[];
}

export const ProgressLog: React.FC<Props> = ({ logs }) => {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  return (
    <div className="progress-log">
      <h3>Agent Logs</h3>
      <div className="progress-log__entries">
        {logs.length === 0 && (
          <p className="progress-log__empty">No logs yet — start a run.</p>
        )}
        {logs.map((entry, i) => (
          <div key={i} className="progress-log__entry">
            <span className="progress-log__time">{entry.timestamp}</span>
            {entry.agent && (
              <span className="progress-log__agent">[{entry.agent}]</span>
            )}
            <span className="progress-log__text">{entry.text}</span>
          </div>
        ))}
        <div ref={endRef} />
      </div>
    </div>
  );
};
