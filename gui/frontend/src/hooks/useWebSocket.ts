import { useEffect, useRef, useState, useCallback } from 'react';

export interface WSMessage {
  type: string;
  [key: string]: unknown;
}

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [messages, setMessages] = useState<WSMessage[]>([]);
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const ws = new WebSocket(`${protocol}//${host}/ws`);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => {
      setConnected(false);
      // Try reconnect after 3s
      setTimeout(() => {
        if (wsRef.current?.readyState === WebSocket.CLOSED) {
          wsRef.current = null;
        }
      }, 3000);
    };
    ws.onmessage = (event) => {
      try {
        const msg: WSMessage = JSON.parse(event.data);
        setMessages(prev => [...prev, msg]);
        setLastMessage(msg);
      } catch {
        // ignore non-JSON
      }
    };

    return () => {
      ws.close();
    };
  }, []);

  const send = useCallback((data: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  const clearMessages = useCallback(() => {
    setMessages([]);
    setLastMessage(null);
  }, []);

  return { connected, messages, lastMessage, send, clearMessages };
}
