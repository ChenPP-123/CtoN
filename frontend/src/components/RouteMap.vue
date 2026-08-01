<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { loadAMap } from '../map/amapLoader'

const props = defineProps({
  stations: { type: Array, default: () => [] },
  geometry: { type: Object, default: null },
  selectedCityId: { type: Number, default: 1 },
})
const emit = defineEmits(['select'])

const mapElement = ref(null)
const unavailableReason = ref('')
const hasUsableCoordinates = computed(() => props.stations.length > 0 && props.stations.every((station) => Number.isFinite(station.longitude) && Number.isFinite(station.latitude)))
let map
let AMap
let polyline
const stationMarkers = new Map()

function positionOf(station) {
  return [station.longitude, station.latitude]
}

function createMarkerElement(station) {
  const element = document.createElement('button')
  element.type = 'button'
  element.className = 'amap-station-marker'
  element.setAttribute('aria-label', `选择${station.station_name}`)
  element.innerHTML = `<span class="amap-station-dot"></span><span class="amap-station-label"><strong>${station.city_name}</strong><small>${station.station_name}</small></span>`
  element.addEventListener('click', () => emit('select', station.city_id))
  return element
}

function updateSelectedMarker() {
  for (const [cityId, marker] of stationMarkers) {
    marker.element.classList.toggle('selected', cityId === props.selectedCityId)
  }
}

function focusSelectedStation() {
  if (!map) return
  const marker = stationMarkers.get(props.selectedCityId)
  if (!marker) return
  updateSelectedMarker()
  map.setCenter(marker.position)
}

function routeCoordinates() {
  const coordinates = props.geometry?.type === 'LineString' ? props.geometry.coordinates : null
  return Array.isArray(coordinates) && coordinates.length > 1 ? coordinates : props.stations.map(positionOf)
}

async function initializeMap() {
  if (!hasUsableCoordinates.value) {
    unavailableReason.value = '路线未提供完整站点坐标。'
    return
  }
  try {
    AMap = await loadAMap()
    await nextTick()
    map = new AMap.Map(mapElement.value, { viewMode: '2D', zoom: 6, center: positionOf(props.stations[0]), mapStyle: 'amap://styles/darkblue' })
    for (const station of props.stations) {
      const element = createMarkerElement(station)
      const position = positionOf(station)
      const marker = new AMap.Marker({ position, content: element, offset: new AMap.Pixel(-10, -10), zIndex: 20 })
      marker.on('click', () => emit('select', station.city_id))
      stationMarkers.set(station.city_id, { marker, element, position })
      map.add(marker)
    }
    polyline = new AMap.Polyline({ path: routeCoordinates(), strokeColor: '#ffbd59', strokeWeight: 5, strokeOpacity: 0.9, strokeStyle: 'dashed', zIndex: 10 })
    map.add(polyline)
    map.setFitView([...stationMarkers.values()].map(({ marker }) => marker).concat(polyline), false, [54, 80, 54, 80])
    updateSelectedMarker()
  } catch (error) {
    unavailableReason.value = error.message || '高德地图暂时不可用。'
  }
}

watch(() => props.selectedCityId, focusSelectedStation)

onMounted(initializeMap)
onBeforeUnmount(() => {
  stationMarkers.clear()
  if (map) map.destroy()
  map = undefined
})
</script>

<template>
  <section class="route-map" aria-label="重庆至南京气象旅行路线">
    <div v-if="!unavailableReason" ref="mapElement" class="amap-canvas"></div>
    <div v-else class="map-unavailable" role="status">
      <p>地图暂不可用</p>
      <span>{{ unavailableReason }}</span>
      <div class="map-station-list">
        <button v-for="station in stations" :key="station.city_id" :class="{ selected: station.city_id === selectedCityId }" @click="emit('select', station.city_id)">
          <strong>{{ station.city_name }}</strong><small>{{ station.station_name }} · {{ station.distance_from_origin_km }} km</small>
        </button>
      </div>
    </div>
    <div class="route-caption"><span>CTN / 1245 KM</span><span>重庆北 → 南京南</span></div>
  </section>
</template>
