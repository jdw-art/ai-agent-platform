import axios from '../utils/axios'
import type { StandardResponse, ListResponse } from './common'

export interface AgentTask {
  id: number
  name: string
  agent_id: string
  conversation_id: string
  user_id: number
  creator_name?: string
  agent_name?: string
  source: 'web' | 'agent'
  cron_expr: string
  prompt: string
  status: number // 0-Stopped, 1-Running, 2-Error
  run_count: number
  config?: any
  last_run_id?: string
  last_run_at?: string
  next_run_at?: string
  created_at: string
  updated_at: string
}

export interface TaskLog {
  id: number
  trace_id: string
  query: string
  summary?: string
  status: string
  execution_time_ms: number
  created_at: string
}

export const taskApi = {
  list: () => axios.get<StandardResponse<AgentTask[]>>('/api/v1/tasks/'),
  get: (id: number) => axios.get<StandardResponse<AgentTask>>(`/api/v1/tasks/${id}`),
  create: (data: any) => axios.post<StandardResponse<AgentTask>>('/api/v1/tasks/', data),
  update: (id: number, data: any) => axios.patch<StandardResponse<AgentTask>>(`/api/v1/tasks/${id}`, data),
  delete: (id: number) => axios.delete<StandardResponse<any>>(`/api/v1/tasks/${id}`),
  run: (id: number) => axios.post<StandardResponse<any>>(`/api/v1/tasks/${id}/run`),
  logs: (id: number, params: { page?: number, page_size?: number }) => 
    axios.get<StandardResponse<ListResponse<TaskLog>>>(`/api/v1/tasks/${id}/logs`, { params })
}
