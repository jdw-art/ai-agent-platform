<template>
  <div
    v-if="errors?.length > 0"
    class="bg-white rounded-xl shadow-sm border border-red-100 overflow-hidden"
  >
    <div
      class="px-6 py-4 border-b border-red-50 bg-red-50/20 flex items-center justify-between"
    >
      <h3 class="text-sm font-bold text-red-900 flex items-center">
        <svg
          class="w-4 h-4 mr-2 text-red-500"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
        智能体异常链路 (Recent Tool Errors)
      </h3>
      <span class="text-[10px] text-red-400 font-mono">Top 5 Failures</span>
    </div>
    <div class="overflow-x-auto">
      <table class="min-w-full divide-y divide-gray-100">
        <thead class="bg-gray-50">
          <tr>
            <th
              class="px-6 py-3 text-left text-[10px] font-bold text-gray-400 uppercase tracking-widest"
            >
              时间
            </th>
            <th
              class="px-6 py-3 text-left text-[10px] font-bold text-gray-400 uppercase tracking-widest"
            >
              工具
            </th>
            <th
              class="px-6 py-3 text-left text-[10px] font-bold text-gray-400 uppercase tracking-widest"
            >
              错误详情
            </th>
            <th
              class="px-6 py-3 text-right text-[10px] font-bold text-gray-400 uppercase tracking-widest"
            >
              操作
            </th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-100 bg-white">
          <tr
            v-for="err in errors"
            :key="err.trace_id"
            class="hover:bg-red-50/30 transition-colors"
          >
            <td class="px-6 py-4 whitespace-nowrap text-xs text-gray-500">
              {{ formatDate(err.time) }}
            </td>
            <td
              class="px-6 py-4 whitespace-nowrap text-xs font-mono font-bold text-amber-700 bg-amber-50 px-2 py-0.5 rounded-md inline-block mt-3 ml-6"
            >
              {{ err.tool }}
            </td>
            <td
              class="px-6 py-4 text-xs text-gray-600 max-w-md truncate"
              :title="err.message"
            >
              {{ err.message }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-right text-xs">
              <button
                @click="$emit('view-trace', err.trace_id)"
                class="text-blue-600 font-bold hover:text-blue-800 transition-colors underline decoration-dotted underline-offset-4"
              >
                回溯详情
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { formatDate } from '../../utils/date';

defineProps<{
  errors: Array<any>;
}>();

defineEmits<{
  (e: 'view-trace', traceId: string): void;
}>();
</script>
