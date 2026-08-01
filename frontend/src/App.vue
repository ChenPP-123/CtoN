<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from './api'
import ProfileChart from './components/ProfileChart.vue'
import RouteMap from './components/RouteMap.vue'
import WeatherPanel from './components/WeatherPanel.vue'

const route = ref(null)
const profile = ref(null)
const weather = ref(null)
const selectedCityId = ref(1)
const activeMetric = ref('temperature')
const loading = ref(true)
const refreshing = ref(false)
const generatingPoem = ref(false)
const poem = ref('')
const poemCityId = ref(null)
const poemError = ref('')
const error = ref('')
const metrics = [['temperature', '温度'], ['humidity', '湿度'], ['aqi', 'AQI'], ['wind_speed', '风速']]
const selectedCity = computed(() => route.value?.stations.find((station) => station.city_id === selectedCityId.value))
let poemRequestVersion = 0

async function selectCity(cityId) {
  poemRequestVersion += 1
  selectedCityId.value = cityId
  poem.value = ''
  poemCityId.value = null
  poemError.value = ''
  generatingPoem.value = false
  try {
    weather.value = await api.getWeather(cityId)
    if (selectedCityId.value === cityId) void generatePoem(cityId)
  } catch (exception) { error.value = exception.message }
}

async function generatePoem(cityId) {
  const requestVersion = ++poemRequestVersion
  generatingPoem.value = true
  poemError.value = ''
  try {
    const result = await api.generatePoem(cityId)
    if (requestVersion !== poemRequestVersion || selectedCityId.value !== cityId) return
    poem.value = result.poem
    poemCityId.value = result.city_id
  } catch (exception) {
    if (requestVersion === poemRequestVersion && selectedCityId.value === cityId) poemError.value = exception.message
  } finally {
    if (requestVersion === poemRequestVersion) generatingPoem.value = false
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [routeData, profileData] = await Promise.all([api.getRoute(1), api.getProfile(1)])
    route.value = routeData
    profile.value = profileData
    await selectCity(selectedCityId.value)
  } catch (exception) { error.value = exception.message } finally { loading.value = false }
}

async function refresh() {
  refreshing.value = true
  error.value = ''
  try {
    await api.refreshWeather()
    await load()
  } catch (exception) { error.value = exception.message } finally { refreshing.value = false }
}

onMounted(load)
</script>

<template>
  <main class="app-shell">
    <header class="site-header"><a class="brand" href="#top">Cto<span>N</span></a><p>CHONGQING TO NANJING · 气象旅行观测站</p><button class="refresh-button" :disabled="refreshing" @click="refresh">{{ refreshing ? '更新中…' : '更新观测' }}</button></header>
    <div v-if="error" class="error-state"><p>{{ error }}</p><button @click="load">重新加载</button></div>
    <template v-else-if="!loading && route && profile">
      <section id="top" class="intro"><div><p class="eyebrow">沿线气象空间变化</p><h1>一趟 1200 公里的<br><em>天气列车</em></h1></div><p class="intro-copy">从巴山湿雾出发，穿过江城晴热，抵达金陵雨意。选择任一站点，读取这条高铁线上的当地观测。</p></section>
      <section class="dashboard"><RouteMap :stations="route.stations" :selected-city-id="selectedCityId" @select="selectCity" /><WeatherPanel :weather-data="weather" :city="weather?.city" /></section>
      <section class="poem-section" aria-live="polite"><div><p class="eyebrow">WEATHER VERSE</p><h2>把此刻写成一首诗</h2><p>以 {{ selectedCity?.city_name }} 当前观测为引，自动生成一段沿线旅途文字。</p></div><div class="poem-action"><p v-if="generatingPoem" class="poem-status">正在为 {{ selectedCity?.city_name }} 落笔…</p><p v-else-if="poemCityId === selectedCityId && poem" class="poem-text">{{ poem }}</p><p v-else-if="poemError" class="poem-error">{{ poemError }}</p><p v-else class="poem-placeholder">正在准备这座城市的气象意象。</p></div></section>
      <section class="profile-section"><div class="profile-heading"><div><p class="eyebrow">DISTANCE PROFILE</p><h2>沿线观测剖面</h2></div><p>横轴以距重庆北站的实际距离排列</p></div><div class="metric-tabs" role="tablist"><button v-for="[key, label] in metrics" :key="key" :class="{ active: activeMetric === key }" role="tab" :aria-selected="activeMetric === key" @click="activeMetric = key">{{ label }}</button></div><ProfileChart :points="profile.points" :selected-city-id="selectedCityId" :metric="activeMetric" /></section>
      <nav class="station-nav" aria-label="城市切换"><button v-for="station in route.stations" :key="station.city_id" :class="{ active: station.city_id === selectedCityId }" @click="selectCity(station.city_id)"><span>0{{ station.station_order }}</span>{{ station.city_name }}<small>{{ station.station_name }}</small></button></nav>
    </template>
    <div v-else class="loading-state">正在调度这趟气象列车<span>.</span><span>.</span><span>.</span></div>
  </main>
</template>
