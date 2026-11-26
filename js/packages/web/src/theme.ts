// The page's theme choice (system, light or dark), kept in localStorage under rasl's own key by patchbay's useTheme.
// index.html inlines patchbay's themeScript for the same key, so a kept choice applies before the first paint
// (theme.test.ts holds the two equal).
export const THEME_KEY = "rasl-web/1/theme";
