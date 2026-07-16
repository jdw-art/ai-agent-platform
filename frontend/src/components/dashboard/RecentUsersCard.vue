<template>
  <div class="bg-white rounded-lg shadow">
    <div class="px-6 py-4 border-b border-gray-200">
      <h3 class="text-lg font-medium text-gray-900">最新用户</h3>
    </div>
    <div class="p-6">
      <div v-if="users?.length > 0" class="space-y-4">
        <div
          v-for="user in users"
          :key="user.user_name"
          class="flex items-center"
        >
          <div
            class="h-10 w-10 rounded-full bg-gray-200 flex items-center justify-center text-gray-600 font-bold"
          >
            {{ user.user_name.charAt(0).toUpperCase() }}
          </div>
          <div class="ml-4 flex-1">
            <p class="text-sm font-medium text-gray-900">
              {{ user.user_name }}
            </p>
            <p class="text-xs text-gray-500">
              {{ user.role === "admin" ? "管理员" : "普通用户" }}
            </p>
          </div>
          <div class="text-xs text-gray-400">
            {{ formatDate(user.created_at) }}
          </div>
        </div>
      </div>
      <div v-else class="text-center py-8 text-gray-500">
        <p>暂无数据</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { formatDate } from '../../utils/date';

defineProps<{
  users: Array<{
    user_name: string;
    role: string;
    created_at: string;
  }>;
}>();
</script>
