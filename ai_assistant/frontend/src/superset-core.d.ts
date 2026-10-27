/**
 * Type declarations for @apache-superset/core
 *
 * This module is provided at runtime via Module Federation (window.superset).
 * These declarations provide TypeScript type safety during compilation.
 */

declare module "@apache-superset/core" {
  // Core types
  export namespace common {
    interface Disposable {
      dispose(): void;
    }

    /** Subscribe to an event; dispose the result to unsubscribe. */
    type Event<T> = (listener: (e: T) => void) => Disposable;
  }

  // Chat API (SIP-214 — core.chat contribution).
  // Present from Superset 6.2 onwards; feature-detect before use.
  export namespace chat {
    interface Chat {
      id: string;
      name: string;
      description?: string;
    }

    type DisplayMode = "floating" | "panel";

    function registerChat(
      chat: Chat,
      trigger: React.ComponentType,
      panel: React.ComponentType,
    ): common.Disposable;

    function getChat(): Chat | undefined;
    function open(): void;
    function close(): void;
    function isOpen(): boolean;
    function getDisplayMode(): DisplayMode;
    function setDisplayMode(displayMode: DisplayMode): void;

    const onDidOpen: common.Event<void>;
    const onDidClose: common.Event<void>;
    const onDidChangeDisplayMode: common.Event<DisplayMode>;
    const onDidResizePanel: common.Event<{ width: number }>;
  }

  // Navigation API — present from Superset 6.2 onwards; feature-detect before use.
  export namespace navigation {
    type Page =
      | "dashboard"
      | "dashboard_list"
      | "explore"
      | "chart_list"
      | "sqllab"
      | "query_history"
      | "saved_queries"
      | "dataset"
      | "dataset_list"
      | "home";

    function getPage(): Page;
    const onDidChangePage: common.Event<Page>;
  }

  // Commands (7.0): registered actions that menus and toolbars invoke
  export namespace commands {
    interface Command {
      id: string;
      title: string;
      icon?: string;
      description?: string;
    }

    function registerCommand(
      command: Command,
      callback: (...args: unknown[]) => unknown,
    ): common.Disposable;
    function executeCommand<T = unknown>(command: string, ...args: unknown[]): Promise<T>;
  }

  // Menus (7.0): place commands in host toolbars, e.g. "sqllab.editor"
  export namespace menus {
    interface MenuItem {
      view: string;
      command: string;
      description?: string;
    }

    function registerMenuItem(
      item: MenuItem,
      location: string,
      group: "primary" | "secondary" | "context",
    ): common.Disposable;
  }

  // SQL Lab API (7.0)
  export namespace sqlLab {
    interface Position {
      /** zero-based */
      line: number;
      column: number;
    }

    interface EditorAnnotation {
      /** zero-based */
      line: number;
      column?: number;
      message: string;
      severity: "error" | "warning" | "info";
    }

    interface Editor {
      getValue(): string;
      setValue(value: string): void;
      getSelectedText(): string;
      insertText(text: string): void;
      focus(): void;
      scrollToLine(line: number): void;
      setAnnotations(annotations: EditorAnnotation[]): void;
      clearAnnotations(): void;
    }

    interface Tab {
      id: string;
      title: string;
      databaseId: number;
      catalog: string | null;
      schema: string | null;
      getEditor(): Promise<Editor>;
    }

    interface Panel {
      id: string;
    }

    interface QueryContext {
      clientId: string;
      tab: Tab;
    }

    interface QueryErrorResultContext extends QueryContext {
      errorMessage: string;
      executedSql: string | null;
    }

    interface CreateTabOptions {
      sql?: string;
      title?: string;
      databaseId?: number;
      catalog?: string | null;
      schema?: string | null;
    }

    function getCurrentTab(): Tab | undefined;
    function getTabs(): Tab[];
    function getDatabases(): { id: number; database_name: string }[];
    function createTab(options?: CreateTabOptions): Promise<Tab>;
    function executeQuery(options?: {
      sql?: string;
      selectedOnly?: boolean;
      limit?: number;
    }): Promise<string>;
    const onDidQueryFail: common.Event<QueryErrorResultContext>;
    const onDidQuerySuccess: common.Event<QueryContext>;
  }

  // Authentication API
  export namespace authentication {
    function getCSRFToken(): Promise<string | undefined>;
  }

  // Extensions API (Storage API — merged in apache/superset#39171)
  export namespace extensions {
    // JSON-serializable value (matches @apache-superset/core/storage JsonValue)
    type JsonValue =
      | string
      | number
      | boolean
      | null
      | JsonValue[]
      | { [key: string]: JsonValue };

    // Base accessor for local/session (no .shared — browser storage is per-device)
    interface StorageAccessor {
      get<T = JsonValue>(key: string): Promise<T | null>;
      set<T = JsonValue>(key: string, value: T): Promise<void>;
      remove(key: string): Promise<void>;
    }

    interface EphemeralSetOptions {
      ttl: number;
      codec?: string;
      isBinary?: boolean;
    }

    interface PersistentSetOptions {
      encrypt?: boolean;
      codec?: string;
      isBinary?: boolean;
    }

    interface PersistentListOptions {
      page: number;
      pageSize: number;
      resourceType?: string;
      resourceUuid?: string;
    }

    interface PersistentListEntry<T = JsonValue> {
      key: string;
      value: T | null;
      codec: string;
      isBinary: boolean;
    }

    interface PersistentListResult<T = JsonValue> {
      entries: PersistentListEntry<T>[];
      count: number;
    }

    interface EphemeralStorageAccessor {
      get<T = JsonValue>(key: string): Promise<T | null>;
      set<T = JsonValue>(key: string, value: T, options: EphemeralSetOptions): Promise<void>;
      remove(key: string): Promise<void>;
    }

    interface EphemeralStorageTier extends EphemeralStorageAccessor {
      shared: EphemeralStorageAccessor;
    }

    interface PersistentStorageAccessor {
      get<T = JsonValue>(key: string): Promise<T | null>;
      set<T = JsonValue>(key: string, value: T, options?: PersistentSetOptions): Promise<void>;
      list<T = JsonValue>(options: PersistentListOptions): Promise<PersistentListResult<T>>;
      remove(key: string): Promise<void>;
    }

    interface PersistentStorageTier extends PersistentStorageAccessor {
      shared: PersistentStorageAccessor;
    }

    interface ExtensionStorage {
      local: StorageAccessor;
      session: StorageAccessor;
      ephemeral: EphemeralStorageTier;
      persistent: PersistentStorageTier;
    }

    interface ExtensionContext {
      storage: ExtensionStorage;
    }

    function getContext(): ExtensionContext;
  }

  // Theme API (from @apache-superset/core/theme via Emotion)
  export namespace theme {
    interface SupersetTheme {
      // Colors - primary
      colorPrimary: string;
      colorPrimaryBg: string;
      colorPrimaryBgHover: string;
      colorPrimaryText: string;
      colorPrimaryTextHover: string;
      colorPrimaryBorder: string;

      // Colors - semantic
      colorError: string;
      colorErrorBg: string;
      colorErrorBorder: string;
      colorSuccess: string;
      colorSuccessBg: string;
      colorWarning: string;
      colorInfo: string;

      // Colors - text
      colorText: string;
      colorTextBase: string;
      colorTextSecondary: string;
      colorTextTertiary: string;
      colorTextPlaceholder: string;
      colorTextHeading: string;
      colorTextLabel: string;

      // Colors - background
      colorBgBase: string;
      colorBgContainer: string;
      colorBgElevated: string;
      colorBgLayout: string;

      // Colors - border
      colorBorder: string;
      colorBorderSecondary: string;
      colorSplit: string;

      // Colors - fill
      colorFill: string;
      colorFillSecondary: string;
      colorFillTertiary: string;
      colorFillQuaternary: string;

      // Colors - other
      colorLink: string;
      colorIcon: string;
      colorIconHover: string;

      // Typography
      fontFamily: string;
      fontFamilyCode: string;
      fontSize: number;
      fontSizeSM: number;
      fontSizeLG: number;
      fontSizeXL: number;
      fontWeightStrong: number;
      lineHeight: number;

      // Spacing
      sizeUnit: number;
      sizeXS: number;
      sizeSM: number;
      size: number;
      sizeLG: number;
      padding: number;
      paddingXS: number;
      paddingSM: number;
      paddingLG: number;
      margin: number;
      marginXS: number;
      marginSM: number;

      // Shape
      borderRadius: number;
      borderRadiusSM: number;
      borderRadiusLG: number;

      // Control
      controlHeight: number;
      controlHeightSM: number;

      [key: string]: unknown;
    }

    function useTheme(): SupersetTheme;
  }
}
