import { useCallback, useEffect, useRef, useState } from "react";
import type { ConnectionStatus, LogEntry, WSMessage } from "../types";

const WS_URL = "ws://localhost:8000/ws";
const RECONNECT_DELAY_MS = 3000;

export function useWebSocket() {
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [progress, setProgress] = useState(0);
  const [report, setReport] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();

  const now = () => new Date().toLocaleTimeString();

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    setStatus("connecting");

    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => setStatus("connected");

    ws.onclose = () => {
      setStatus("disconnected");
      reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS);
    };

    ws.onerror = () => ws.close();

    ws.onmessage = (ev) => {
      try {
        const msg: WSMessage = JSON.parse(ev.data);
        switch (msg.type) {
          case "agent_log":
            setLogs((prev) => [
              ...prev,
              { timestamp: now(), agent: msg.agent, text: msg.line },
            ]);
            break;
          case "progress":
            setProgress(msg.percent);
            break;
          case "pipeline_finished":
            setRunning(false);
            setProgress(100);
            setReport(JSON.stringify(msg.results, null, 2));
            break;
          case "research_log":
            setLogs((prev) => [
              ...prev,
              { timestamp: now(), agent: "research", text: msg.line },
            ]);
            break;
          case "research_finished":
            setRunning(false);
            setProgress(100);
            setReport(msg.report);
            break;
          default:
            break;
        }
      } catch {
        // ignore non-JSON messages
      }
    };
  }, []);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const sendAction = useCallback(
    (action: string, payload?: Record<string, unknown>) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ action, ...payload }));
      }
    },
    []
  );

  const startPipeline = useCallback(() => {
    setLogs([]);
    setProgress(0);
    setReport(null);
    setRunning(true);
    sendAction("run");
  }, [sendAction]);

  const clearLogs = useCallback(() => {
    setLogs([]);
    setProgress(0);
    setReport(null);
  }, []);

  return {
    status,
    logs,
    progress,
    report,
    running,
    startPipeline,
    clearLogs,
  };
}
