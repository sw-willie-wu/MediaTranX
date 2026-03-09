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
  has_nvidia_gpu: boolean
  cuda_toolkit_installed: boolean
  driver_version: string | null
  ram_total: number | null
  ram_available: number | null
  os_name: string
  os_version: string
  cpu_name: string
  cpu_count: number | null
}
