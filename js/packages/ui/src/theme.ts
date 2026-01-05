/**
 * UI theme configuration.
 */

/**
 * Theme interface for UI styling.
 */
export interface ITheme {
  colors: {
    background: string;
    surface: string;
    primary: string;
    secondary: string;
    accent: string;
    text: string;
    textMuted: string;
    border: string;
    error: string;
    warning: string;
    success: string;
  };
  fonts: {
    body: string;
    mono: string;
  };
  spacing: {
    xs: string;
    sm: string;
    md: string;
    lg: string;
    xl: string;
  };
  borderRadius: {
    sm: string;
    md: string;
    lg: string;
  };
}

/**
 * Default dark theme.
 */
export const defaultTheme: ITheme = {
  colors: {
    background: "#0a0a0a",
    surface: "#1a1a1a",
    primary: "#3b82f6",
    secondary: "#6366f1",
    accent: "#8b5cf6",
    text: "#f5f5f5",
    textMuted: "#a3a3a3",
    border: "#2a2a2a",
    error: "#ef4444",
    warning: "#f59e0b",
    success: "#22c55e",
  },
  fonts: {
    body: "system-ui, -apple-system, sans-serif",
    mono: "ui-monospace, SFMono-Regular, Menlo, monospace",
  },
  spacing: {
    xs: "0.25rem",
    sm: "0.5rem",
    md: "1rem",
    lg: "1.5rem",
    xl: "2rem",
  },
  borderRadius: {
    sm: "0.25rem",
    md: "0.5rem",
    lg: "1rem",
  },
};
