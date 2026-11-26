// The add-node palette's commands: one per node type, and one per other name a type is registered under, since
// patchbay's CommandPalette matches the label only. Each runs `choose` with the type itself.
import type { Command } from "@mcurcio/patchbay/composites";

import type { NodeType } from "./api";

/** The palette's groups: the types by their names first, then the names they are also known by. */
export const TYPE_GROUP = "Node types";
export const ALIAS_GROUP = "Other names";

/**
 * The commands for the node types: each type under its name with its summary as the hint, then each alias that is not
 * the name in another case (the palette's matching ignores case already) with the type it names as the hint.
 */
export function typeCommands(types: readonly NodeType[], choose: (type: NodeType) => void): Command[] {
  const named: Command[] = types.map((type) => ({
    id: `type:${type.name}`,
    label: type.name,
    group: TYPE_GROUP,
    hint: type.summary,
    run: () => choose(type),
  }));
  const aliases: Command[] = types.flatMap((type) =>
    type.aliases
      .filter((alias) => alias.toLowerCase() !== type.name.toLowerCase())
      .map((alias) => ({
        id: `alias:${alias}`,
        label: alias,
        group: ALIAS_GROUP,
        hint: `Another name for ${type.name}`,
        run: () => choose(type),
      })),
  );
  return [...named, ...aliases];
}
