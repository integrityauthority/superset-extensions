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
 * SQL Lab integration outside the chat panel.
 *
 * - An "Ask Vambery" button in the SQL editor toolbar opens the chat with the
 *   selected SQL (or the whole editor) as the subject of the question.
 * - A failed query marks its line in the editor and offers "Explain and fix"
 *   in the chat.
 *
 * The panel may not be mounted when these fire, so requests go through a
 * small bus: the panel picks up a pending request when it mounts.
 */

import * as core from "@apache-superset/core";

export interface PromptRequest {
  text: string;
  /** Send immediately instead of prefilling the input. */
  send: boolean;
}

export interface QueryFailure {
  error: string;
  sql: string | null;
  at: number;
}

type Listener<T> = (value: T) => void;

let pendingPrompt: PromptRequest | null = null;
const promptListeners = new Set<Listener<PromptRequest>>();
let lastFailure: QueryFailure | null = null;
const failureListeners = new Set<Listener<QueryFailure | null>>();

/** Subscribe the panel; delivers a request that arrived while it was closed. */
export function onPromptRequest(listener: Listener<PromptRequest>): () => void {
  promptListeners.add(listener);
  if (pendingPrompt) {
    const request = pendingPrompt;
    pendingPrompt = null;
    listener(request);
  }
  return () => promptListeners.delete(listener);
}

export function requestPrompt(request: PromptRequest): void {
  if (promptListeners.size === 0) {
    pendingPrompt = request;
  } else {
    promptListeners.forEach((listener) => listener(request));
  }
  try {
    core.chat.open();
  } catch {
    /* chat not registered yet */
  }
}

export function getLastFailure(): QueryFailure | null {
  return lastFailure;
}

export function onFailureChange(listener: Listener<QueryFailure | null>): () => void {
  failureListeners.add(listener);
  return () => failureListeners.delete(listener);
}

function setFailure(failure: QueryFailure | null): void {
  lastFailure = failure;
  failureListeners.forEach((listener) => listener(failure));
}

/**
 * Editor line (zero-based) the error most likely refers to, or null.
 *
 * Line numbers in database messages ("LINE 2:") count lines of the SQL that
 * was executed, which Superset reformats, so they do not match the editor.
 * Instead, look for an identifier the message quotes ("column \"x\" does not
 * exist", "Invalid column name 'x'") and mark the first editor line using it.
 */
export function errorLine(message: string, editorText: string): number | null {
  const quoted = /["'\[`]([A-Za-z_][\w.$]*)["'\]`]/g;
  const lines = editorText.split("\n");
  for (let match = quoted.exec(message); match; match = quoted.exec(message)) {
    const name = match[1].split(".").pop() as string;
    const pattern = new RegExp(`\\b${name.replace(/\$/g, "\\$")}\\b`, "i");
    const index = lines.findIndex((line) => pattern.test(line));
    if (index >= 0) return index;
  }
  return null;
}

export function explainFailurePrompt(failure: QueryFailure): string {
  const sql = failure.sql ? `\n\n\`\`\`sql\n${failure.sql}\n\`\`\`` : "";
  return (
    "My query failed. Explain the error in plain words, then give me a corrected " +
    `query and put it in the editor.\n\nError:\n${failure.error}${sql}`
  );
}

async function currentEditor(): Promise<core.sqlLab.Editor | null> {
  try {
    const tab = core.sqlLab.getCurrentTab();
    return tab ? await tab.getEditor() : null;
  } catch {
    return null;
  }
}

async function askAboutSelection(): Promise<void> {
  const editor = await currentEditor();
  const selected = editor?.getSelectedText().trim() || "";
  const sql = selected || editor?.getValue().trim() || "";
  const subject = selected ? "this part of my query" : "my query";
  requestPrompt({
    text: sql ? `Explain ${subject}:\n\n\`\`\`sql\n${sql}\n\`\`\`` : "",
    send: false,
  });
}

function explainLastError(): void {
  if (lastFailure) {
    requestPrompt({ text: explainFailurePrompt(lastFailure), send: true });
  } else {
    requestPrompt({ text: "", send: false });
  }
}

/** Register commands, toolbar items and query listeners. Called once. */
export function registerSqlLabIntegration(): void {
  core.commands.registerCommand(
    {
      id: "vambery.askAboutSelection",
      title: "Ask Vambery",
      icon: "CommentOutlined",
      description: "Ask Vambery about the selected SQL (or the whole query)",
    },
    askAboutSelection,
  );
  core.commands.registerCommand(
    {
      id: "vambery.explainLastError",
      title: "Explain and fix the last error",
      icon: "BugOutlined",
      description: "Ask Vambery to explain the last failed query and fix it",
    },
    explainLastError,
  );
  core.menus.registerMenuItem(
    { view: "sqllab.editor", command: "vambery.askAboutSelection" },
    "sqllab.editor",
    "primary",
  );
  core.menus.registerMenuItem(
    { view: "sqllab.editor", command: "vambery.explainLastError" },
    "sqllab.editor",
    "secondary",
  );

  core.sqlLab.onDidQueryFail(async (context) => {
    const failure: QueryFailure = {
      error: context.errorMessage,
      sql: context.executedSql,
      at: Date.now(),
    };
    setFailure(failure);
    try {
      const editor = await context.tab.getEditor();
      const line = errorLine(context.errorMessage, editor.getValue());
      if (line !== null) {
        editor.setAnnotations([
          { line, message: context.errorMessage, severity: "error" },
        ]);
      }
    } catch {
      /* editor gone */
    }
  });
  core.sqlLab.onDidQuerySuccess(async (context) => {
    setFailure(null);
    try {
      (await context.tab.getEditor()).clearAnnotations();
    } catch {
      /* editor gone */
    }
  });
}
