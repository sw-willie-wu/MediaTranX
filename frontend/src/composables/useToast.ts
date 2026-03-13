/**
 * 全域 toast 通知管理
 */
import { reactive } from 'vue'

export type ToastType = 'info' | 'success' | 'error'

export interface ToastAction {
  label: string
  callback: () => void
}

export interface Toast {
  id: number
  message: string
  type: ToastType
  icon?: string
  action?: ToastAction
}

export interface ToastOptions {
  type?: ToastType
  icon?: string
  duration?: number
  action?: ToastAction
}

const toasts = reactive<Toast[]>([])
let nextId = 0

function show(message: string, options: ToastOptions = {}) {
  const { type = 'info', icon, duration = 5000, action } = options

  const id = nextId++
  const toast: Toast = { id, message, type, icon, action }
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
