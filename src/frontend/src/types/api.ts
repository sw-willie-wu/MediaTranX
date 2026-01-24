/**
 * API 回應類型定義
 */

export interface ApiResponse<T = unknown> {
  data: T
  status: number
  message?: string
}

export interface ApiError {
  error: string
  detail?: string
  code?: string
}

export interface DeviceInfo {
  device: 'cuda' | 'mps' | 'cpu'
  compute_type: string
  device_name: string
  memory_total: number | null
  memory_free: number | null
}
