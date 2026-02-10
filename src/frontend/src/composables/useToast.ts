/**
 * 全域 toast 通知管理
 */
import { reactive } from 'vue'

export type ToastType = 'info' | 'success' | 'error'

export interface Toast {
  id: number
  message: string
  type: ToastType
  icon?: string
}

export interface ToastOptions {
  type?: ToastType
  icon?: string
  duration?: number
}

const toasts = reactive<Toast[]>([])
let nextId = 0

function show(message: string, options: ToastOptions = {}) {
  const { type = 'info', icon, duration = 5000 } = options

  const id = nextId++
  const toast: Toast = { id, message, type, icon }
  toasts.push(toast)

  if (duration > 0) {
    setTimeout(() => dismiss(id), duration)
  }

  return id
}

function dismiss(id: number) {
  const index = toasts.findIndex((t) => t.id === id)
  if (index !== -1) {
    toasts.splice(index, 1)
  }
}

export function useToast() {
  return {
    toasts,
    show,
    dismiss,
  }
}
