// electron/lib/crash-recovery.js
'use strict';

/**
 * A render-process-gone reason counts as a crash unless it is a clean exit.
 * Handles the raw string; does not enumerate a closed set (Electron's reason
 * set may grow). Missing/empty reason is treated as a crash.
 */
function isCrashReason(reason) {
  return reason !== 'clean-exit';
}

/**
 * Sliding-window reload loop-guard. onCrash(now) returns 'reload' while the
 * number of reloads inside the last `windowMs` is below `maxReloads`, else
 * 'error-ui'. Timestamps outside the window are pruned each call. reset()
 * clears history (call after a load has been STABLE for a while).
 *
 * `now` is supplied by the caller (typically `Date.now()`). A monotonic source
 * is preferable but not required: clock jumps only degrade the best-effort
 * guard slightly (early trip / extra reload), never throw, and a bad/NaN `now`
 * self-corrects on the next call (the stale stamp is pruned).
 */
class ReloadLoopGuard {
  constructor(maxReloads = 3, windowMs = 30000) {
    this.maxReloads = maxReloads;
    this.windowMs = windowMs;
    this._stamps = [];
  }
  onCrash(now) {
    this._stamps = this._stamps.filter((t) => now - t < this.windowMs);
    if (this._stamps.length >= this.maxReloads) return 'error-ui';
    this._stamps.push(now);
    return 'reload';
  }
  reset() {
    this._stamps = [];
  }
}

module.exports = { isCrashReason, ReloadLoopGuard };
