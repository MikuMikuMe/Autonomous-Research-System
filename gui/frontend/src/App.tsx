import React, { useCallback } from "react";
import { useWebSocket } from "./hooks/useWebSocket";
import { StatusBar } from "./components/StatusBar";
import { ResearchInput } from "./components/ResearchInput";
import { ProgressLog } from "./components/ProgressLog";
import { ReportView } from "./components/ReportView";
import "./styles/App.css";

const App: React.FC = () => {
  const { status, logs, progress, report, running, startPipeline, clearLogs } =
    useWebSocket();

  const handleSubmit = useCallback(
    async (idea: string) => {
      clearLogs();

      // POST the idea to the REST endpoint; pipeline progress streams via WS
      try {
        const body = new URLSearchParams({ idea });
        await fetch("/api/research", { method: "POST", body });
      } catch {
        // fall back to WS-triggered pipeline run
        startPipeline();
      }
    },
    [clearLogs, startPipeline]
  );

  return (
    <div className="app">
      <h1 className="app__title">Autonomous Research System</h1>
      <StatusBar status={status} progress={progress} running={running} />
      <ResearchInput onSubmit={handleSubmit} disabled={running} />
      <ProgressLog logs={logs} />
      <ReportView report={report} />
    </div>
  );
};

export default App;
