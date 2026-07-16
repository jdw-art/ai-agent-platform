import assert from "node:assert/strict";
import {
  createSseLineParser,
  mergeChartDefaults,
  parseChartOptions,
} from "../src/utils/chartRenderer.ts";

const parsed = parseChartOptions(`
{
  xAxis: { type: "category", data: ["A"] },
  yAxis: { type: "value" },
  series: [{ type: "bar", data: [1] }]
}
`);
assert.equal(parsed.ok, true);
if (parsed.ok) {
  assert.equal(parsed.option.series[0].type, "bar");
}

const echartsFencePattern = /(?:<thought>([\s\S]*?)<\/thought>)|(?:<chart>([\s\S]*?)<\/chart>)|(?:```\s*(?:chart|echarts|json)\s*([\s\S]*?)```)|(?:```\s*mermaid\s*([\s\S]*?)```)|(?::::analysis\s*([^\n]*)\n([\s\S]*?)\n:::)/gi;
const echartsFence = '```echarts\n{"series":[{"type":"bar","data":[1]}]}\n```';
const echartsMatch = echartsFencePattern.exec(echartsFence);
assert.equal(echartsMatch?.[3]?.includes('"series"'), true);

const executable = parseChartOptions(`
{
  series: [{
    type: "bar",
    data: [globalThis.__chartRendererExecuted = true]
  }]
}
`);
assert.equal(executable.ok, false);
assert.equal((globalThis as any).__chartRendererExecuted, undefined);

const pie = mergeChartDefaults({
  series: [{ type: "pie", data: [{ name: "A", value: 1 }] }],
});
assert.equal("xAxis" in pie, false);
assert.equal("yAxis" in pie, false);
assert.equal("grid" in pie, false);
assert.equal(pie.tooltip.trigger, "item");

const bar = mergeChartDefaults({
  xAxis: { data: ["A"] },
  series: [{ type: "bar", data: [1] }],
});
assert.equal("xAxis" in bar, true);
assert.equal("yAxis" in bar, true);
assert.equal("grid" in bar, true);

const parseSse = createSseLineParser();
assert.deepEqual(parseSse.feed("data: {\"content\":\"hel"), []);
assert.deepEqual(parseSse.feed("lo\"}\n\ndata: [DONE]\n"), [
  '{"content":"hello"}',
  "[DONE]",
]);
assert.deepEqual(parseSse.flush(), []);
