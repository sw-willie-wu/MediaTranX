// electron/lib/splash-progress.js
'use strict';

/**
 * Asymptotic ease-out percent for the backend-wait phase.
 * p(t) = start + (ceiling - start) * (1 - exp(-t / tauMs)), strictly < ceiling.
 */
function creepPercent(elapsedMs, start = 90, ceiling = 99, tauMs = 12000) {
  const span = ceiling - start;
  const eased = span * (1 - Math.exp(-Math.max(0, elapsedMs) / tauMs));
  return Math.min(start + eased, ceiling - 1e-6);
}

/** Whole elapsed seconds (floored). */
function formatElapsedSeconds(elapsedMs) {
  return Math.floor(Math.max(0, elapsedMs) / 1000);
}

/** Has the wait crossed the reassurance threshold? */
function isLongWait(elapsedMs, thresholdMs = 8000) {
  return elapsedMs >= thresholdMs;
}

module.exports = { creepPercent, formatElapsedSeconds, isLongWait };
