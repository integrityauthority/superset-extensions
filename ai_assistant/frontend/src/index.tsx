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
 * ExtensionsLoader on import) through the official chat surface, available
 * on every page. The host owns placement, open/close state and display mode
 * (floating or docked panel).
 */

import * as core from "@apache-superset/core";
import ChatPanel from "./ChatPanel";
import VamberyTrigger from "./VamberyTrigger";
import { registerSqlLabIntegration } from "./sqlLabBridge";

const CHAT_ID = "integrityauthority.vambery";
const DISPLAY_NAME = "Vambery AI Agent";
const DESCRIPTION =
  "AI-powered SQL assistant — explores schemas, writes and runs queries, and builds charts.";

// Superset 7.0+ only: the SIP-214 chat contribution is the single surface.
// Vambery 0.7.x is the last release with the SQL Lab sidebar fallback for 6.x.
try {
  core.chat.registerChat(
    { id: CHAT_ID, name: DISPLAY_NAME, description: DESCRIPTION },
    VamberyTrigger,
    ChatPanel,
  );
  console.log("[Vambery AI Agent] Extension activated (core.chat)");
} catch (e) {
  console.error("[Vambery AI Agent] core.chat registration failed:", e);
}

try {
  registerSqlLabIntegration();
} catch (e) {
  console.error("[Vambery AI Agent] SQL Lab integration failed:", e);
}
