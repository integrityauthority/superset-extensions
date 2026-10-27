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
 * Per-user settings: favourite models, the model to start with, the answer
 * language, and clearing stored conversations. The administrator's defaults
 * (provider, default model, available deployments) come from Superset's
 * config; these settings only narrow or adjust them for one user.
 */

import React, { useState } from "react";
import type { AnswerLanguage, UserSettings } from "./conversationStorage";

export interface ModelChoice {
  id: string;
  provider: string;
  label: string;
}

interface Props {
  models: ModelChoice[];
  settings: UserSettings;
  selectedModelId: string;
  theme: Record<string, any>;
  onChange: (settings: UserSettings) => void;
  onSelectModel: (modelId: string) => void;
  onClearAll: () => Promise<void>;
  onClose: () => void;
}

const LANGUAGES: { value: AnswerLanguage; label: string }[] = [
  { value: "auto", label: "Same as my question" },
  { value: "en", label: "English" },
  { value: "hu", label: "Magyar" },
];

const SettingsPanel: React.FC<Props> = ({
  models,
  settings,
  selectedModelId,
  theme,
  onChange,
  onSelectModel,
  onClearAll,
  onClose,
}) => {
  const [cleared, setCleared] = useState(false);
  const section: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: theme.paddingXS,
    marginBottom: theme.paddingMD,
  };
  const label: React.CSSProperties = { fontWeight: 600, fontSize: theme.fontSizeSM };
  const hint: React.CSSProperties = { color: theme.colorTextSecondary, fontSize: theme.fontSizeSM };
  const favorites = new Set(settings.favoriteModels);

  const toggleFavorite = (id: string) => {
    const next = favorites.has(id)
      ? settings.favoriteModels.filter((m) => m !== id)
      : [...settings.favoriteModels, id];
    onChange({ ...settings, favoriteModels: next });
  };

  return (
    <div
      style={{
        flex: 1,
        overflowY: "auto",
        padding: theme.paddingMD,
        color: theme.colorText,
        fontSize: theme.fontSize,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", marginBottom: theme.paddingMD }}>
        <strong style={{ flex: 1 }}>Settings</strong>
        <button type="button" onClick={onClose}>Done</button>
      </div>

      <div style={section}>
        <span style={label}>Model to start with</span>
        <select value={selectedModelId} onChange={(e) => onSelectModel(e.target.value)}>
          {models.map((m) => (
            <option key={m.id} value={m.id}>{m.provider}/{m.label}</option>
          ))}
        </select>
      </div>

      <div style={section}>
        <span style={label}>Favourite models</span>
        <span style={hint}>Favourites are listed first in the model picker.</span>
        {models.map((m) => (
          <label key={m.id} style={{ display: "flex", gap: theme.paddingXS, alignItems: "center" }}>
            <input
              type="checkbox"
              checked={favorites.has(m.id)}
              onChange={() => toggleFavorite(m.id)}
            />
            <span>{m.provider}/{m.label}</span>
          </label>
        ))}
        <label style={{ display: "flex", gap: theme.paddingXS, alignItems: "center" }}>
          <input
            type="checkbox"
            checked={!settings.showAllModels}
            disabled={favorites.size === 0}
            onChange={(e) => onChange({ ...settings, showAllModels: !e.target.checked })}
          />
          <span>Show only my favourites in the picker</span>
        </label>
      </div>

      <div style={section}>
        <span style={label}>Answer language</span>
        <select
          value={settings.language}
          onChange={(e) => onChange({ ...settings, language: e.target.value as AnswerLanguage })}
        >
          {LANGUAGES.map((l) => (
            <option key={l.value} value={l.value}>{l.label}</option>
          ))}
        </select>
      </div>

      <div style={section}>
        <span style={label}>Conversation history</span>
        <span style={hint}>
          Conversations are saved per SQL Lab tab in Superset, for your user only.
        </span>
        <button
          type="button"
          disabled={cleared}
          onClick={async () => {
            if (window.confirm("Delete all your saved Vambery conversations?")) {
              await onClearAll();
              setCleared(true);
            }
          }}
        >
          {cleared ? "All conversations deleted" : "Delete all my conversations"}
        </button>
      </div>
    </div>
  );
};

export default SettingsPanel;
