"""Watch the config files and apply their changes to the running scheduler.

``watch_config`` checks the files a config was loaded from (the root and every
file it includes) a few times a second. When one changes it reloads the config
off the event loop, so ticks keep their timing, and hands the resulting plan
update to the scheduler, which swaps it in at the next tick boundary.

A reload that fails (a syntax error, an unknown node type, a bad connection) is
reported and changes nothing: the graph keeps running as it was until the files
are valid again.
"""

from __future__ import annotations

import os
import sys

import anyio
import anyio.to_thread
import structlog

from rasl.config.reload import ConfigSession
from rasl.runtime.unified import UnifiedScheduler

logger = structlog.get_logger()

Stamps = dict[str, tuple[int, int] | None]


def _stamps(paths: tuple[str, ...]) -> Stamps:
    """Each file's modification time and size, or None for a file that is gone."""
    stamps: Stamps = {}
    for path in paths:
        try:
            status = os.stat(path)
        except OSError:
            stamps[path] = None
        else:
            stamps[path] = (status.st_mtime_ns, status.st_size)
    return stamps


async def watch_config(
    session: ConfigSession,
    scheduler: UnifiedScheduler,
    *,
    interval: float = 0.5,
) -> None:
    """Reload the config whenever its files change, until cancelled.

    Args:
        session: The config as loaded; it is reloaded in place.
        scheduler: The running scheduler, which receives each plan update.
        interval: Seconds between checks. A change is acted on once the files
            have stayed the same for one interval, so a save in progress or
            several files saved together make one reload.
    """
    seen = _stamps(session.watched)
    while True:
        await anyio.sleep(interval)
        now = _stamps(session.watched)
        if now == seen:
            continue

        # Let the writer finish: wait until nothing changes for one interval
        while True:
            await anyio.sleep(interval)
            again = _stamps(session.watched)
            if again == now:
                break
            now = again

        logger.info("config_changed", path=str(session.path))
        update = None
        try:
            update = await anyio.to_thread.run_sync(session.reload)
        except Exception as e:
            logger.error("config_reload_failed", path=str(session.path))
            print(f"Config reload failed; the graph keeps running as it was.\n{e}", file=sys.stderr)
        else:
            if update is None:
                logger.info("config_reloaded", changes=0)

        # What the reload read is as it was before the reload started (``now``), so
        # a save that landed while it ran is still seen as a change. The reload may
        # have read files not watched until now (a new include, broken or not).
        fresh = _stamps(session.watched)
        seen = {path: now.get(path, stamp) for path, stamp in fresh.items()}

        if update is None:
            continue

        for ignored in update.ignored:
            logger.warning("config_change_needs_restart", change=ignored)
        logger.info("config_reloaded", changes=len(update.changes), detail=list(update.changes))
        if update.changes_graph:
            applied = scheduler.request_update(update)
            await applied.wait()
            if scheduler.plan is not update.plan:
                # The scheduler refused it and said why (plan_update_failed)
                print("Config reload failed; the graph keeps running as it was.", file=sys.stderr)
                continue
        session.commit(update)
