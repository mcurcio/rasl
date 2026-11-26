import { rankCommands } from "@mcurcio/patchbay/composites";
import { describe as group, expect, it } from "vitest";

import type { NodeType } from "./api";
import { ALIAS_GROUP, TYPE_GROUP, typeCommands } from "./palette";

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
