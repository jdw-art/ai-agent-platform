import axios from '../utils/axios'
import type { StandardResponse, ListResponse } from './common'

export interface User {
  id: number
  user_name: string
  real_name?: string
  role: string
  dept_code?: string
  org_path?: string
  is_active: boolean
}

export interface Role {
  id: number
  code: string
  name: string
  description?: string
  user_count: number
}

export const portalApi = {
  // Roles
  getRoles: (params?: { search?: string, page?: number, size?: number }) => 
    axios.get<StandardResponse<ListResponse<Role>>>('/api/portal/roles', { params }),
  
  // Users
  getUsers: (params?: { search?: string, page?: number, size?: number }) => 
    axios.get<StandardResponse<ListResponse<User>>>('/api/portal/management/users', { params }),

  // SSO Users (if needed for selection)
  getSsoUsers: (params?: { search?: string, page?: number, size?: number }) => 
    axios.get<StandardResponse<ListResponse<User>>>('/api/portal/management/sso-users', { params })
}
