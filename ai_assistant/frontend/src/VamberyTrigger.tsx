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
 * Vambery AI Agent — chat trigger.
 *
 * The collapsed entry point rendered by the host when the extension is
 * registered through the `core.chat` contribution (Superset 6.2+). The host
 * owns placement; the trigger owns the toggle and its own visual state.
 */

import React, { useState, useEffect } from "react";
import { chat, theme as themeApi } from "@apache-superset/core";

const VamberyTrigger: React.FC = () => {
  const theme = themeApi.useTheme();
  const [open, setOpen] = useState<boolean>(() => {
    try {
      return chat.isOpen();
    } catch {
      return false;
    }
  });
  const [hovered, setHovered] = useState(false);

  // Track open state — the user can also close the panel from host controls.
  useEffect(() => {
    try {
      const opened = chat.onDidOpen(() => setOpen(true));
      const closed = chat.onDidClose(() => setOpen(false));
      return () => {
        opened.dispose();
        closed.dispose();
      };
    } catch {
      return undefined;
    }
  }, []);

  const toggle = () => {
    try {
      if (chat.isOpen()) {
        chat.close();
      } else {
        chat.open();
      }
    } catch (e) {
      console.warn("[Vambery AI] Could not toggle chat:", e);
    }
  };

  return (
    <button
      type="button"
      onClick={toggle}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      aria-label={open ? "Close Vambery AI Agent" : "Open Vambery AI Agent"}
      aria-expanded={open}
      title="Vambery AI Agent"
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        width: 48,
        height: 48,
        borderRadius: "50%",
        border: `1px solid ${theme.colorPrimaryBorder}`,
        background: open || hovered ? theme.colorPrimary : theme.colorBgElevated,
        color: open || hovered ? theme.colorPrimaryText : theme.colorPrimary,
        fontSize: theme.fontSizeXL,
        lineHeight: 1,
        cursor: "pointer",
        boxShadow: `0 2px 8px ${theme.colorSplit}`,
        transition: "background 0.15s ease, color 0.15s ease",
      }}
    >
      <span role="img" aria-hidden="true">
        &#x1F916;
      </span>
    </button>
  );
};

export default VamberyTrigger;
