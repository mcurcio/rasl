// The queued edits (owner, 2026-11-16: changes are saved on purpose, not as they are made):
// each can be dropped; Check shows the diff and whether the result builds; Save writes it.
import type { ReactElement } from "react";

import type { Edit, EditOutcome } from "../api";
import { describe } from "../model";

export type PendingPanelProps = {
  readonly edits: readonly Edit[];
  readonly outcome: EditOutcome | null;
  /** The files the last Save wrote, until the next change is queued. */
  readonly saved: readonly string[];
  readonly busy: boolean;
  readonly stale: boolean;
  readonly onDrop: (index: number) => void;
  readonly onCheck: () => void;
  readonly onSave: () => void;
  readonly onDiscard: () => void;
};

function basename(path: string): string {
  return path.split("/").pop() ?? path;
}

function Diff({ text }: { readonly text: string }): ReactElement {
  return (
    <pre className="diff">
      {text.split("\n").map((line, i) => (
        <div
          key={i}
          className={
            line.startsWith("+") && !line.startsWith("+++")
              ? "add"
              : line.startsWith("-") && !line.startsWith("---")
                ? "del"
                : line.startsWith("@@")
                  ? "hunk"
                  : undefined
          }
        >
          {line || " "}
        </div>
      ))}
    </pre>
  );
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
    <div className="pending">
      <div className="section-title">
        Changes <span className="muted">({edits.length} queued)</span>
      </div>
      {stale ? <p className="warning">The files changed on disk. Check again before saving.</p> : null}
      {edits.length === 0 ? (
        <p className="muted small">
          Wire ports, add or remove nodes: changes queue here and are written to the config only when you save.
        </p>
      ) : (
        <ol className="edit-list">
          {edits.map((edit, i) => (
            <li key={i} className={outcome?.refused?.index === i ? "refused" : undefined}>
              <span className="mono">{describe(edit)}</span>
              <button className="icon-button" title="Drop this change" onClick={() => onDrop(i)}>
                ×
              </button>
            </li>
          ))}
        </ol>
      )}
      <div className="actions">
        <button className="button" disabled={busy || edits.length === 0} onClick={onCheck}>
          Check
        </button>
        <button
          className="button primary"
          disabled={busy || edits.length === 0 || outcome?.ok === false}
          onClick={onSave}
        >
          Save
        </button>
        <button className="button" disabled={busy || edits.length === 0} onClick={onDiscard}>
          Discard
        </button>
      </div>
      {outcome?.refused ? (
        <p className="field-error">
          Change {outcome.refused.index + 1}: {outcome.refused.message}
        </p>
      ) : null}
      {outcome?.conflict ? <p className="warning">{outcome.conflict}</p> : null}
      {outcome?.error ? <pre className="problem">{outcome.error.formatted}</pre> : null}
      {saved.length > 0 ? (
        <p className="ok">Saved {saved.map(basename).join(", ")}; the running graph reloads it.</p>
      ) : null}
      {outcome?.changes.map((change) => (
        <details key={change.path} open>
          <summary className="mono small" title={change.path}>
            {basename(change.path)}
          </summary>
          <Diff text={change.diff} />
        </details>
      ))}
    </div>
  );
}
