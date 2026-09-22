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
 * Conversation Storage — persistence layer for Vambery AI Agent.
 *
 * Uses the Superset Extensions Storage API (PR #39171) when available.
 * Falls back to no-op when the API is not present, so the extension
 * works identically on Superset builds without the Storage API.
 *
 * Storage keys:
 *   persistent (user-scoped):
 *     "conversations"   -> { [tabId]: StoredConversation }
 *     "customPrompts"   -> CustomPrompt[]
 *   persistent (shared):
 *     "sharedPlaybooks" -> SharedPlaybook[]
 *   local:
 *     "selectedModelId" -> string
 */

import { extensions } from "@apache-superset/core";

// -------------------------------------------------------------------------
// Data structures (exported for hook & ChatPanel)
// -------------------------------------------------------------------------

export interface StoredConversation {
  version: 1;
  tabId: string;
  messages: ChatMessageData[];
  activePlanState?: Record<string, unknown>;
  todoItems: TodoItemData[];
  pendingQuestion: EditorActionData | null;
  updatedAt: number;
}

// Serializable subsets of ChatPanel types (no functions, no DOM refs)
export interface ChatMessageData {
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: number;
  steps?: AgentStepData[];
  actions?: EditorActionData[];
  error?: boolean;
  hasRunnable?: boolean;
  planState?: Record<string, unknown>;
}

export interface AgentStepData {
  type: string;
  tool: string;
  args: Record<string, unknown>;
  result_summary: string;
}

export interface EditorActionData {
  type: string;
  sql?: string;
  url?: string;
  chart_name?: string;
  viz_type?: string;
  saved?: boolean;
  question?: string;
  options?: { id: string; label: string }[];
  items?: TodoItemData[];
}

export interface TodoItemData {
  id: string;
  text: string;
  status: "pending" | "in_progress" | "done" | "error";
}

export interface CustomPrompt {
  id: string;
  name: string;
  content: string;
  createdAt: number;
}

export interface SharedPlaybook {
  id: string;
  name: string;
  content: string;
  createdBy: string;
  createdAt: number;
}

// -------------------------------------------------------------------------
// Storage API detection
// -------------------------------------------------------------------------

let _storageAvailable: boolean | null = null;

export function isStorageAvailable(): boolean {
  if (_storageAvailable !== null) return _storageAvailable;
  try {
    // Must use the same access path as getStorage(), otherwise detection and
    // actual access can disagree and silently disable persistence.
    const ctx = extensions.getContext();
    _storageAvailable = ctx?.storage?.persistent != null;
  } catch {
    _storageAvailable = false;
  }
  if (!_storageAvailable) {
    console.log("[Vambery] Storage API not available, conversations will not persist");
  }
  return _storageAvailable;
}

/** Reset cached detection (useful if the API becomes available later) */
export function resetStorageDetection(): void {
  _storageAvailable = null;
}

// -------------------------------------------------------------------------
// Internal helpers
// -------------------------------------------------------------------------

function getStorage(): extensions.ExtensionStorage | null {
  try {
    return extensions.getContext().storage;
  } catch {
    return null;
  }
}

// -------------------------------------------------------------------------
// Conversation persistence (Tier 3: persistent, user-scoped, encrypted)
// -------------------------------------------------------------------------

const CONVERSATIONS_KEY = "conversations";

type ConversationsMap = { [tabId: string]: StoredConversation };

async function loadAllConversations(): Promise<ConversationsMap> {
  if (!isStorageAvailable()) return {};
  const storage = getStorage();
  if (!storage) return {};
  try {
    const map = await storage.persistent.get<ConversationsMap>(CONVERSATIONS_KEY);
    if (map && typeof map === "object" && !Array.isArray(map)) {
      return map;
    }
  } catch (err) {
    console.warn("[Vambery] Failed to load conversations:", err);
  }
  return {};
}

async function saveAllConversations(map: ConversationsMap): Promise<void> {
  if (!isStorageAvailable()) return;
  const storage = getStorage();
  if (!storage) return;
  try {
    await storage.persistent.set<ConversationsMap>(
      CONVERSATIONS_KEY,
      map,
      { encrypt: true }
    );
  } catch (err) {
    console.warn("[Vambery] Failed to save conversations:", err);
  }
}

/**
 * Serializes read-modify-write cycles on the conversations map. Without this,
 * two overlapping saves both read the same snapshot and the slower one clobbers
 * the other's conversation.
 */
let _writeChain: Promise<void> = Promise.resolve();

function enqueueWrite(fn: () => Promise<void>): Promise<void> {
  const next = _writeChain.then(fn, fn);
  // Keep the chain alive even if a write rejects.
  _writeChain = next.catch(() => undefined);
  return next;
}

export async function loadConversation(tabId: string): Promise<StoredConversation | null> {
  const all = await loadAllConversations();
  return all[tabId] ?? null;
}

export async function saveConversation(tabId: string, data: StoredConversation): Promise<void> {
  return enqueueWrite(async () => {
    const all = await loadAllConversations();
    all[tabId] = { ...data, updatedAt: Date.now() };
    await saveAllConversations(all);
  });
}

export async function deleteConversation(tabId: string): Promise<void> {
  return enqueueWrite(async () => {
    const all = await loadAllConversations();
    if (!(tabId in all)) return;
    delete all[tabId];
    await saveAllConversations(all);
  });
}

// -------------------------------------------------------------------------
// Model preference (Tier 1: local, user-scoped)
// -------------------------------------------------------------------------

const MODEL_PREF_KEY = "selectedModelId";

export async function loadModelPreference(): Promise<string | null> {
  if (!isStorageAvailable()) return null;
  const storage = getStorage();
  if (!storage) return null;
  try {
    return await storage.local.get<string>(MODEL_PREF_KEY);
  } catch (err) {
    console.warn("[Vambery] Failed to load model preference:", err);
    return null;
  }
}

export async function saveModelPreference(modelId: string): Promise<void> {
  if (!isStorageAvailable()) return;
  const storage = getStorage();
  if (!storage) return;
  try {
    await storage.local.set(MODEL_PREF_KEY, modelId);
  } catch (err) {
    console.warn("[Vambery] Failed to save model preference:", err);
  }
}

// -------------------------------------------------------------------------
// Custom prompts (Tier 3: persistent, user-scoped)
// -------------------------------------------------------------------------

const CUSTOM_PROMPTS_KEY = "customPrompts";

export async function loadCustomPrompts(): Promise<CustomPrompt[]> {
  if (!isStorageAvailable()) return [];
  const storage = getStorage();
  if (!storage) return [];
  try {
    const prompts = await storage.persistent.get<CustomPrompt[]>(CUSTOM_PROMPTS_KEY);
    if (Array.isArray(prompts)) return prompts;
  } catch (err) {
    console.warn("[Vambery] Failed to load custom prompts:", err);
  }
  return [];
}

export async function saveCustomPrompts(prompts: CustomPrompt[]): Promise<void> {
  if (!isStorageAvailable()) return;
  const storage = getStorage();
  if (!storage) return;
  try {
    await storage.persistent.set<CustomPrompt[]>(CUSTOM_PROMPTS_KEY, prompts);
  } catch (err) {
    console.warn("[Vambery] Failed to save custom prompts:", err);
  }
}

// -------------------------------------------------------------------------
// Shared playbooks (Tier 3: persistent, shared/org-scoped)
// -------------------------------------------------------------------------

const SHARED_PLAYBOOKS_KEY = "sharedPlaybooks";

export async function loadSharedPlaybooks(): Promise<SharedPlaybook[]> {
  if (!isStorageAvailable()) return [];
  const storage = getStorage();
  if (!storage) return [];
  try {
    const playbooks = await storage.persistent.shared.get<SharedPlaybook[]>(SHARED_PLAYBOOKS_KEY);
    if (Array.isArray(playbooks)) return playbooks;
  } catch (err) {
    console.warn("[Vambery] Failed to load shared playbooks:", err);
  }
  return [];
}

export async function saveSharedPlaybooks(playbooks: SharedPlaybook[]): Promise<void> {
  if (!isStorageAvailable()) return;
  const storage = getStorage();
  if (!storage) return;
  try {
    await storage.persistent.shared.set<SharedPlaybook[]>(
      SHARED_PLAYBOOKS_KEY,
      playbooks
    );
  } catch (err) {
    console.warn("[Vambery] Failed to save shared playbooks:", err);
  }
}

// -------------------------------------------------------------------------
// Debounced save utility (exported for use by the hook)
// -------------------------------------------------------------------------

export function createDebouncedSave<T extends (...args: any[]) => Promise<void>>(
  fn: T,
  delayMs = 500
): T & { cancel: () => void; flush: () => void } {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let lastArgs: Parameters<T> | null = null;

  const debounced = ((...args: Parameters<T>) => {
    lastArgs = args;
    if (timer) clearTimeout(timer);
    timer = setTimeout(async () => {
      timer = null;
      if (lastArgs) {
        await fn(...lastArgs);
        lastArgs = null;
      }
    }, delayMs);
    return Promise.resolve();
  }) as T & { cancel: () => void; flush: () => void };

  debounced.cancel = () => {
    if (timer) clearTimeout(timer);
    timer = null;
    lastArgs = null;
  };

  debounced.flush = async () => {
    if (timer) clearTimeout(timer);
    timer = null;
    if (lastArgs) {
      await fn(...lastArgs);
      lastArgs = null;
    }
  };

  return debounced;
}
