<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from './api'
import { visualForCity } from './content/cityVisuals'
import ProfileChart from './components/ProfileChart.vue'
import RouteMap from './components/RouteMap.vue'
import WeatherPanel from './components/WeatherPanel.vue'

const route = ref(null)
const profile = ref(null)
const weather = ref(null)
const travelAdvice = ref(null)
const selectedCityId = ref(null)
const trainDestinationCityId = ref(null)
const autoplayEnabled = ref(true)
const activeMetric = ref('temperature')
const loading = ref(true)
const refreshing = ref(false)
const refreshStage = ref('')
const adviceRefreshing = ref(false)
const adviceError = ref('')
const traveling = ref(false)
const error = ref('')
const heroImageFailed = ref(false)
const AUTOPLAY_CYCLE_MS = 10_000
const TRAIN_MOVE_MS = 1_200
const metrics = [['temperature', '温度'], ['humidity', '湿度'], ['aqi', 'AQI'], ['wind_speed', '风速']]
const selectedCity = computed(() => route.value?.stations.find((station) => station.city_id === selectedCityId.value))
const visual = computed(() => visualForCity(selectedCity.value?.city_name, weather.value?.weather?.text, weather.value?.date))
const themeStyle = computed(() => ({ '--theme-primary': visual.value.primary, '--theme-accent': visual.value.accent, '--hero-overlay': visual.value.overlay, '--hero-fallback': visual.value.gradient }))
const refreshLabel = computed(() => refreshStage.value === 'weather' ? '更新天气…' : refreshStage.value === 'advice' ? '生成建议…' : '更新观测')
let departureTimer
let arrivalTimer
let weatherRequestId = 0

function clearRoutePlayback() {
  window.clearTimeout(departureTimer)
  window.clearTimeout(arrivalTimer)
  departureTimer = undefined
  arrivalTimer = undefined
  trainDestinationCityId.value = null
}

function nextStation() {
  const stations = route.value?.stations || []
  const currentIndex = stations.findIndex((station) => station.city_id === selectedCityId.value)
  if (currentIndex < 0 || stations.length < 2) return null
  return stations[(currentIndex + 1) % stations.length]
}

function scheduleRoutePlayback() {
  clearRoutePlayback()
  if (!autoplayEnabled.value || document.hidden) return
  const destination = nextStation()
  if (!destination) return

  departureTimer = window.setTimeout(() => {
    trainDestinationCityId.value = destination.city_id
  }, AUTOPLAY_CYCLE_MS - TRAIN_MOVE_MS)
  arrivalTimer = window.setTimeout(() => {
    selectCity(destination.city_id)
  }, AUTOPLAY_CYCLE_MS)
}

async function selectCity(cityId, { restartPlayback = true } = {}) {
  const destination = route.value?.stations.find((station) => station.city_id === cityId)
  if (!destination) return

  const cityChanged = cityId !== selectedCityId.value
  error.value = ''
  if (cityChanged) {
    selectedCityId.value = cityId
    weather.value = null
    heroImageFailed.value = false
  }
  if (restartPlayback) scheduleRoutePlayback()
  if (!cityChanged && weather.value) return

  const requestId = ++weatherRequestId
  try {
    const weatherData = await api.getWeather(cityId)
    if (requestId === weatherRequestId && selectedCityId.value === cityId) weather.value = weatherData
  } catch (exception) {
    if (requestId === weatherRequestId && selectedCityId.value === cityId) error.value = exception.message
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
    const [routeData, profileData, adviceData] = await Promise.all([
      api.getRoute(1),
      api.getProfile(1),
      api.getTravelAdvice(1).catch((exception) => { adviceError.value = exception.message; return null }),
    ])
    route.value = routeData
    profile.value = profileData
    travelAdvice.value = adviceData
    selectedCityId.value = routeData.stations[0]?.city_id ?? null
    if (selectedCityId.value !== null) await selectCity(selectedCityId.value, { restartPlayback: false })
  } catch (exception) {
    error.value = exception.message
  } finally {
    loading.value = false
    scheduleRoutePlayback()
  }
}

async function refresh() {
  clearRoutePlayback()
  refreshing.value = true
  refreshStage.value = 'weather'
  error.value = ''
  adviceError.value = ''
  try {
    await api.refreshWeather()
    const refreshCityId = selectedCityId.value
    const requestId = ++weatherRequestId
    const [profileData, weatherData] = await Promise.all([api.getProfile(1), api.getWeather(refreshCityId)])
    profile.value = profileData
    if (requestId === weatherRequestId && selectedCityId.value === refreshCityId) weather.value = weatherData
    refreshStage.value = 'advice'
    adviceRefreshing.value = true
    try {
      travelAdvice.value = await api.generateTravelAdvice(1)
    } catch (exception) {
      adviceError.value = exception.message
    } finally {
      adviceRefreshing.value = false
    }
  } catch (exception) {
    error.value = exception.message
  } finally {
    refreshing.value = false
    refreshStage.value = ''
    scheduleRoutePlayback()
  }
}

function toggleAutoplay() {
  autoplayEnabled.value = !autoplayEnabled.value
  if (autoplayEnabled.value) scheduleRoutePlayback()
  else clearRoutePlayback()
}

function handleVisibilityChange() {
  if (document.hidden) clearRoutePlayback()
  else if (autoplayEnabled.value) scheduleRoutePlayback()
}

function useFallbackImage(event) {
  if (!heroImageFailed.value && event.target.src !== new URL(visual.value.fallbackImage, window.location.origin).href) {
    heroImageFailed.value = true
    event.target.src = visual.value.fallbackImage
    return
  }
  event.target.hidden = true
}

onMounted(() => {
  document.addEventListener('visibilitychange', handleVisibilityChange)
  load()
})
onBeforeUnmount(() => {
  clearRoutePlayback()
  document.removeEventListener('visibilitychange', handleVisibilityChange)
})
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
            <p class="hero-poem">{{ heroImageFailed ? visual.fallbackPoem : visual.poem }}</p>
          </div>
        </section>
        <header class="site-header">
          <a class="brand" href="#top">Cto<span>N</span></a>
          <p>重庆北 → 南京南 · 沿线气象观测</p>
          <button class="refresh-button" :disabled="refreshing" @click="refresh">{{ refreshLabel }}</button>
        </header>
        <aside class="map-dock">
          <RouteMap :stations="route.stations" :geometry="route.geometry" :selected-city-id="selectedCityId" :train-destination-city-id="trainDestinationCityId" :train-duration-ms="TRAIN_MOVE_MS" :autoplay-enabled="autoplayEnabled" @select="selectCity" @toggle-autoplay="toggleAutoplay" />
          <button class="random-button" :disabled="traveling" @click="randomTravel"><span class="travel-mark" aria-hidden="true"><svg viewBox="0 0 24 24" focusable="false"><path d="M4 17.5 10.5 14l3.1 1.7L20 6.5" /><path d="M15.5 6.5H20v4.5" /></svg></span><span class="travel-label">{{ traveling ? `前往 ${selectedCity?.city_name}…` : '随机旅行' }}</span><span class="travel-arrow" aria-hidden="true"><svg viewBox="0 0 24 24" focusable="false"><path d="M5 12h13M13 6l6 6-6 6" /></svg></span></button>
        </aside>
        <section class="observatory" aria-label="当前城市气象观测台">
          <WeatherPanel :weather-data="weather" :city="weather?.city" />
          <div class="profile-area">
            <div class="profile-heading"><div><p class="eyebrow">ROUTE OBSERVATORY</p><h2>沿线观测剖面</h2></div><p>从重庆北站起算的真实距离</p></div>
            <div class="metric-tabs" role="tablist" aria-label="观测指标"><button v-for="[key, label] in metrics" :key="key" :class="{ active: activeMetric === key }" role="tab" :aria-selected="activeMetric === key" @click="activeMetric = key">{{ label }}</button></div>
            <div class="profile-content">
              <aside class="travel-advice" aria-live="polite">
                <div>
                  <span>今日行路建议</span>
                  <small v-if="adviceRefreshing">正在更新</small>
                  <small v-else-if="travelAdvice">{{ travelAdvice.is_stale ? `上次建议 · ${travelAdvice.travel_date}` : travelAdvice.travel_date }}</small>
                </div>
                <p v-if="travelAdvice">{{ travelAdvice.content }}</p>
                <p v-else-if="adviceRefreshing">正在结合沿线观测生成建议…</p>
                <p v-else>更新观测后生成今日路线建议。</p>
                <small v-if="adviceError" class="advice-error">本次建议更新失败：{{ adviceError }}</small>
              </aside>
              <ProfileChart :points="profile.points" :selected-city-id="selectedCityId" :metric="activeMetric" :theme-color="visual.primary" />
            </div>
          </div>
        </section>
        <p v-if="error" class="inline-error">{{ error }} <button @click="selectCity(selectedCityId)">重试</button></p>
      </section>
    </template>
    <div v-else class="loading-state">正在读取沿线观测…</div>
  </main>
</template>
