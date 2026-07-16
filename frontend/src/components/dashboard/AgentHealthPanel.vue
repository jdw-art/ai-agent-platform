<template>
  <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
    <div
      class="lg:col-span-2 bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden"
    >
      <div
        class="px-6 py-4 border-b border-gray-50 flex items-center justify-between bg-blue-50/30"
      >
        <h3 class="text-sm font-bold text-blue-900 flex items-center">
          <svg
            class="w-4 h-4 mr-2"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M13 10V3L4 14h7v7l9-11h-7z"
            />
          </svg>
          智能体运行健康度 (Agent Health)
        </h3>
        <span
          class="text-[10px] text-blue-400 font-mono uppercase tracking-widest"
          >Real-time Analytics</span
        >
      </div>
      <div class="p-6 grid grid-cols-1 md:grid-cols-2 gap-8">
        <!-- Pie Chart -->
        <div class="space-y-4">
          <p
            class="text-xs font-semibold text-gray-400 uppercase tracking-wider text-center"
          >
            工具调用分布
          </p>
          <div class="h-48 relative">
            <v-chart
              v-if="agentStats?.tool_usage?.length > 0"
              :option="toolPieOption"
              autoresize
            />
            <div
              v-else
              class="absolute inset-0 flex items-center justify-center text-gray-300 text-xs"
            >
              暂无调用数据
            </div>
          </div>
        </div>
        <!-- Line Chart -->
        <div class="space-y-4">
          <p
            class="text-xs font-semibold text-gray-400 uppercase tracking-wider text-center"
          >
            执行耗时趋势 (24h)
          </p>
          <div class="h-48 relative">
            <v-chart
              v-if="agentStats?.performance_trend?.length > 0"
              :option="latencyTrendOption"
              autoresize
            />
            <div
              v-else
              class="absolute inset-0 flex items-center justify-center text-gray-300 text-xs"
            >
              暂无趋势数据
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Key Metrics Side Panel -->
    <div
      class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 space-y-6"
    >
      <div class="flex items-center justify-between">
        <span
          class="text-xs font-bold text-gray-400 uppercase tracking-widest"
          >核心指标</span
        >
        <span
          class="px-2 py-0.5 bg-green-100 text-green-700 text-[10px] rounded-full font-bold"
          >LIVE</span
        >
      </div>
      <div class="space-y-4">
        <div
          class="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
        >
          <span class="text-xs text-gray-500">工具成功率</span>
          <span class="text-lg font-bold text-gray-900"
            >{{ agentStats?.health_stats?.success_rate || 0 }}%</span
          >
        </div>
        <div
          class="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
        >
          <span class="text-xs text-gray-500">平均执行耗时</span>
          <span class="text-lg font-bold text-amber-600"
            >{{ agentStats?.health_stats?.avg_latency || 0
            }}<small class="text-[10px] ml-0.5">ms</small></span
          >
        </div>
        <div
          class="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
        >
          <span class="text-xs text-gray-500">总工具调用</span>
          <span class="text-lg font-bold text-gray-900">{{
            agentStats?.health_stats?.total_tool_calls || 0
          }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import VChart from "vue-echarts";
// Note: ECharts modules are assumed to be registered in the parent or a global plugin.
// If not, we should import and register them here too. 
// For safety, let's assume the parent registers them, but we might want to move registration here if we want true isolation.
// Since Overview.vue already has them, we rely on that for now, or we can duplicate imports.
// Duplicating imports is safer for refactoring.

import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { PieChart, LineChart } from "echarts/charts";
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
} from "echarts/components";

use([
  CanvasRenderer,
  PieChart,
  LineChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
]);

const props = defineProps<{
  agentStats: any;
}>();

const toolPieOption = computed(() => {
  if (!props.agentStats?.tool_usage) return {};
  return {
    tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
    legend: {
      orient: "vertical",
      left: "left",
      top: "center",
      textStyle: { fontSize: 10 },
    },
    series: [
      {
        name: "工具占比",
        type: "pie",
        radius: ["40%", "70%"],
        center: ["60%", "50%"],
        avoidLabelOverlap: false,
        itemStyle: { borderRadius: 8, borderColor: "#fff", borderWidth: 2 },
        label: { show: false },
        emphasis: { label: { show: true, fontSize: 12, fontWeight: "bold" } },
        data: props.agentStats.tool_usage,
      },
    ],
  };
});

const latencyTrendOption = computed(() => {
  if (!props.agentStats?.performance_trend) return {};
  return {
    tooltip: { trigger: "axis", backgroundColor: "rgba(255, 255, 255, 0.9)" },
    grid: { left: "3%", right: "4%", bottom: "3%", containLabel: true },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: props.agentStats.performance_trend.map((i: any) => i.hour),
      axisLine: { lineStyle: { color: "#e5e7eb" } },
    },
    yAxis: {
      type: "value",
      name: "ms",
      splitLine: { lineStyle: { type: "dashed" } },
    },
    series: [
      {
        name: "平均耗时",
        type: "line",
        smooth: true,
        showSymbol: false,
        data: props.agentStats.performance_trend.map((i: any) => i.avg_ms),
        itemStyle: { color: "#f59e0b" },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(245, 158, 11, 0.2)" },
              { offset: 1, color: "rgba(245, 158, 11, 0)" },
            ],
          },
        },
      },
    ],
  };
});
</script>
