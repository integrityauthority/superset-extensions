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
 * Host capability detection.
 *
 * The extension targets several Superset versions at once:
 *
 *   6.1  — only `views` (SQL Lab right sidebar). No chat, navigation or storage.
 *   6.2  — adds `core.chat` + `navigation`, so the panel can mount on any page.
 *   7.0  — additionally adds the extensions Storage API.
 *
 * Everything here feature-detects at runtime and degrades rather than throwing,
 * so one build runs on all three.
 */

import * as core from "@apache-superset/core";

type Page = core.navigation.Page;

/** Whether the host exposes the SIP-214 chat contribution (6.2+). */
export function isChatApiAvailable(): boolean {
  try {
    return typeof (core as { chat?: { registerChat?: unknown } }).chat
      ?.registerChat === "function";
  } catch {
    return false;
  }
}

/** Whether the host exposes the navigation namespace (6.2+). */
export function isNavigationApiAvailable(): boolean {
  try {
    return typeof (core as { navigation?: { getPage?: unknown } }).navigation
      ?.getPage === "function";
  } catch {
    return false;
  }
}

/** Current page, or null when the host predates the navigation API. */
export function getCurrentPage(): Page | null {
  if (!isNavigationApiAvailable()) return null;
  try {
    return core.navigation.getPage();
  } catch {
    return null;
  }
}

/**
 * Whether we are on a page where the SQL Lab APIs are usable.
 *
 * On 6.2+ the sqlLab namespace is wrapped in a page-scoped Proxy that THROWS
 * when touched from the wrong page, so this must be checked before any
 * sqlLab.* call once the panel can mount globally.
 *
 * On hosts without the navigation API we are only ever mounted in the SQL Lab
 * sidebar, so SQL Lab is implied.
 */
export function isSqlLabContext(): boolean {
  const page = getCurrentPage();
  if (page === null) return true;
  return page === "sqllab";
}

/**
 * Subscribe to page changes. Returns an unsubscribe function; a no-op on hosts
 * without the navigation API.
 */
export function onPageChange(listener: (page: Page) => void): () => void {
  if (!isNavigationApiAvailable()) return () => undefined;
  try {
    const disposable = core.navigation.onDidChangePage(listener);
    return () => {
      try {
        disposable.dispose();
      } catch {
        /* host already torn down */
      }
    };
  } catch {
    return () => undefined;
  }
}

/**
 * Read the current SQL Lab tab, or null when unavailable — either because we
 * are on another page or because the host threw.
 */
export function safeGetCurrentTab(): core.sqlLab.Tab | null {
  if (!isSqlLabContext()) return null;
  try {
    return core.sqlLab.getCurrentTab() ?? null;
  } catch {
    return null;
  }
}
