/**
 * Type declarations for @apache-superset/core
 *
 * This module is provided at runtime via Module Federation (window.superset).
 * These declarations provide TypeScript type safety during compilation.
 */

declare module "@apache-superset/core" {
  // Core extension types
  export namespace core {
    interface Disposable {
      dispose(): void;
    }

    interface ExtensionContext {
      disposables: Disposable[];
    }

    function registerViewProvider(
      viewId: string,
      factory: () => React.ReactElement
    ): Disposable;
  }

  // SQL Lab API
  export namespace sqlLab {
    interface Editor {
      getValue(): string;
      setValue(value: string): void;
      getSelectedText(): string;
      insertText(text: string): void;
      focus(): void;
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

    function getCurrentTab(): Tab | undefined;
    function getTabs(): Tab[];
    function getDatabases(): { id: number; database_name: string }[];
    function executeQuery(options?: {
      sql?: string;
      limit?: number;
    }): Promise<string>;
  }

  // Authentication API
  export namespace authentication {
    function getCSRFToken(): Promise<string | undefined>;
  }

  // Theme API (from @apache-superset/core/ui via Emotion)
  export interface SupersetTheme {
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

  export function useTheme(): SupersetTheme;
}
