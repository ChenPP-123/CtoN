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
const adviceRefreshing = ref(false)
const adviceError = ref('')
const traveling = ref(false)
const heroLoading = ref(false)
const error = ref('')
const readyHero = ref(null)
const AUTOPLAY_CYCLE_MS = 10_000
const TRAIN_MOVE_MS = 1_200
const metrics = [['temperature', '温度'], ['humidity', '湿度'], ['aqi', 'AQI'], ['wind_speed', '风速']]
const selectedCity = computed(() => route.value?.stations.find((station) => station.city_id === selectedCityId.value))
const displayedCity = computed(() => readyHero.value?.city || selectedCity.value)
const displayedDate = computed(() => readyHero.value?.weatherDate || '读取观测中')
const visual = computed(() => readyHero.value?.visual || visualForCity(selectedCity.value?.city_name, weather.value?.weather?.text, weather.value?.date))
const themeStyle = computed(() => ({ '--theme-primary': visual.value.primary, '--theme-accent': visual.value.accent, '--hero-overlay': visual.value.overlay, '--hero-fallback': visual.value.gradient }))
const refreshLabel = computed(() => refreshing.value ? '刷新中…' : '刷新数据')
let departureTimer
let arrivalTimer
let weatherRequestId = 0

function preloadImage(source) {
  return new Promise((resolve, reject) => {
    const image = new Image()
    image.onload = resolve
    image.onerror = reject
    image.src = source
  })
}

function isCurrentWeatherRequest(requestId, cityId) {
  return requestId === weatherRequestId && selectedCityId.value === cityId
}

function addHeroImageError(cityName) {
  const message = `${cityName}天气图片加载失败，已显示城市主题背景。`
  error.value = error.value ? `${error.value}；${message}` : message
}

async function prepareHero(city, weatherData, requestId, { fallbackOnly = false } = {}) {
  const nextVisual = visualForCity(city.city_name, fallbackOnly ? '' : weatherData?.weather?.text, weatherData?.date)
  const primarySource = fallbackOnly ? nextVisual.fallbackImage : nextVisual.image

  try {
    await preloadImage(primarySource)
    if (!isCurrentWeatherRequest(requestId, city.city_id)) return
    readyHero.value = { city, visual: nextVisual, weatherDate: weatherData?.date, imageSource: primarySource, imageFailed: fallbackOnly }
    return
  } catch {
    if (!isCurrentWeatherRequest(requestId, city.city_id)) return
  }

  if (primarySource !== nextVisual.fallbackImage) {
    try {
      await preloadImage(nextVisual.fallbackImage)
      if (!isCurrentWeatherRequest(requestId, city.city_id)) return
      readyHero.value = { city, visual: nextVisual, weatherDate: weatherData?.date, imageSource: nextVisual.fallbackImage, imageFailed: true }
      return
    } catch {
      if (!isCurrentWeatherRequest(requestId, city.city_id)) return
    }
  }

  readyHero.value = { city, visual: nextVisual, weatherDate: weatherData?.date, imageSource: '', imageFailed: true }
  addHeroImageError(city.city_name)
}

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
  }
  if (restartPlayback) scheduleRoutePlayback()
  if (!cityChanged && weather.value) return

  const requestId = ++weatherRequestId
  heroLoading.value = true
  try {
    const weatherData = await api.getWeather(cityId)
    if (!isCurrentWeatherRequest(requestId, cityId)) return
    weather.value = weatherData
    await prepareHero(destination, weatherData, requestId)
  } catch (exception) {
    if (!isCurrentWeatherRequest(requestId, cityId)) return
    error.value = exception.message
    await prepareHero(destination, null, requestId, { fallbackOnly: true })
  } finally {
    if (isCurrentWeatherRequest(requestId, cityId)) heroLoading.value = false
  }
}

async function randomTravel() {
  traveling.value = true
  error.value = ''
  try {
    const trip = await api.getRandomTrip(1)
    await selectCity(trip.station.city_id)
  } catch (exception) {
    error.value = exception.message
  } finally {
    traveling.value = false
  }
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
  adviceRefreshing.value = true
  error.value = ''
  adviceError.value = ''
  try {
    const refreshCityId = selectedCityId.value
    const requestId = ++weatherRequestId
    const [profileData, weatherData, adviceResult] = await Promise.all([
      api.getProfile(1),
      api.getWeather(refreshCityId),
      api.getTravelAdvice(1)
        .then((data) => ({ data, error: '' }))
        .catch((exception) => ({ data: null, error: exception.message })),
    ])
    profile.value = profileData
    if (isCurrentWeatherRequest(requestId, refreshCityId)) {
      weather.value = weatherData
      await prepareHero(selectedCity.value, weatherData, requestId)
    }
    if (adviceResult.data) travelAdvice.value = adviceResult.data
    adviceError.value = adviceResult.error
  } catch (exception) {
    error.value = exception.message
  } finally {
    adviceRefreshing.value = false
    refreshing.value = false
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
        <header class="site-header">
          <a class="brand" href="#top">Cto<span>N</span></a>
          <div class="route-identity">
            <p class="route-title">重庆北 → 南京南</p>
            <p class="route-meta">8 STATIONS · 1245 KM · 沿线气象观测</p>
          </div>
          <div class="header-actions">
            <div class="project-meta">
              <span>作者：Yule</span>
              <a href="https://github.com/ChenPP-123/CtoN" target="_blank" rel="noopener noreferrer">
                GitHub <span aria-hidden="true">↗</span>
              </a>
            </div>
            <button class="refresh-button" :disabled="refreshing" @click="refresh">{{ refreshLabel }}</button>
          </div>
        </header>
        <section class="hero" :style="{ background: visual.gradient }">
          <Transition name="hero-image">
            <img v-if="readyHero?.imageSource" :key="readyHero.imageSource" class="hero-image" :src="readyHero.imageSource" :alt="`${displayedCity?.city_name}当地天气景象`">
          </Transition>
          <div class="hero-wash"></div>
          <div :key="displayedCity?.city_id" class="hero-copy" :class="`tone-${visual.textTone}`">
            <div class="hero-title">
              <p class="eyebrow">第 {{ String(displayedCity?.station_order || 1).padStart(2, '0') }} 站 · {{ displayedDate }}</p>
              <h1>{{ displayedCity?.city_name }}</h1>
            </div>
            <p class="city-phrase">{{ visual.phrase }}</p>
            <p class="hero-poem">{{ readyHero?.imageFailed ? visual.fallbackPoem : visual.poem }}</p>
          </div>
          <Transition name="hero-journey">
            <div v-if="heroLoading" class="hero-journey" role="status" aria-live="polite">
              <p>正在抵达</p>
              <strong>「{{ selectedCity?.city_name }}」</strong>
              <div class="journey-track" aria-hidden="true">
                <i class="journey-station journey-station-start"></i>
                <i class="journey-station journey-station-end"></i>
                <span class="journey-train"><b></b><b></b></span>
              </div>
            </div>
          </Transition>
        </section>
        <aside class="map-dock">
          <RouteMap :stations="route.stations" :geometry="route.geometry" :selected-city-id="selectedCityId" :train-destination-city-id="trainDestinationCityId" :train-duration-ms="TRAIN_MOVE_MS" :autoplay-enabled="autoplayEnabled" @select="selectCity" @toggle-autoplay="toggleAutoplay" />
          <button class="random-button" :disabled="traveling" @click="randomTravel"><span class="travel-mark" aria-hidden="true"><svg viewBox="0 0 24 24" focusable="false"><path d="M4 17.5 10.5 14l3.1 1.7L20 6.5" /><path d="M15.5 6.5H20v4.5" /></svg></span><span class="travel-label">{{ traveling ? `前往 ${selectedCity?.city_name}…` : '随机旅行' }}</span><span class="travel-arrow" aria-hidden="true"><svg viewBox="0 0 24 24" focusable="false"><path d="M5 12h13M13 6l6 6-6 6" /></svg></span></button>
        </aside>
        <section class="observatory" aria-label="当前城市气象观测台">
          <WeatherPanel :weather-data="weather" :city="weather?.city" />
          <div class="profile-area">
            <aside class="travel-advice" aria-live="polite">
              <div>
                <span>今日行路建议</span>
                <small v-if="adviceRefreshing">正在更新</small>
                <small v-else-if="travelAdvice">{{ travelAdvice.is_stale ? `上次建议 · ${travelAdvice.travel_date}` : travelAdvice.travel_date }}</small>
              </div>
              <p v-if="travelAdvice">{{ travelAdvice.content }}</p>
              <p v-else-if="adviceRefreshing">正在读取最新路线建议…</p>
              <p v-else>等待后台每日更新生成路线建议。</p>
              <small v-if="adviceError" class="advice-error">本次建议读取失败：{{ adviceError }}</small>
            </aside>
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
