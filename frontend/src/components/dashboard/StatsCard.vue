<template>
  <div class="bg-white rounded-lg shadow p-6">
    <div class="flex items-center">
      <div 
        class="flex-shrink-0 rounded-md p-3"
        :class="bgClass"
      >
        <slot name="icon"></slot>
      </div>
      <div class="ml-5 w-0 flex-1">
        <dl>
          <dt class="text-sm font-medium text-gray-500 truncate">
            {{ title }}
          </dt>
          <dd 
            class="text-lg font-semibold"
            :class="valueClass"
          >
            {{ value }}
            <small v-if="unit" class="text-[10px] ml-0.5">{{ unit }}</small>
          </dd>
          <dd v-if="$slots.subtext || subtext" class="text-xs text-gray-400">
            <slot name="subtext">{{ subtext }}</slot>
          </dd>
        </dl>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  title: string;
  value: string | number;
  type?: 'primary' | 'success' | 'warning' | 'danger' | 'info' | 'purple';
  unit?: string;
  subtext?: string;
  valueColor?: string; // Optional override for value color class
  bgColor?: string; // Optional override for icon bg color class
}>();

const bgClass = computed(() => {
  if (props.bgColor) return props.bgColor;
  
  switch (props.type) {
    case 'success': return 'bg-green-100 text-green-600';
    case 'warning': return 'bg-yellow-100 text-yellow-600';
    case 'danger': return 'bg-red-100 text-red-600';
    case 'info': return 'bg-blue-100 text-blue-600';
    case 'purple': return 'bg-purple-100 text-purple-600';
    default: return 'bg-blue-100 text-blue-600';
  }
});

const valueClass = computed(() => {
  if (props.valueColor) return props.valueColor;
  return 'text-gray-900';
});
</script>
