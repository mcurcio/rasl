import { rankCommands } from "@mcurcio/patchbay/composites";
import { describe as group, expect, it } from "vitest";

import type { NodeType } from "./api";
import {
  ADD_GROUP,
  ALIAS_GROUP,
  CHANGES_GROUP,
  type EditorActions,
  editorCommands,
  type EditorState,
  HELP_GROUP,
  shortcutLines,
  TYPE_GROUP,
  typeCommands,
  VIEW_GROUP,
} from "./palette";

const type = (name: string, aliases: string[], summary: string): NodeType => ({ name, aliases, summary, schema: null });

const TYPES = [
  type("ConsoleSink", ["ConsoleSinkNode"], "Logs frames to the console."),
  type("Crossfade", ["CrossfadeNode", "crossfade"], "Fades between two inputs."),
  type("cron", [], "Minute-granularity cron matcher."),
];

group("typeCommands", () => {
  it("lists each type under its name with its summary, then its other names", () => {
    const commands = typeCommands(TYPES, () => undefined);
    expect(commands.map((c) => [c.group, c.label, c.hint])).toEqual([
      [TYPE_GROUP, "ConsoleSink", "Logs frames to the console."],
      [TYPE_GROUP, "Crossfade", "Fades between two inputs."],
      [TYPE_GROUP, "cron", "Minute-granularity cron matcher."],
      [ALIAS_GROUP, "ConsoleSinkNode", "Another name for ConsoleSink"],
      [ALIAS_GROUP, "CrossfadeNode", "Another name for Crossfade"],
    ]);
    expect(new Set(commands.map((c) => c.id)).size).toBe(commands.length);
  });

  it("chooses the type itself from one of its other names", () => {
    const chosen: string[] = [];
    const commands = typeCommands(TYPES, (t) => chosen.push(t.name));
    commands.find((c) => c.label === "CrossfadeNode")?.run();
    expect(chosen).toEqual(["Crossfade"]);
  });

  it("finds a type by an alias the name alone does not match", () => {
    const ranked = rankCommands(
      typeCommands(TYPES, () => undefined),
      "consolesinknode",
    );
    expect(ranked.flatMap((g) => g.items.map((i) => i.command.label))).toEqual(["ConsoleSinkNode"]);
  });
});

const STATE: EditorState = {
  types: TYPES,
  editable: true,
  removable: false,
  queued: 0,
  busy: null,
  refused: false,
  sideOpen: true,
  theme: "system",
};

/** Actions that record the name of each one run. */
function recording(): { ran: string[]; actions: EditorActions } {
  const ran: string[] = [];
  const note = (name: string) => () => ran.push(name);
  return {
    ran,
    actions: {
      add: (t) => ran.push(`add ${t.name}`),
      remove: note("remove"),
      undo: note("undo"),
      check: note("check"),
      save: note("save"),
      discard: note("discard"),
      fit: note("fit"),
      toggleSide: note("toggleSide"),
      setTheme: (choice) => ran.push(`theme ${choice}`),
      shortcuts: note("shortcuts"),
    },
  };
}

group("editorCommands", () => {
  it("lists adding a node first, its types and other names in one group, then the changes, the view and help", () => {
    const commands = editorCommands(STATE, recording().actions);
    expect([...new Set(commands.map((c) => c.group))]).toEqual([ADD_GROUP, CHANGES_GROUP, VIEW_GROUP, HELP_GROUP]);
    expect(commands.filter((c) => c.group === ADD_GROUP).map((c) => c.label)).toEqual([
      "ConsoleSink",
      "Crossfade",
      "cron",
      "ConsoleSinkNode",
      "CrossfadeNode",
    ]);
    expect(commands.filter((c) => c.group !== ADD_GROUP).map((c) => [c.label, c.keys])).toEqual([
      ["Remove the selection", ["Delete", "Backspace"]],
      ["Drop the last change", "Mod+Z"],
      ["Check the changes", undefined],
      ["Save the changes", undefined],
      ["Discard the changes", undefined],
      ["Fit the view", "F"],
      ["Hide the side panel", undefined],
      ["Follow the system's theme", undefined],
      ["Light theme", undefined],
      ["Dark theme", undefined],
      ["Keyboard shortcuts", "?"],
    ]);
    expect(new Set(commands.map((c) => c.id)).size).toBe(commands.length);
  });

  it("lists no adding and no changes for a read-only graph", () => {
    const commands = editorCommands({ ...STATE, editable: false }, recording().actions);
    expect([...new Set(commands.map((c) => c.group))]).toEqual([VIEW_GROUP, HELP_GROUP]);
  });

  it("disables what cannot act now, as its button is", () => {
    const disabled = (state: Partial<EditorState>): string[] =>
      editorCommands({ ...STATE, ...state }, recording().actions)
        .filter((c) => c.disabled === true)
        .map((c) => c.id);
    expect(disabled({})).toEqual(["remove", "undo", "check", "save", "discard", "theme:system"]);
    expect(disabled({ removable: true, queued: 2, theme: "dark" })).toEqual(["theme:dark"]);
    expect(disabled({ queued: 2, refused: true, theme: "dark" })).toEqual(["remove", "save", "theme:dark"]);
    expect(disabled({ queued: 2, busy: "check", theme: "dark" })).toEqual([
      "remove",
      "check",
      "save",
      "discard",
      "theme:dark",
    ]);
  });

  it("runs the editor's actions", () => {
    const { ran, actions } = recording();
    const commands = editorCommands({ ...STATE, sideOpen: false }, actions);
    for (const label of ["CrossfadeNode", "Fit the view", "Show the side panel", "Dark theme", "Keyboard shortcuts"])
      commands.find((c) => c.label === label)?.run();
    expect(ran).toEqual(["add Crossfade", "fit", "toggleSide", "theme dark", "shortcuts"]);
  });
});

group("shortcutLines", () => {
  it("lists every key the editor binds, adding and the changes only while it can edit", () => {
    expect(shortcutLines(true).map((l) => l.keys)).toEqual(["Mod+K", "?", "A", ["Delete", "Backspace"], "Mod+Z", "F"]);
    expect(shortcutLines(false).map((l) => l.keys)).toEqual(["Mod+K", "?", "F"]);
  });
});
