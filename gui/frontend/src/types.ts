/** WebSocket message types sent by the FastAPI backend. */

export interface AgentLogMessage {
  type: "agent_log";
  agent: string;
  line: string;
}

export interface ProgressMessage {
  type: "progress";
  agent: string;
  percent: number;
  label: string;
}

export interface PipelineFinishedMessage {
  type: "pipeline_finished";
  all_passed: boolean;
  results: Record<string, unknown>;
}

export interface IdeaLogMessage {
  type: "idea_log";
  session_id: string;
  line: string;
}

export interface IdeaFinishedMessage {
  type: "idea_finished";
  session_id: string;
  final_report: {
    verdict: string;
    flaws: string[];
    recommendations: string[];
  };
  iterations_completed: number;
}

export interface ResearchLogMessage {
  type: "research_log";
  line: string;
}

export interface ResearchFinishedMessage {
  type: "research_finished";
  success: boolean;
  report: string;
}

export type WSMessage =
  | AgentLogMessage
  | ProgressMessage
  | PipelineFinishedMessage
  | IdeaLogMessage
  | IdeaFinishedMessage
  | ResearchLogMessage
  | ResearchFinishedMessage;

export type ConnectionStatus = "disconnected" | "connecting" | "connected";

export interface LogEntry {
  timestamp: string;
  agent: string;
  text: string;
}
