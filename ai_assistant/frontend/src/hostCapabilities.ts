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
 * Thin wrappers over the host APIs the panel reads on every render.
 *
 * Superset 7.0+ is the minimum host, so `chat`, `navigation` and `sqlLab`
 * always exist. The wrappers only absorb errors thrown while the host tears
 * a page down, and turn event subscriptions into plain unsubscribe functions
 * for React effects.
 */

import * as core from "@apache-superset/core";

type Page = core.navigation.Page;

function toUnsubscribe(disposable: core.common.Disposable): () => void {
  return () => {
    try {
      disposable.dispose();
    } catch {
      /* host already torn down */
    }
  };
}

export function getCurrentPage(): Page | null {
  try {
    return core.navigation.getPage();
  } catch {
    return null;
  }
}

/** The agent works on a SQL Lab tab's database; other pages get a notice. */
export function isSqlLabContext(): boolean {
  return getCurrentPage() === "sqllab";
}

export function onPageChange(listener: (page: Page) => void): () => void {
  return toUnsubscribe(core.navigation.onDidChangePage(listener));
}

export function getDisplayMode(): core.chat.DisplayMode {
  return core.chat.getDisplayMode();
}

export function onDisplayModeChange(
  listener: (mode: core.chat.DisplayMode) => void,
): () => void {
  return toUnsubscribe(core.chat.onDidChangeDisplayMode(listener));
}

/** The active SQL Lab tab, or null outside SQL Lab. */
export function safeGetCurrentTab(): core.sqlLab.Tab | null {
  if (!isSqlLabContext()) return null;
  try {
    return core.sqlLab.getCurrentTab() ?? null;
  } catch {
    return null;
  }
}
