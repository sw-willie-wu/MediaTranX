/**
 * 前端統一 Logger
 *
 * 用法：
 *   const log = createLogger('ModuleName')
 *   log.info('action description', { key: value })
 *   log.warn('something unexpected', error)
 *   log.error('failed to do X', error)
 *
 * 輸出格式：[ModuleName] message  {data}
 */

type LogData = unknown

function serialize(data: LogData[]): string {
  if (data.length === 0) return ''
  return ' ' + data.map((d) => {
    if (d instanceof Error) return d.message
    if (typeof d === 'object' && d !== null) {
      try { return JSON.stringify(d) } catch { return String(d) }
    }
    return String(d)
  }).join(' ')
}

function fmt(module: string, msg: string, data: LogData[]): string {
  return `[${module}] ${msg}${serialize(data)}`
}

export interface Logger {
  info(msg: string, ...data: LogData[]): void
  warn(msg: string, ...data: LogData[]): void
  error(msg: string, ...data: LogData[]): void
  debug(msg: string, ...data: LogData[]): void
}

export function createLogger(module: string): Logger {
  return {
    info: (msg, ...data) => console.info(fmt(module, msg, data)),
    warn: (msg, ...data) => console.warn(fmt(module, msg, data)),
    error: (msg, ...data) => console.error(fmt(module, msg, data)),
    debug: (msg, ...data) => console.debug(fmt(module, msg, data)),
  }
}
