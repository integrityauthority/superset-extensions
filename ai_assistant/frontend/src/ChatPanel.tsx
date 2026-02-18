/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */

/**
 * Vambery AI Agent Chat Panel
 *
 * Renders in the SQL Lab right sidebar. Provides a chat interface
 * for users to interact with the AI agent, which can inspect
 * database schemas, write SQL queries, and modify the SQL editor.
 */

import React, { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { sqlLab, authentication, useTheme, SupersetTheme } from "@apache-superset/core";

// --------------------------------------------------------------------------
// Types
// --------------------------------------------------------------------------

interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: number;
  steps?: AgentStep[];
  actions?: EditorAction[];
  error?: boolean;
  hasRunnable?: boolean;
}

interface AgentStep {
  type: string;
  tool: string;
  args: Record<string, unknown>;
  result_summary: string;
}

interface EditorAction {
  type: string;
  sql?: string;
}

interface ChatContext {
  database_id: number | undefined;
  database_name: string | undefined;
  schema: string | null;
  catalog: string | null;
  current_sql: string;
}

// --------------------------------------------------------------------------
// SSE Streaming API Helper
// --------------------------------------------------------------------------

interface StreamEvent {
  event: "step" | "action" | "response" | "error";
  data: Record<string, unknown>;
}

/**
 * Post a chat message and stream SSE events back.
 * Calls onEvent for each parsed SSE event as it arrives.
 */
async function postChatStream(
  messages: { role: string; content: string }[],
  context: ChatContext,
  onEvent: (evt: StreamEvent) => void
): Promise<void> {
  const csrfToken = await authentication.getCSRFToken();

  const response = await fetch("/api/v1/ai_assistant/chat/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
    },
    credentials: "same-origin",
    body: JSON.stringify({ messages, context }),
  });

  if (!response.ok) {
    const errData = await response.json().catch(() => ({}));
    throw new Error(
      (errData as Record<string, string>).error ||
        `HTTP ${response.status}: ${response.statusText}`
    );
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error("ReadableStream not supported");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // SSE format: "event: <type>\ndata: <json>\n\n"
    // Split on double newline to get complete events
    const parts = buffer.split("\n\n");
    // Last part may be incomplete — keep it in the buffer
    buffer = parts.pop() || "";

    for (const part of parts) {
      if (!part.trim()) continue;
      let eventType = "";
      let eventData = "";

      for (const line of part.split("\n")) {
        if (line.startsWith("event: ")) {
          eventType = line.slice(7).trim();
        } else if (line.startsWith("data: ")) {
          eventData = line.slice(6);
        }
      }

      if (eventType && eventData) {
        try {
          onEvent({
            event: eventType as StreamEvent["event"],
            data: JSON.parse(eventData),
          });
        } catch (e) {
          console.warn("[Vambery AI] Failed to parse SSE event:", e, eventData);
        }
      }
    }
  }
}

// --------------------------------------------------------------------------
// Styles - theme-aware (uses Superset theme tokens for light/dark support)
// --------------------------------------------------------------------------

function getStyles(t: SupersetTheme) {
  return {
    container: {
      display: "flex",
      flexDirection: "column" as const,
      height: "100%",
      fontFamily: t.fontFamily,
      fontSize: t.fontSize,
      backgroundColor: t.colorBgLayout,
      color: t.colorText,
    },
    header: {
      padding: `${t.paddingSM}px ${t.padding}px`,
      borderBottom: `1px solid ${t.colorBorderSecondary}`,
      backgroundColor: t.colorBgContainer,
      fontWeight: t.fontWeightStrong,
      fontSize: t.fontSizeLG,
      display: "flex",
      alignItems: "center",
      gap: t.sizeXS,
    },
    headerIcon: {
      fontSize: t.fontSizeLG,
    },
    betaBadge: {
      fontSize: t.fontSizeSM - 2,
      color: t.colorTextTertiary,
      marginLeft: "auto",
    },
    messagesContainer: {
      flex: 1,
      overflowY: "auto" as const,
      padding: `${t.paddingSM}px ${t.padding}px`,
    },
    messageBubble: (isUser: boolean) => ({
      marginBottom: t.marginSM,
      padding: `${t.paddingXS + 2}px ${t.paddingSM + 2}px`,
      borderRadius: t.borderRadius,
      backgroundColor: isUser ? t.colorPrimary : t.colorBgContainer,
      color: isUser ? "#fff" : t.colorText,
      border: isUser ? "none" : `1px solid ${t.colorBorderSecondary}`,
      maxWidth: "100%",
      lineHeight: t.lineHeight,
      whiteSpace: "pre-wrap" as const,
      wordBreak: "break-word" as const,
    }),
    stepsContainer: {
      marginTop: t.marginXS,
      padding: `${t.paddingXS}px ${t.paddingXS + 2}px`,
      backgroundColor: t.colorFillQuaternary,
      borderRadius: t.borderRadiusSM,
      fontSize: t.fontSizeSM - 2,
      color: t.colorTextTertiary,
      border: `1px solid ${t.colorBorderSecondary}`,
    },
    stepItem: {
      padding: "2px 0",
      display: "flex",
      gap: 6,
      alignItems: "flex-start",
    },
    stepIcon: {
      color: t.colorSuccess,
      flexShrink: 0,
    },
    stepArgs: {
      color: t.colorTextTertiary,
    },
    inputContainer: {
      padding: `${t.paddingSM}px ${t.padding}px`,
      borderTop: `1px solid ${t.colorBorderSecondary}`,
      backgroundColor: t.colorBgContainer,
    },
    textArea: {
      width: "100%",
      border: `1px solid ${t.colorBorder}`,
      borderRadius: t.borderRadius,
      padding: `${t.paddingXS}px ${t.paddingSM}px`,
      fontSize: t.fontSize,
      resize: "none" as const,
      outline: "none",
      fontFamily: "inherit",
      lineHeight: t.lineHeight,
      minHeight: 60,
      maxHeight: 120,
      backgroundColor: t.colorBgContainer,
      color: t.colorText,
    },
    buttonRow: {
      display: "flex",
      justifyContent: "flex-end",
      marginTop: t.marginXS,
      gap: t.sizeXS,
    },
    sendButton: (disabled: boolean) => ({
      padding: `${t.paddingXS - 2}px ${t.padding}px`,
      backgroundColor: disabled ? t.colorFillSecondary : t.colorPrimary,
      color: disabled ? t.colorTextTertiary : "#fff",
      border: "none",
      borderRadius: t.borderRadiusSM,
      cursor: disabled ? "not-allowed" : "pointer",
      fontSize: t.fontSize,
      fontWeight: t.fontWeightStrong,
    }),
    clearButton: {
      padding: `${t.paddingXS - 2}px ${t.paddingSM}px`,
      backgroundColor: "transparent",
      color: t.colorTextSecondary,
      border: `1px solid ${t.colorBorder}`,
      borderRadius: t.borderRadiusSM,
      cursor: "pointer",
      fontSize: t.fontSizeSM,
    },
    loadingDots: {
      display: "inline-flex",
      gap: 4,
      padding: `${t.paddingXS + 2}px ${t.paddingSM + 2}px`,
      backgroundColor: t.colorBgContainer,
      border: `1px solid ${t.colorBorderSecondary}`,
      borderRadius: t.borderRadius,
      marginBottom: t.marginSM,
      color: t.colorTextSecondary,
    },
    emptyState: {
      display: "flex",
      flexDirection: "column" as const,
      alignItems: "center",
      justifyContent: "center",
      height: "100%",
      color: t.colorTextTertiary,
      textAlign: "center" as const,
      padding: t.paddingLG * 2,
      gap: t.marginSM,
    },
    emptyIcon: {
      fontSize: 40,
      opacity: 0.5,
    },
    emptySubtext: {
      fontSize: t.fontSizeSM,
      color: t.colorTextPlaceholder,
    },
    errorBubble: {
      marginBottom: t.marginSM,
      padding: `${t.paddingXS + 2}px ${t.paddingSM + 2}px`,
      borderRadius: t.borderRadius,
      backgroundColor: t.colorErrorBg,
      color: t.colorError,
      border: `1px solid ${t.colorErrorBorder}`,
      fontSize: t.fontSizeSM,
    },
    runQueryButton: {
      display: "inline-flex",
      alignItems: "center",
      gap: 6,
      marginTop: t.marginXS,
      marginBottom: t.marginSM,
      padding: `${t.paddingXS - 2}px ${t.paddingSM + 2}px`,
      backgroundColor: t.colorSuccess,
      color: "#fff",
      border: "none",
      borderRadius: t.borderRadiusSM,
      cursor: "pointer",
      fontSize: t.fontSizeSM,
      fontWeight: t.fontWeightStrong,
    },
    stepSpinner: {
      display: "inline-block",
      width: 10,
      height: 10,
      border: `2px solid ${t.colorTextQuaternary}`,
      borderTopColor: t.colorPrimary,
      borderRadius: "50%",
      animation: "vambery-spin 0.8s linear infinite",
      flexShrink: 0,
    },
    streamingLabel: {
      fontWeight: 600,
      marginBottom: 4,
      display: "flex",
      alignItems: "center",
      gap: 6,
    },
  };
}

// --------------------------------------------------------------------------
// Component
// --------------------------------------------------------------------------

const ChatPanel: React.FC = () => {
  const theme = useTheme();
  const styles = useMemo(() => getStyles(theme), [theme]);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  // Steps that arrive progressively while the agent is working
  const [streamingSteps, setStreamingSteps] = useState<AgentStep[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textAreaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom when new messages or streaming steps arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading, streamingSteps]);

  // Inject the CSS keyframe animation for the spinner (once)
  useEffect(() => {
    const styleId = "vambery-spin-keyframes";
    if (!document.getElementById(styleId)) {
      const style = document.createElement("style");
      style.id = styleId;
      style.textContent =
        "@keyframes vambery-spin { to { transform: rotate(360deg); } }";
      document.head.appendChild(style);
    }
  }, []);

  // Get current SQL Lab context
  const getContext = useCallback(async (): Promise<ChatContext> => {
    const tab = sqlLab.getCurrentTab();
    let currentSql = "";

    if (tab) {
      try {
        const editor = await tab.getEditor();
        currentSql = editor.getValue() || "";
      } catch (e) {
        console.warn("[Vambery AI] Could not get editor content:", e);
      }
    }

    return {
      database_id: tab?.databaseId,
      database_name: undefined, // Will be resolved by backend
      schema: tab?.schema || null,
      catalog: tab?.catalog || null,
      current_sql: currentSql,
    };
  }, []);

  // Apply a single action immediately (called as actions stream in)
  const applyAction = useCallback(async (action: EditorAction): Promise<boolean> => {
    if (action.type === "set_editor_sql" && action.sql) {
      const tab = sqlLab.getCurrentTab();
      if (tab) {
        try {
          const editor = await tab.getEditor();
          editor.setValue(action.sql);
          console.log("[Vambery AI] Set editor SQL:", action.sql.slice(0, 80));

          // Auto-execute SELECT queries
          if (action.sql.trim().toUpperCase().startsWith("SELECT") ||
              action.sql.trim().toUpperCase().startsWith("WITH")) {
            // Small delay so the editor value is committed before execution
            await new Promise((r) => setTimeout(r, 150));
            try {
              await sqlLab.executeQuery();
              console.log("[Vambery AI] Auto-executed query");
            } catch (e) {
              console.error("[Vambery AI] Failed to auto-execute query:", e);
            }
            return true;
          }
        } catch (e) {
          console.error("[Vambery AI] Failed to set editor SQL:", e);
        }
      }
    }
    return false;
  }, []);

  // Run the current query in the SQL editor (manual fallback button)
  const handleRunQuery = useCallback(async () => {
    try {
      await sqlLab.executeQuery();
      console.log("[Vambery AI] Query executed");
    } catch (e) {
      console.error("[Vambery AI] Failed to execute query:", e);
    }
  }, []);

  // Send message handler — uses SSE streaming
  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;

    const userMessage: ChatMessage = {
      role: "user",
      content: text,
      timestamp: Date.now(),
    };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);
    setStreamingSteps([]);

    try {
      const context = await getContext();

      if (!context.database_id) {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content:
              "Please select a database in the left sidebar first, so I know which database to work with.",
            timestamp: Date.now(),
            error: true,
          },
        ]);
        setLoading(false);
        return;
      }

      // Build message history for the API (only role + content)
      const apiMessages = [
        ...messages.map((m) => ({ role: m.role, content: m.content })),
        { role: "user", content: text },
      ];

      // Accumulators for the streaming response
      const collectedSteps: AgentStep[] = [];
      const collectedActions: EditorAction[] = [];
      let finalResponse = "";
      let hasError = false;
      let hasRunnable = false;

      await postChatStream(apiMessages, context, async (evt) => {
        if (evt.event === "step") {
          const step = evt.data as unknown as AgentStep;
          collectedSteps.push(step);
          // Update the live streaming steps display
          setStreamingSteps([...collectedSteps]);
        } else if (evt.event === "action") {
          const action = evt.data as unknown as EditorAction;
          collectedActions.push(action);
          // Apply the action immediately (sets SQL + auto-runs)
          const ran = await applyAction(action);
          if (ran) hasRunnable = true;
        } else if (evt.event === "response") {
          finalResponse =
            (evt.data.response as string) || "I couldn't generate a response.";
        } else if (evt.event === "error") {
          finalResponse = `Error: ${evt.data.error || "Something went wrong"}`;
          hasError = true;
        }
      });

      // Build the final assistant message with all collected data
      const assistantMessage: ChatMessage = {
        role: "assistant",
        content: finalResponse || "I couldn't generate a response.",
        timestamp: Date.now(),
        steps: collectedSteps,
        actions: collectedActions,
        error: hasError,
        hasRunnable: hasRunnable,
      };
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      console.error("[Vambery AI] Chat error:", error);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `Error: ${(error as Error).message || "Something went wrong"}`,
          timestamp: Date.now(),
          error: true,
        },
      ]);
    } finally {
      setLoading(false);
      setStreamingSteps([]);
    }
  }, [input, loading, messages, getContext, applyAction]);

  // Handle Enter key (Shift+Enter for newline)
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  // Clear conversation
  const handleClear = useCallback(() => {
    setMessages([]);
    setInput("");
  }, []);

  return (
    <div style={styles.container}>
      {/* Header */}
      <div style={styles.header}>
        <span style={styles.headerIcon}>&#x1F916;</span>
        <span>Vambery AI Agent</span>
        <span style={styles.betaBadge}>BETA</span>
      </div>

      {/* Messages area */}
      <div style={styles.messagesContainer}>
        {messages.length === 0 && !loading && (
          <div style={styles.emptyState}>
            <div style={styles.emptyIcon}>&#x1F4AC;</div>
            <div>
              <strong>Ask me anything about your data</strong>
            </div>
            <div style={styles.emptySubtext}>
              I can explore schemas, write SQL queries, and help you analyse
              your data. Select a database and schema first, then describe what
              you need.
            </div>
          </div>
        )}

        {messages.map((msg, idx) => (
          <div key={idx}>
            {/* User messages render normally */}
            {msg.role === "user" && (
              <div style={styles.messageBubble(true)}>{msg.content}</div>
            )}

            {/* Assistant: steps ABOVE the response text */}
            {msg.role === "assistant" && (
              <>
                {/* Agent steps (thinking process) — shown first */}
                {msg.steps && msg.steps.length > 0 && (
                  <div style={styles.stepsContainer}>
                    <div style={{ fontWeight: 600, marginBottom: 4 }}>
                      Agent steps:
                    </div>
                    {msg.steps.map((step, sIdx) => (
                      <div key={sIdx} style={styles.stepItem}>
                        <span style={styles.stepIcon}>&#x2713;</span>
                        <span>
                          <strong>{step.tool}</strong>
                          {step.args && Object.keys(step.args).length > 0 && (
                            <span style={styles.stepArgs}>
                              ({Object.values(step.args).join(", ")})
                            </span>
                          )}
                          {" — "}
                          {step.result_summary}
                        </span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Response text — below the steps */}
                {msg.error ? (
                  <div style={styles.errorBubble}>{msg.content}</div>
                ) : (
                  <div style={styles.messageBubble(false)}>{msg.content}</div>
                )}

                {/* "Re-run query" button at the bottom */}
                {msg.hasRunnable && (
                  <button
                    style={styles.runQueryButton}
                    onClick={handleRunQuery}
                    type="button"
                  >
                    &#9654; Re-run query
                  </button>
                )}
              </>
            )}
          </div>
        ))}

        {/* Live streaming steps + loading indicator */}
        {loading && (
          <div>
            <div style={styles.stepsContainer}>
              <div style={styles.streamingLabel}>
                <span style={styles.stepSpinner} />
                <span>Agent working...</span>
              </div>
              {streamingSteps.map((step, sIdx) => (
                <div key={sIdx} style={styles.stepItem}>
                  <span style={styles.stepIcon}>&#x2713;</span>
                  <span>
                    <strong>{step.tool}</strong>
                    {step.args && Object.keys(step.args).length > 0 && (
                      <span style={styles.stepArgs}>
                        ({Object.values(step.args).join(", ")})
                      </span>
                    )}
                    {" — "}
                    {step.result_summary}
                  </span>
                </div>
              ))}
              {streamingSteps.length === 0 && (
                <div style={{ color: styles.stepsContainer.color, padding: "2px 0" }}>
                  Connecting to AI...
                </div>
              )}
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div style={styles.inputContainer}>
        <textarea
          ref={textAreaRef}
          style={styles.textArea}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about your data... (Enter to send, Shift+Enter for newline)"
          disabled={loading}
          rows={3}
        />
        <div style={styles.buttonRow}>
          {messages.length > 0 && (
            <button style={styles.clearButton} onClick={handleClear} type="button">
              Clear
            </button>
          )}
          <button
            style={styles.sendButton(loading || !input.trim())}
            onClick={handleSend}
            disabled={loading || !input.trim()}
            type="button"
          >
            {loading ? "Thinking..." : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ChatPanel;
