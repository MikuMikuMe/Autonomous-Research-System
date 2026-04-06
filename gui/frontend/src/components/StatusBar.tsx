import React from "react";
import type { ConnectionStatus } from "../types";

interface Props {
  status: ConnectionStatus;
  progress: number;
  running: boolean;
}

const STATUS_LABELS: Record<ConnectionStatus, string> = {
  connected: "🟢 Connected",
  connecting: "🟡 Connecting…",
  disconnected: "🔴 Disconnected",
};

export const StatusBar: React.FC<Props> = ({ status, progress, running }) => (
  <div className="status-bar">
    <span className="status-bar__label">{STATUS_LABELS[status]}</span>
    {running && (
      <div className="status-bar__progress">
        <div
          className="status-bar__fill"
          style={{ width: `${Math.min(progress, 100)}%` }}
        />
      </div>
    )}
  </div>
);
