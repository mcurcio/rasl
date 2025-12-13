# DDP Diagnostics: family_room.conf

## Summary

A 2-minute diagnostic capture was run with `ddp_frame_diag` instrumentation enabled.

- The DDP sink consistently produced **`count=2284` elements** and **`channels=3`**.
- The outgoing payload size was consistently **`bytes=6852`** (= `2284 * 3`).
- No frames were flagged as **`suspicious=true`**.
- No `ddp_send_error` or `ddp_send_slow` events were observed in the filtered capture.

## Option B (bad data / abrupt aberrations)

From `docs/ddp_diag_run.txt`:

- **Non-finite values**: `non_finite=0` throughout
- **Out-of-range float values**: `below0=0`, `above1=0` throughout
- **All/mostly-white frames**: `white_ratio=0.0` throughout
- **Abrupt frame deltas**: `delta_mean` stayed in the ~5–6 range in the sampled lines; nothing resembling a “large swath jump” or an all-white blast

Based on these diagnostics, there is no evidence that RASL is generating NaNs/Infs, out-of-range values, or all-white frames.

## Option C (timing / jitter / drops)

The capture does show scheduler jitter events for the `leds` sink:

- `tick_late` and `frame_interval_jitter` events occurred (examples include ~61ms, ~83–89ms, and a larger ~130ms interval).
- `slow_tick_trace` indicates the `leds` node accounted for most of the slow tick time in at least one instance (the trace shows ~86ms attributed to `leds`).

This supports the hypothesis that the receiver/controller could be reacting to **irregular frame delivery / jitter** rather than bad pixel values.

## Notes

- `repeat_until` is now effective in the runtime (it previously wasn’t being applied because implicit repeats were only triggered when `repeat > 1`).
- The diagnostics file captured by the runner is: `docs/ddp_diag_run.txt`.
