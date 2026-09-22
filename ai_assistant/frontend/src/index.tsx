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
 * Vambery AI Agent Extension — entry point.
 *
 * Registers the agent as a module-level side effect (called by
 * ExtensionsLoader on import), preferring the official chat surface and
 * falling back to the SQL Lab sidebar:
 *
 *   Superset 6.2+  -> `core.chat` contribution. Available on every page,
 *                     with the host owning placement, open/close state and
 *                     display mode (floating or docked panel).
 *   Superset 6.1   -> `views` contribution in the SQL Lab right sidebar.
 *
 * A namespace import is used deliberately: a named `chat` import would fail
 * to link on hosts that do not export it.
 */

import React from "react";
import * as core from "@apache-superset/core";
import ChatPanel from "./ChatPanel";
import VamberyTrigger from "./VamberyTrigger";
import { isChatApiAvailable } from "./hostCapabilities";

const CHAT_ID = "integrityauthority.vambery";
const VIEW_ID = "vambery_ai_assistant.chatPanel";
const DISPLAY_NAME = "Vambery AI Agent";
const DESCRIPTION =
  "AI-powered SQL assistant — explores schemas, writes and runs queries, and builds charts.";

/** Register through the SIP-214 chat contribution. Returns false if unavailable. */
function registerAsChat(): boolean {
  if (!isChatApiAvailable()) return false;
  try {
    core.chat.registerChat(
      { id: CHAT_ID, name: DISPLAY_NAME, description: DESCRIPTION },
      VamberyTrigger,
      ChatPanel,
    );
    return true;
  } catch (e) {
    console.warn("[Vambery AI Agent] core.chat registration failed:", e);
    return false;
  }
}

/** Register in the SQL Lab right sidebar (pre-6.2 hosts). */
function registerAsSidebarView(): boolean {
  try {
    core.views.registerView(
      { id: VIEW_ID, name: DISPLAY_NAME, description: DESCRIPTION },
      "sqllab.rightSidebar",
      () => <ChatPanel />,
    );
    return true;
  } catch (e) {
    console.error("[Vambery AI Agent] sidebar registration failed:", e);
    return false;
  }
}

// The host persists the user's display mode and open/closed state across
// reloads, so deliberately no setDisplayMode() call here — forcing one would
// override the user's own choice on every page load.
if (registerAsChat()) {
  console.log("[Vambery AI Agent] Extension activated (core.chat)");
} else if (registerAsSidebarView()) {
  console.log("[Vambery AI Agent] Extension activated (SQL Lab sidebar)");
} else {
  console.error("[Vambery AI Agent] Extension failed to register");
}
