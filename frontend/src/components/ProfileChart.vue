<script setup>
import * as echarts from 'echarts'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({ points: { type: Array, default: () => [] }, selectedCityId: { type: Number, default: 1 }, metric: { type: String, default: 'temperature' }, themeColor: { type: String, default: '#d97847' } })
const element = ref(null)
const chartError = ref(false)
let chart
let resizeObserver
const metrics = {
  temperature: { label: '温度', field: 'temperature_c', unit: '°C' },
  humidity: { label: '湿度', field: 'humidity_percent', unit: '%', color: '#6fd8ef' },
  aqi: { label: 'AQI', field: 'aqi', unit: '', color: '#ff8270' },
  wind_speed: { label: '风速', field: 'wind_speed_ms', unit: ' m/s', color: '#a79eff' },
}
const hasMetricData = computed(() => {
  const current = metrics[props.metric]
  return Boolean(current && props.points.some((point) => point[current.field] !== null && point[current.field] !== undefined))
})

function render() {
  if (!chart || !hasMetricData.value) return
  const current = metrics[props.metric]
  const color = props.metric === 'temperature' ? props.themeColor : current.color
  const data = props.points.map((point) => ({ value: point[current.field], selected: point.city_id === props.selectedCityId, name: point.city_name, distance: point.distance_from_origin_km }))
  try {
    chart.setOption({
      animationDuration: 350,
      grid: { left: 42, right: 20, top: 8, bottom: 54 },
      xAxis: {
        type: 'category',
        data: props.points.map((point) => point.city_name),
        axisLine: { lineStyle: { color: '#355467' } },
        axisLabel: {
          interval: 0,
          lineHeight: 13,
          formatter: (_value, index) => {
            const point = props.points[index]
            const cityStyle = point.city_id === props.selectedCityId ? 'activeCity' : 'city'
            return `{${cityStyle}|${point.city_name}}\n{distance|${point.distance_from_origin_km} km}`
          },
          rich: {
            city: { color: '#3f5962', fontSize: 9, fontWeight: 600 },
            activeCity: { color, fontSize: 9, fontWeight: 700 },
            distance: { color: '#566f76', fontSize: 6 },
          },
        },
      },
      yAxis: { type: 'value', axisLine: { show: false }, splitLine: { lineStyle: { color: 'rgba(53, 84, 103, .20)' } }, axisLabel: { color: '#405a62', fontSize: 9, formatter: `{value}${current.unit}` } },
      tooltip: { trigger: 'axis', valueFormatter: (value) => value === null ? '暂无数据' : `${value}${current.unit}` },
      series: [{ type: 'line', data, connectNulls: false, smooth: .25, symbolSize: (value, params) => params.data.selected ? 14 : 9, lineStyle: { color, width: 3 }, itemStyle: { color, borderColor: '#fff', borderWidth: 3 }, areaStyle: { color, opacity: .26 } }],
    }, true)
    chartError.value = false
  } catch {
    chartError.value = true
  }
}

function resizeChart() {
  if (!chart || !element.value) return
  const { width, height } = element.value.getBoundingClientRect()
  if (width <= 0 || height <= 0) return
  try {
    chart.resize()
    render()
  } catch {
    chartError.value = true
  }
}

watch(
  () => [props.points, props.selectedCityId, props.metric, props.themeColor],
  () => render(),
  { deep: true, flush: 'post' },
)

onMounted(async () => {
  await nextTick()
  try {
    chart = echarts.init(element.value, null, { renderer: 'svg' })
    resizeObserver = new ResizeObserver(resizeChart)
    resizeObserver.observe(element.value)
    window.addEventListener('resize', resizeChart)
    resizeChart()
  } catch {
    chartError.value = true
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  window.removeEventListener('resize', resizeChart)
  chart?.dispose()
})
</script>

<template>
  <div class="chart-frame">
    <div ref="element" class="chart" role="img" aria-label="沿线气象变化图"></div>
    <p v-if="chartError" class="chart-state" role="alert">剖面绘制失败，请刷新页面</p>
    <p v-else-if="!hasMetricData" class="chart-state">暂无该指标的沿线观测</p>
  </div>
</template>
