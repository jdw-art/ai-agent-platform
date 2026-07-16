<template>
  <div class="bg-white rounded-lg shadow p-6">
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-lg font-medium text-gray-900">近 24 小时请求趋势</h2>
    </div>
    <div class="h-80 w-full">
      <v-chart class="h-full w-full" :option="chartOption" autoresize />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { LineChart } from "echarts/charts";
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
} from "echarts/components";

use([
  CanvasRenderer,
  LineChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
]);

const props = defineProps<{
  trends: Array<any>;
}>();

const chartOption = computed(() => {
  if (!props.trends) return {};
  
  return {
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(255, 255, 255, 0.9)",
      borderWidth: 1,
      borderColor: "#e5e7eb",
      textStyle: { color: "#374151" },
    },
    legend: {
      data: ["总请求量", "成功请求量"],
      bottom: 0,
      icon: "circle",
    },
    grid: {
      left: "3%",
      right: "4%",
      bottom: "12%",
      top: "10%",
      containLabel: true,
    },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: props.trends.map((item: any) => item.hour),
      axisLine: { lineStyle: { color: "#9ca3af" } },
      axisTick: { show: false },
    },
    yAxis: {
      type: "value",
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { type: "dashed", color: "#f3f4f6" } },
    },
    series: [
      {
        name: "总请求量",
        type: "line",
        smooth: true,
        showSymbol: false,
        data: props.trends.map((item: any) => item.total_calls),
        itemStyle: { color: "#3b82f6" },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(59, 130, 246, 0.2)" },
              { offset: 1, color: "rgba(59, 130, 246, 0)" },
            ],
          },
        },
      },
      {
        name: "成功请求量",
        type: "line",
        smooth: true,
        showSymbol: false,
        data: props.trends.map((item: any) => item.success_calls),
        itemStyle: { color: "#10b981" },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(16, 185, 129, 0.2)" },
              { offset: 1, color: "rgba(16, 185, 129, 0)" },
            ],
          },
        },
      },
    ],
  };
});
</script>
