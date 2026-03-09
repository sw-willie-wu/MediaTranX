/**
 * 任務相關類型定義
 */

export type TaskStatus = 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled'

export interface Task {
  taskId: string
  taskType: string
  status: TaskStatus
  progress: number
  message: string | null
  result: unknown | null
  error: string | null
  createdAt: Date
  updatedAt: Date
  label?: string
  fileName?: string
}

export interface ProgressUpdate {
  task_id: string
  progress: number
  stage: string
  message: string
  timestamp: string
  result?: unknown
  error?: string
}

export interface TaskSubmitParams {
  type: string
  params: Record<string, unknown>
}
