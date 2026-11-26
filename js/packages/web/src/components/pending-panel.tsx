// The queued edits (owner, 2026-11-16: changes are saved on purpose, not as they are made):
// each can be dropped; Check shows the diff and whether the result builds; Save writes it.
// A section of the side column's body under patchbay's SectionTitle, drawn on its Button and IconButton; its news
// (files changed on disk, a refused change, a conflict, the files saved) on Banner; the diff of what Save would write
// on DiffView, a section per file that folds.
import { Banner, DiffView } from "@mcurcio/patchbay/composites";
import { Button, IconButton, SectionTitle } from "@mcurcio/patchbay/primitives";
import type { ReactElement } from "react";

import type { Edit, EditOutcome } from "../api";
import { describe } from "../model";

export type PendingPanelProps = {
  readonly edits: readonly Edit[];
  readonly outcome: EditOutcome | null;
  /** The files the last Save wrote, until the next change is queued. */
  readonly saved: readonly string[];
  /** The request on its way, if any: its button shows a spinner, and the others wait. */
  readonly busy: "check" | "save" | null;
  readonly stale: boolean;
  readonly onDrop: (index: number) => void;
  readonly onCheck: () => void;
  readonly onSave: () => void;
  readonly onDiscard: () => void;
};

function basename(path: string): string {
  return path.split("/").pop() ?? path;
}

export function PendingPanel({
  edits,
  outcome,
  saved,
  busy,
  stale,
  onDrop,
  onCheck,
  onSave,
  onDiscard,
}: PendingPanelProps): ReactElement {
  return (
    <section className="pending" aria-label="Changes">
      <SectionTitle actions={<span className="muted small">{edits.length} queued</span>}>Changes</SectionTitle>
      {stale ? (
        <Banner className="pending-banner" tone="warn">
          The files changed on disk. Check again before saving.
        </Banner>
      ) : null}
      {edits.length === 0 ? (
        <p className="muted small">
          Wire ports, add or remove nodes: changes queue here and are written to the config only when you save.
        </p>
      ) : (
        <ol className="edit-list" aria-label="Queued changes">
          {edits.map((edit, i) => (
            <li key={i} className={outcome?.refused?.index === i ? "refused" : undefined}>
              <span className="mono">{describe(edit)}</span>
              <IconButton label="Drop this change" size="sm" onClick={() => onDrop(i)}>
                ×
              </IconButton>
            </li>
          ))}
        </ol>
      )}
      <div className="actions">
        <Button
          busy={busy === "check"}
          busyLabel="Checking"
          disabled={(busy !== null && busy !== "check") || edits.length === 0}
          onClick={onCheck}
        >
          Check
        </Button>
        <Button
          tone="primary"
          busy={busy === "save"}
          busyLabel="Saving"
          disabled={(busy !== null && busy !== "save") || edits.length === 0 || outcome?.ok === false}
          onClick={onSave}
        >
          Save
        </Button>
        <Button disabled={busy !== null || edits.length === 0} onClick={onDiscard}>
          Discard
        </Button>
      </div>
      {outcome?.refused ? (
        <Banner className="pending-banner" tone="err">
          Change {outcome.refused.index + 1}: {outcome.refused.message}
        </Banner>
      ) : null}
      {outcome?.conflict ? (
        <Banner className="pending-banner" tone="warn">
          {outcome.conflict}
        </Banner>
      ) : null}
      {outcome?.error ? (
        <pre className="problem" data-outcome="error">
          {outcome.error.formatted}
        </pre>
      ) : null}
      {saved.length > 0 ? (
        <Banner className="pending-banner" tone="ok">
          Saved {saved.map(basename).join(", ")}; the running graph reloads it.
        </Banner>
      ) : null}
      {outcome && outcome.changes.length > 0 ? (
        <DiffView role="region" aria-label="What Save writes" files={outcome.changes} />
      ) : null}
    </section>
  );
}
