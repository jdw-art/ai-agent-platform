<template>
  <div class="bg-white rounded-lg shadow">
    <div class="px-6 py-4 border-b border-gray-200">
      <h3 class="text-lg font-medium text-gray-900">{{ title || '最近调用' }}</h3>
    </div>
    <div class="p-6">
      <!-- Detailed Mode (User) -->
      <div v-if="mode === 'detailed'">
        <div v-if="calls?.length > 0" class="space-y-3">
          <div
            v-for="call in calls"
            :key="call.id"
            class="flex items-center justify-between py-2 border-b border-gray-100 last:border-0"
          >
            <div class="flex items-center flex-1 min-w-0">
              <span
                class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium mr-3"
                :class="{
                  'bg-green-100 text-green-800':
                    call.status_code >= 200 && call.status_code < 300,
                  'bg-yellow-100 text-yellow-800':
                    call.status_code >= 300 && call.status_code < 400,
                  'bg-red-100 text-red-800': call.status_code >= 400,
                }"
              >
                {{ call.status_code }}
              </span>
              <span
                class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800 font-mono mr-3"
              >
                {{ call.method }}
              </span>
              <span
                class="text-sm text-gray-600 font-mono flex-1 truncate"
                :title="call.endpoint"
              >
                {{ call.endpoint }}
              </span>
            </div>
            <div class="flex items-center space-x-4 ml-4 flex-shrink-0">
              <span class="text-sm text-gray-500"
                >{{ call.process_time_ms?.toFixed(2) }} ms</span
              >
              <span class="text-xs text-gray-400">{{
                formatDate(call.created_at)
              }}</span>
            </div>
          </div>
        </div>
        <div v-else class="text-center py-12 text-gray-500">
          <svg
            class="mx-auto h-12 w-12 text-gray-300 mb-3"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
          <p class="text-sm">暂无调用记录</p>
          <p class="text-xs text-gray-400 mt-1">
            开始使用 API 后，这里会显示最近的调用记录
          </p>
        </div>
      </div>

      <!-- Compact Mode (Admin) -->
      <div v-else>
        <div v-if="calls?.length > 0" class="space-y-3">
          <div
            v-for="call in calls.slice(0, 5)"
            :key="call.id"
            class="flex items-center text-sm"
          >
            <span
              class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium mr-2"
              :class="{
                'bg-green-100 text-green-800':
                  call.status_code >= 200 && call.status_code < 300,
                'bg-red-100 text-red-800': call.status_code >= 400,
              }"
            >
              {{ call.status_code }}
            </span>
            <span
              class="text-gray-600 font-mono text-xs flex-1 truncate"
              :title="call.endpoint"
            >
              {{ call.endpoint }}
            </span>
            <span class="text-xs text-gray-400 ml-2">
              {{ formatDate(call.created_at) }}
            </span>
          </div>
        </div>
        <div v-else class="text-center py-8 text-gray-500">
          <p>暂无数据</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { formatDate } from '../../utils/date';

defineProps<{
  title?: string;
  calls: Array<any>;
  mode?: 'compact' | 'detailed';
}>();
</script>
