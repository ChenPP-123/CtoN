<script setup>
import * as echarts from 'echarts'
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({ points: { type: Array, default: () => [] }, selectedCityId: { type: Number, default: 1 }, metric: { type: String, default: 'temperature' }, themeColor: { type: String, default: '#d97847' } })
const element = ref(null)
let chart
const metrics = {
  temperature: { label: '温度', field: 'temperature_c', unit: '°C' },
  humidity: { label: '湿度', field: 'humidity_percent', unit: '%', color: '#6fd8ef' },
  aqi: { label: 'AQI', field: 'aqi', unit: '', color: '#ff8270' },
  wind_speed: { label: '风速', field: 'wind_speed_ms', unit: ' m/s', color: '#a79eff' },
}

function render() {
  if (!element.value) return
  chart ??= echarts.init(element.value)
  const current = metrics[props.metric]
  const color = props.metric === 'temperature' ? props.themeColor : current.color
  const data = props.points.map((point) => ({ value: point[current.field], selected: point.city_id === props.selectedCityId, name: point.city_name, distance: point.distance_from_origin_km }))
  chart.setOption({
    animationDuration: 350,
    grid: { left: 42, right: 20, top: 8, bottom: 34 },
    xAxis: {
      type: 'category',
      data: props.points.map((point) => point.city_name),
      axisLine: { lineStyle: { color: '#355467' } },
      axisLabel: {
        lineHeight: 17,
        formatter: (_value, index) => {
          const point = props.points[index]
          const cityStyle = point.city_id === props.selectedCityId ? 'activeCity' : 'city'
          return `{${cityStyle}|${point.city_name}}\n{distance|${point.distance_from_origin_km} km}`
        },
        rich: {
          city: { color: '#3f5962', fontWeight: 600 },
          activeCity: { color, fontWeight: 700 },
          distance: { color: '#71878d', fontSize: 10 },
        },
      },
    },
    yAxis: { type: 'value', axisLine: { show: false }, splitLine: { lineStyle: { color: 'rgba(53, 84, 103, .16)' } }, axisLabel: { color: '#789099', formatter: `{value}${current.unit}` } },
    tooltip: { trigger: 'axis', valueFormatter: (value) => value === null ? '暂无数据' : `${value}${current.unit}` },
    series: [{ type: 'line', data, connectNulls: false, smooth: .25, symbolSize: (value, params) => params.data.selected ? 14 : 9, lineStyle: { color, width: 3 }, itemStyle: { color, borderColor: '#fff', borderWidth: 3 }, areaStyle: { color, opacity: .11 } }],
  }, true)
}

function resizeChart() {
  chart?.resize()
}

watch(() => [props.points, props.selectedCityId, props.metric, props.themeColor], async () => { await nextTick(); render() }, { deep: true })
watch(element, async () => { await nextTick(); render() })
window.addEventListener('resize', resizeChart)
onBeforeUnmount(() => { window.removeEventListener('resize', resizeChart); chart?.dispose() })
</script>

<template><div ref="element" class="chart" role="img" aria-label="沿线气象变化图"></div></template>
