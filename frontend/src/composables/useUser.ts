import { ref, computed } from 'vue'

export function useUser() {
  const userInfoStr = localStorage.getItem('user_info')
  const userInfo = ref(userInfoStr ? JSON.parse(userInfoStr) : null)

  const isAdmin = computed(() => {
    return userInfo.value?.role === 'admin'
  })

  const hasPermission = (perm: string) => {
    if (isAdmin.value) return true
    const permissions = userInfo.value?.permissions
    if (Array.isArray(permissions)) {
      return permissions.includes(perm)
    }
    // Fallback for legacy nested object structure
    if (permissions && typeof permissions === 'object') {
      return (permissions as any).elements?.includes(perm) || false
    }
    return false
  }

  const refreshUser = () => {
    const freshStr = localStorage.getItem('user_info')
    userInfo.value = freshStr ? JSON.parse(freshStr) : null
  }

  return {
    userInfo,
    isAdmin,
    hasPermission,
    refreshUser
  }
}
