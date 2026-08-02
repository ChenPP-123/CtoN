<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from './api'
import { visualForCity } from './content/cityVisuals'
import ProfileChart from './components/ProfileChart.vue'
import RouteMap from './components/RouteMap.vue'
import WeatherPanel from './components/WeatherPanel.vue'

const route = ref(null)
const profile = ref(null)
const weather = ref(null)
const selectedCityId = ref(1)
const previousCityId = ref(null)
const activeMetric = ref('temperature')
const loading = ref(true)
const refreshing = ref(false)
const traveling = ref(false)
const error = ref('')
const heroImageFailed = ref(false)
const metrics = [['temperature', '温度'], ['humidity', '湿度'], ['aqi', 'AQI'], ['wind_speed', '风速']]
const selectedCity = computed(() => route.value?.stations.find((station) => station.city_id === selectedCityId.value))
const visual = computed(() => visualForCity(selectedCity.value?.city_name, weather.value?.weather?.text, weather.value?.date))
const themeStyle = computed(() => ({ '--theme-primary': visual.value.primary, '--theme-accent': visual.value.accent, '--hero-overlay': visual.value.overlay, '--hero-fallback': visual.value.gradient }))

async function selectCity(cityId) {
  if (cityId === selectedCityId.value && weather.value) return
  previousCityId.value = selectedCityId.value
  selectedCityId.value = cityId
  weather.value = null
  heroImageFailed.value = false
  try {
    weather.value = await api.getWeather(cityId)
  } catch (exception) {
    error.value = exception.message
  }
}

async function randomTravel() {
  const choices = route.value.stations.filter((station) => station.city_id !== selectedCityId.value)
  const destination = choices[Math.floor(Math.random() * choices.length)]
  traveling.value = true
  await selectCity(destination.city_id)
  traveling.value = false
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [routeData, profileData] = await Promise.all([api.getRoute(1), api.getProfile(1)])
    route.value = routeData
    profile.value = profileData
    await selectCity(selectedCityId.value)
  } catch (exception) {
    error.value = exception.message
  } finally {
    loading.value = false
  }
}

async function refresh() {
  refreshing.value = true
  error.value = ''
  try {
    await api.refreshWeather()
    await load()
  } catch (exception) {
    error.value = exception.message
  } finally {
    refreshing.value = false
  }
}

function useFallbackImage(event) {
  if (!heroImageFailed.value && event.target.src !== new URL(visual.value.fallbackImage, window.location.origin).href) {
    heroImageFailed.value = true
    event.target.src = visual.value.fallbackImage
    return
  }
  event.target.hidden = true
}

onMounted(load)
</script>

<template>
  <main class="app-shell" :style="themeStyle">
    <div v-if="error && !route" class="error-state"><p>{{ error }}</p><button @click="load">重新加载</button></div>
    <template v-else-if="!loading && route && profile">
      <section id="top" class="city-stage">
        <section class="hero" :key="selectedCityId" :style="{ background: visual.gradient }" aria-live="polite">
          <img class="hero-image" :src="visual.image" :alt="`${selectedCity?.city_name}当地天气景象`" @error="useFallbackImage">
          <div class="hero-wash"></div>
          <div class="hero-copy" :class="`tone-${visual.textTone}`">
            <p class="eyebrow">第 {{ String(selectedCity?.station_order || 1).padStart(2, '0') }} 站 · {{ weather?.date || '读取观测中' }}</p>
            <h1>{{ selectedCity?.city_name }}</h1>
            <p class="city-phrase">{{ visual.phrase }}</p>
            <p v-if="weather?.poem" class="hero-poem">{{ weather.poem.content }}</p>
            <p v-else class="hero-poem placeholder">正在等候这座城市的诗句…</p>
          </div>
        </section>
        <header class="site-header">
          <a class="brand" href="#top">Cto<span>N</span></a>
          <p>重庆北 → 南京南 · 沿线气象观测</p>
          <button class="refresh-button" :disabled="refreshing" @click="refresh">{{ refreshing ? '更新中…' : '更新观测' }}</button>
        </header>
        <aside class="map-dock">
          <RouteMap :stations="route.stations" :geometry="route.geometry" :selected-city-id="selectedCityId" :previous-city-id="previousCityId" :theme-color="visual.primary" @select="selectCity" />
          <button class="random-button" :disabled="traveling" @click="randomTravel"><span class="travel-mark" aria-hidden="true">⌁</span>{{ traveling ? `前往 ${selectedCity?.city_name}…` : '随机旅行' }} <b aria-hidden="true">›</b></button>
        </aside>
        <section class="observatory" aria-label="当前城市气象观测台">
          <WeatherPanel :weather-data="weather" :city="weather?.city" />
          <div class="profile-area">
            <div class="profile-heading"><div><p class="eyebrow">ROUTE OBSERVATORY</p><h2>沿线观测剖面</h2></div><p>从重庆北站起算的真实距离</p></div>
            <div class="metric-tabs" role="tablist" aria-label="观测指标"><button v-for="[key, label] in metrics" :key="key" :class="{ active: activeMetric === key }" role="tab" :aria-selected="activeMetric === key" @click="activeMetric = key">{{ label }}</button></div>
            <ProfileChart :points="profile.points" :selected-city-id="selectedCityId" :metric="activeMetric" :theme-color="visual.primary" />
          </div>
        </section>
        <p v-if="error" class="inline-error">{{ error }} <button @click="selectCity(selectedCityId)">重试</button></p>
      </section>
    </template>
    <div v-else class="loading-state">正在读取沿线观测…</div>
  </main>
</template>
