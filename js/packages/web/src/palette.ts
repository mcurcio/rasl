// The editor's commands and keys. Mod+K opens the whole palette (patchbay's CommandPalette), adding a node first;
// A, the Add node button, a double-click on empty canvas and a dropped wire open adding alone. Each node type is a
// command, and so is each other name a type is registered under, since the palette matches the label only.
import type { Command, ShortcutLine } from "@mcurcio/patchbay/composites";
import type { ThemeChoice } from "@mcurcio/patchbay/hooks";

import type { NodeType } from "./api";

/** The adding palette's groups: the types by their names first, then the names they are also known by. */
export const TYPE_GROUP = "Node types";
export const ALIAS_GROUP = "Other names";

/** The whole palette's groups, in the order it lists them: adding a node first (types, then other names). */
export const ADD_GROUP = "Add a node";
export const CHANGES_GROUP = "Changes";
export const VIEW_GROUP = "View";
export const HELP_GROUP = "Help";

/** The editor's keys (patchbay ux-rules U18). Mod is ⌘ on Apple platforms and Ctrl elsewhere. */
export const KEYS = {
  palette: "Mod+K",
  add: "A",
  fit: "F",
  shortcuts: "?",
  remove: ["Delete", "Backspace"],
  undo: "Mod+Z",
} as const;

/**
 * The commands for the node types: each type under its name with its summary as the hint, then each alias that is not
 * the name in another case (the palette's matching ignores case already) with the type it names as the hint. The whole
 * palette lists both under one group, `ADD_GROUP`.
 */
export function typeCommands(
  types: readonly NodeType[],
  choose: (type: NodeType) => void,
  groups: { readonly types: string; readonly aliases: string } = { types: TYPE_GROUP, aliases: ALIAS_GROUP },
): Command[] {
  const named: Command[] = types.map((type) => ({
    id: `type:${type.name}`,
    label: type.name,
    group: groups.types,
    hint: type.summary,
    run: () => choose(type),
  }));
  const aliases: Command[] = types.flatMap((type) =>
    type.aliases
      .filter((alias) => alias.toLowerCase() !== type.name.toLowerCase())
      .map((alias) => ({
        id: `alias:${alias}`,
        label: alias,
        group: groups.aliases,
        hint: `Another name for ${type.name}`,
        run: () => choose(type),
      })),
  );
  return [...named, ...aliases];
}

/** What the whole palette needs of the editor: its state now, and the actions its commands run. */
export type EditorState = {
  readonly types: readonly NodeType[];
  /** Whether the graph can be edited: a read-only graph has no adding and no changes commands. */
  readonly editable: boolean;
  /** Whether the selection is one that Delete would queue removing. */
  readonly removable: boolean;
  /** How many changes are queued. */
  readonly queued: number;
  readonly busy: "check" | "save" | null;
  /** Whether the last check refused the queue, so it cannot be saved. */
  readonly refused: boolean;
  readonly sideOpen: boolean;
  readonly theme: ThemeChoice;
};

export type EditorActions = {
  readonly add: (type: NodeType) => void;
  readonly remove: () => void;
  readonly undo: () => void;
  readonly check: () => void;
  readonly save: () => void;
  readonly discard: () => void;
  readonly fit: () => void;
  readonly toggleSide: () => void;
  readonly setTheme: (choice: ThemeChoice) => void;
  readonly shortcuts: () => void;
};

const THEMES: readonly { readonly choice: ThemeChoice; readonly label: string }[] = [
  { choice: "system", label: "Follow the system's theme" },
  { choice: "light", label: "Light theme" },
  { choice: "dark", label: "Dark theme" },
];

/**
 * The whole palette's commands, the editor's existing actions only: adding a node (each type and other name), then
 * the changes (remove the selection, drop the last change, check, save, discard), the view (fit, the side panel, the
 * theme) and the shortcut sheet. A command that cannot act now is listed disabled, as the button it stands for is; a
 * read-only graph lists no adding and no changes.
 */
export function editorCommands(state: EditorState, actions: EditorActions): Command[] {
  const edit: Command[] = state.editable
    ? [
        ...typeCommands(state.types, actions.add, { types: ADD_GROUP, aliases: ADD_GROUP }),
        {
          id: "remove",
          label: "Remove the selection",
          group: CHANGES_GROUP,
          keys: KEYS.remove,
          run: actions.remove,
          disabled: !state.removable,
        },
        {
          id: "undo",
          label: "Drop the last change",
          group: CHANGES_GROUP,
          keys: KEYS.undo,
          run: actions.undo,
          disabled: state.queued === 0,
        },
        {
          id: "check",
          label: "Check the changes",
          group: CHANGES_GROUP,
          hint: "Whether the queued changes build",
          run: actions.check,
          disabled: state.busy !== null || state.queued === 0,
        },
        {
          id: "save",
          label: "Save the changes",
          group: CHANGES_GROUP,
          hint: "Write the queued changes to the config files",
          run: actions.save,
          disabled: state.busy !== null || state.queued === 0 || state.refused,
        },
        {
          id: "discard",
          label: "Discard the changes",
          group: CHANGES_GROUP,
          hint: "Drop every queued change",
          run: actions.discard,
          disabled: state.busy !== null || state.queued === 0,
        },
      ]
    : [];
  return [
    ...edit,
    { id: "fit", label: "Fit the view", group: VIEW_GROUP, keys: KEYS.fit, run: actions.fit },
    {
      id: "side",
      label: state.sideOpen ? "Hide the side panel" : "Show the side panel",
      group: VIEW_GROUP,
      run: actions.toggleSide,
    },
    ...THEMES.map(({ choice, label }) => ({
      id: `theme:${choice}`,
      label,
      group: VIEW_GROUP,
      hint: state.theme === choice ? "The theme now" : undefined,
      run: () => actions.setTheme(choice),
      disabled: state.theme === choice,
    })),
    { id: "shortcuts", label: "Keyboard shortcuts", group: HELP_GROUP, keys: KEYS.shortcuts, run: actions.shortcuts },
  ];
}

/** The shortcut sheet's lines: the keys the editor binds (app.tsx), adding and the changes only while it can edit. */
export function shortcutLines(editable: boolean): ShortcutLine[] {
  return [
    { keys: KEYS.palette, label: "Open the command palette", group: "General" },
    { keys: KEYS.shortcuts, label: "Show the keyboard shortcuts", group: "General" },
    ...(editable
      ? [
          { keys: KEYS.add, label: "Add a node", group: "Editing" },
          { keys: KEYS.remove, label: "Remove the selection", group: "Editing" },
          { keys: KEYS.undo, label: "Drop the last change", group: "Editing" },
        ]
      : []),
    { keys: KEYS.fit, label: "Fit the view", group: "View" },
  ];
}
