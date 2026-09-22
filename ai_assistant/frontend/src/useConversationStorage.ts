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
 * useConversationStorage — React hook bridging ChatPanel state
 * with the Superset Extensions Storage API.
 *
 * - Loads persisted conversation on mount (per tab ID)
 * - Debounced auto-save on state changes
 * - Tab-switching triggers save-current / load-new
 * - Graceful no-op when Storage API is unavailable
 */

import { useState, useRef, useEffect, useCallback } from "react";
import { sqlLab } from "@apache-superset/core";
import {
  isStorageAvailable,
  loadConversation,
  saveConversation,
  deleteConversation,
  loadModelPreference,
  saveModelPreference,
  createDebouncedSave,
  type StoredConversation,
  type ChatMessageData,
  type TodoItemData,
  type EditorActionData,
} from "./conversationStorage";

const GLOBAL_TAB_ID = "__global__";
const SAVE_DEBOUNCE_MS = 500;

/** Resolve the current SQL Lab tab ID, or a fallback global key */
function getCurrentTabId(): string {
  try {
    return sqlLab.getCurrentTab()?.id ?? GLOBAL_TAB_ID;
  } catch {
    return GLOBAL_TAB_ID;
  }
}

export interface ConversationStorageState {
  /** Current tab ID driving the conversation scope */
  currentTabId: string;
  /** Whether persisted data has been loaded (avoids flash of empty) */
  isLoaded: boolean;
  /** Whether the Storage API is available */
  storageAvailable: boolean;

  // Managed state (mirrors ChatPanel's useState calls)
  messages: ChatMessageData[];
  setMessages: React.Dispatch<React.SetStateAction<ChatMessageData[]>>;
  todoItems: TodoItemData[];
  setTodoItems: React.Dispatch<React.SetStateAction<TodoItemData[]>>;
  pendingQuestion: EditorActionData | null;
  setPendingQuestion: React.Dispatch<React.SetStateAction<EditorActionData | null>>;
  activePlanState: Record<string, unknown> | undefined;
  setActivePlanState: (ps: Record<string, unknown> | undefined) => void;

  // Model preference
  savedModelId: string | null;
  persistModelPreference: (modelId: string) => void;

  // Actions
  clearConversation: () => Promise<void>;
  /** Flush any pending debounced save immediately (e.g. before unmount) */
  flushSave: () => void;
}

export function useConversationStorage(): ConversationStorageState {
  const storageAvailable = isStorageAvailable();

  const [currentTabId, setCurrentTabId] = useState<string>(getCurrentTabId);
  const [isLoaded, setIsLoaded] = useState(!storageAvailable);

  // Core conversation state
  const [messages, setMessages] = useState<ChatMessageData[]>([]);
  const [todoItems, setTodoItems] = useState<TodoItemData[]>([]);
  const [pendingQuestion, setPendingQuestion] = useState<EditorActionData | null>(null);
  const activePlanStateRef = useRef<Record<string, unknown> | undefined>(undefined);

  // Model preference (loaded once)
  const [savedModelId, setSavedModelId] = useState<string | null>(null);

  // Expose planState setter that also triggers save
  const setActivePlanState = useCallback(
    (ps: Record<string, unknown> | undefined) => {
      activePlanStateRef.current = ps;
    },
    []
  );

  // ------------------------------------------------------------------
  // Debounced save: auto-persist on state changes
  // ------------------------------------------------------------------
  const debouncedSaveRef = useRef(
    createDebouncedSave(async (tabId: string, conv: StoredConversation) => {
      await saveConversation(tabId, conv);
    }, SAVE_DEBOUNCE_MS)
  );

  // Build a StoredConversation snapshot from current state
  const buildSnapshot = useCallback(
    (tabId: string): StoredConversation => ({
      version: 1,
      tabId,
      messages,
      activePlanState: activePlanStateRef.current,
      todoItems,
      pendingQuestion,
      updatedAt: Date.now(),
    }),
    [messages, todoItems, pendingQuestion]
  );

  // Auto-save whenever messages/todoItems/pendingQuestion change
  useEffect(() => {
    if (!storageAvailable || !isLoaded) return;
    // Don't save empty conversations (avoid polluting storage on fresh mount)
    if (messages.length === 0) return;
    debouncedSaveRef.current(currentTabId, buildSnapshot(currentTabId));
  }, [storageAvailable, isLoaded, currentTabId, messages, todoItems, pendingQuestion, buildSnapshot]);

  // ------------------------------------------------------------------
  // Load conversation on mount + tab ID polling
  // ------------------------------------------------------------------
  useEffect(() => {
    if (!storageAvailable) return;

    let cancelled = false;

    (async () => {
      // Load model preference (once)
      const modelPref = await loadModelPreference();
      if (!cancelled) setSavedModelId(modelPref);

      // Load conversation for current tab
      const stored = await loadConversation(currentTabId);
      if (!cancelled && stored) {
        setMessages(stored.messages);
        setTodoItems(stored.todoItems ?? []);
        setPendingQuestion(stored.pendingQuestion ?? null);
        activePlanStateRef.current = stored.activePlanState;
      }
      if (!cancelled) setIsLoaded(true);
    })();

    return () => { cancelled = true; };
  }, [storageAvailable]); // Only on mount (storageAvailable won't change)

  // Poll for tab changes (SQL Lab may switch tabs without re-mounting)
  useEffect(() => {
    if (!storageAvailable) return;

    const interval = setInterval(async () => {
      const newTabId = getCurrentTabId();
      if (newTabId === currentTabId) return;

      // Save current conversation before switching
      const snapshot = buildSnapshot(currentTabId);
      if (snapshot.messages.length > 0) {
        debouncedSaveRef.current.cancel();
        await saveConversation(currentTabId, snapshot);
      }

      // Load new tab's conversation
      setCurrentTabId(newTabId);
      const stored = await loadConversation(newTabId);
      if (stored) {
        setMessages(stored.messages);
        setTodoItems(stored.todoItems ?? []);
        setPendingQuestion(stored.pendingQuestion ?? null);
        activePlanStateRef.current = stored.activePlanState;
      } else {
        setMessages([]);
        setTodoItems([]);
        setPendingQuestion(null);
        activePlanStateRef.current = undefined;
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [storageAvailable, currentTabId, buildSnapshot]);

  // Flush on unmount
  useEffect(() => {
    return () => {
      debouncedSaveRef.current.flush();
    };
  }, []);

  // ------------------------------------------------------------------
  // Actions
  // ------------------------------------------------------------------

  const clearConversation = useCallback(async () => {
    debouncedSaveRef.current.cancel();
    setMessages([]);
    setTodoItems([]);
    setPendingQuestion(null);
    activePlanStateRef.current = undefined;
    await deleteConversation(currentTabId);
  }, [currentTabId]);

  const persistModelPreference = useCallback((modelId: string) => {
    saveModelPreference(modelId);
  }, []);

  const flushSave = useCallback(() => {
    debouncedSaveRef.current.flush();
  }, []);

  return {
    currentTabId,
    isLoaded,
    storageAvailable,
    messages,
    setMessages,
    todoItems,
    setTodoItems,
    pendingQuestion,
    setPendingQuestion,
    activePlanState: activePlanStateRef.current,
    setActivePlanState,
    savedModelId,
    persistModelPreference,
    clearConversation,
    flushSave,
  };
}
