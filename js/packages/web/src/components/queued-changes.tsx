// The queued changes (owner, 2026-11-16: changes are saved on purpose, not as they are made): patchbay's ChangeList,
// one row per queued edit with its change Badge, its words and a Drop button, the change a check refused marked in
// words, and Check, Save and Discard in its head. The queue keeps only the net change (model.ts queue()). Its news
// (files changed on disk, a conflict, the files saved) is on Banner; the diff of what Save would write on DiffView, a
// section per file that folds. A section of the side column's body under patchbay's SectionTitle.
import { Banner, ChangeList, DiffView } from "@mcurcio/patchbay/composites";
import { Button, SectionTitle } from "@mcurcio/patchbay/primitives";
import type { ReactElement } from "react";

import type { Edit, EditOutcome } from "../api";
import { changeOf } from "../model";

export type QueuedChangesProps = {
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

/** The queue's count, as ChangeList's status line says it. */
const count = (n: number): string =>
  n === 0 ? "No changes queued" : n === 1 ? "1 change queued" : `${n} changes queued`;

export function QueuedChanges({
  edits,
  outcome,
  saved,
  busy,
  stale,
  onDrop,
  onCheck,
  onSave,
  onDiscard,
}: QueuedChangesProps): ReactElement {
  const changes = edits.map((edit, i) => {
    const words = changeOf(edit);
    return {
      // Each row's id is its place in the queue, which is what dropping it takes
      id: String(i),
      change: words.change,
      label: <span className="mono">{words.label}</span>,
      detail: <span className="mono">{words.detail}</span>,
      refused: outcome?.refused?.index === i ? outcome.refused.message : undefined,
    };
  });
  return (
    <div className="queued">
      <SectionTitle>Changes</SectionTitle>
      {stale ? (
        <Banner className="queued-banner" tone="warn">
          The files changed on disk. Check again before saving.
        </Banner>
      ) : null}
      <ChangeList
        className="queued-list"
        aria-label="Queued changes"
        changes={changes}
        onDrop={(id) => onDrop(Number(id))}
        labels={{ count }}
        actions={
          <>
            <Button
              size="sm"
              busy={busy === "check"}
              busyLabel="Checking"
              disabled={(busy !== null && busy !== "check") || edits.length === 0}
              onClick={onCheck}
            >
              Check
            </Button>
            <Button
              size="sm"
              tone="primary"
              busy={busy === "save"}
              busyLabel="Saving"
              disabled={(busy !== null && busy !== "save") || edits.length === 0 || outcome?.ok === false}
              onClick={onSave}
            >
              Save
            </Button>
            <Button size="sm" disabled={busy !== null || edits.length === 0} onClick={onDiscard}>
              Discard
            </Button>
          </>
        }
      />
      {edits.length === 0 ? (
        <p className="muted small">
          Wire ports, add or remove nodes: changes queue here and are written to the config only when you save.
        </p>
      ) : null}
      {outcome?.conflict ? (
        <Banner className="queued-banner" tone="warn">
          {outcome.conflict}
        </Banner>
      ) : null}
      {outcome?.error ? (
        <pre className="problem" data-outcome="error">
          {outcome.error.formatted}
        </pre>
      ) : null}
      {saved.length > 0 ? (
        <Banner className="queued-banner" tone="ok">
          Saved {saved.map(basename).join(", ")}; the running graph reloads it.
        </Banner>
      ) : null}
      {outcome && outcome.changes.length > 0 ? (
        <DiffView role="region" aria-label="What Save writes" files={outcome.changes} />
      ) : null}
    </div>
  );
}
