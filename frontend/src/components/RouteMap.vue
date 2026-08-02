<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { loadAMap } from '../map/amapLoader'

const props = defineProps({
  stations: { type: Array, default: () => [] },
  geometry: { type: Object, default: null },
  selectedCityId: { type: Number, default: null },
  trainDestinationCityId: { type: Number, default: null },
  trainDurationMs: { type: Number, default: 1_200 },
  autoplayEnabled: { type: Boolean, default: true },
})
const emit = defineEmits(['select', 'toggle-autoplay'])

const mapElement = ref(null)
const unavailableReason = ref('')
const hasUsableCoordinates = computed(() => props.stations.length > 0 && props.stations.every((station) => Number.isFinite(station.longitude) && Number.isFinite(station.latitude)))
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
const ROUTE_CENTER = [112.6741, 30.7831]
const ROUTE_ZOOM = 6.2
let map
let AMap
let routeCasing
let routeLine
let trainMarker
let trainElement
let animationFrame
let relocationTimer
let animationToken = 0
const stationMarkers = new Map()

function positionOf(station) {
  return [station.longitude, station.latitude]
}

function stationByCityId(cityId) {
  return props.stations.find((station) => station.city_id === cityId)
}

function createMarkerElement(station) {
  const element = document.createElement('button')
  element.type = 'button'
  element.className = `amap-station-marker label-${station.station_order % 2 === 0 ? 'below' : 'above'}`
  element.setAttribute('aria-label', `选择${station.station_name}`)
  element.title = station.station_name

  const node = document.createElement('span')
  node.className = 'amap-station-node'
  node.setAttribute('aria-hidden', 'true')
  const label = document.createElement('span')
  label.className = 'amap-station-label'
  label.textContent = station.station_name.replace(/站$/, '')
  element.append(node, label)
  element.addEventListener('click', () => emit('select', station.city_id))
  return element
}

function createTrainElement() {
  const element = document.createElement('div')
  element.className = 'amap-train-marker'
  element.setAttribute('aria-hidden', 'true')
  element.innerHTML = `<svg viewBox="0 0 52 34" focusable="false"><path class="train-body" d="M4 25V14.5C4 9.8 7.8 6 12.5 6h17.7c6.2 0 10.7 3.8 15.1 9.1l3.2 3.9c2 2.5.2 6-3 6H4Z"/><path class="train-window" d="M12 10h17.6c4 0 7.1 1.7 10.5 5.8H9v-2.7c0-1.7 1.3-3.1 3-3.1Z"/><path class="train-detail" d="M7 21h38M12 25l-2 4m30-4 2 4M7 29h38"/><circle cx="15" cy="25" r="2.2"/><circle cx="37" cy="25" r="2.2"/></svg>`
  return element
}

function updateSelectedMarker() {
  for (const [cityId, marker] of stationMarkers) {
    const selected = cityId === props.selectedCityId
    marker.element.classList.toggle('selected', selected)
    marker.element.setAttribute('aria-current', selected ? 'location' : 'false')
  }
}

function routeCoordinates() {
  const coordinates = props.geometry?.type === 'LineString' ? props.geometry.coordinates : null
  return Array.isArray(coordinates) && coordinates.length > 1 ? coordinates : props.stations.map(positionOf)
}

function lngLatArray(position) {
  if (!position) return null
  if (Array.isArray(position)) return position
  return [position.getLng(), position.getLat()]
}

function cancelTrainAnimation() {
  animationToken += 1
  window.cancelAnimationFrame(animationFrame)
  window.clearTimeout(relocationTimer)
  animationFrame = undefined
  relocationTimer = undefined
  trainElement?.classList.remove('resetting', 'relocating')
}

function setTrainPosition(position) {
  trainMarker?.setPosition(position)
}

function relocateTrainToSelected() {
  if (!trainMarker) return
  const station = stationByCityId(props.selectedCityId)
  if (!station) return
  const destination = positionOf(station)
  const current = lngLatArray(trainMarker.getPosition())
  if (current && Math.abs(current[0] - destination[0]) < .0001 && Math.abs(current[1] - destination[1]) < .0001) return
  if (reducedMotion.matches) {
    setTrainPosition(destination)
    return
  }

  trainElement.classList.add('relocating')
  relocationTimer = window.setTimeout(() => {
    setTrainPosition(destination)
    requestAnimationFrame(() => trainElement?.classList.remove('relocating'))
  }, 180)
}

function trainAngle(from, to) {
  return Math.atan2(-(to[1] - from[1]), to[0] - from[0]) * 180 / Math.PI
}

function animateTrain(from, to) {
  cancelTrainAnimation()
  if (!trainMarker) return
  if (reducedMotion.matches) {
    setTrainPosition(to)
    return
  }

  const token = animationToken
  const startedAt = performance.now()
  trainElement.style.setProperty('--train-angle', `${trainAngle(from, to)}deg`)

  function move(now) {
    if (token !== animationToken) return
    const progress = Math.min((now - startedAt) / props.trainDurationMs, 1)
    const eased = progress < .5 ? 4 * progress ** 3 : 1 - (-2 * progress + 2) ** 3 / 2
    setTrainPosition([
      from[0] + (to[0] - from[0]) * eased,
      from[1] + (to[1] - from[1]) * eased,
    ])
    if (progress < 1) animationFrame = requestAnimationFrame(move)
  }

  animationFrame = requestAnimationFrame(move)
}

function resetTrainAtOrigin(origin) {
  cancelTrainAnimation()
  if (!trainMarker) return
  if (reducedMotion.matches) {
    setTrainPosition(origin)
    return
  }

  const token = animationToken
  trainElement.classList.add('resetting')
  relocationTimer = window.setTimeout(() => {
    if (token !== animationToken) return
    setTrainPosition(origin)
    trainElement.style.setProperty('--train-angle', '0deg')
    requestAnimationFrame(() => trainElement?.classList.remove('resetting'))
  }, props.trainDurationMs / 2)
}

function moveTrainToDestination(cityId) {
  if (!trainMarker || cityId === null) return
  const fromStation = stationByCityId(props.selectedCityId)
  const destination = stationByCityId(cityId)
  if (!fromStation || !destination) return

  const wrapsToOrigin = fromStation.station_order === props.stations.length && destination.station_order === 1
  if (wrapsToOrigin) resetTrainAtOrigin(positionOf(destination))
  else animateTrain(positionOf(fromStation), positionOf(destination))
}

async function initializeMap() {
  if (!hasUsableCoordinates.value) {
    unavailableReason.value = '路线未提供完整站点坐标。'
    return
  }
  try {
    AMap = await loadAMap()
    await nextTick()
    map = new AMap.Map(mapElement.value, { viewMode: '2D', zoom: ROUTE_ZOOM, center: ROUTE_CENTER, mapStyle: 'amap://styles/normal' })
    const coordinates = routeCoordinates()
    routeCasing = new AMap.Polyline({ path: coordinates, strokeColor: '#f7faf6', strokeWeight: 8, strokeOpacity: .94, lineJoin: 'round', lineCap: 'round', zIndex: 9 })
    routeLine = new AMap.Polyline({ path: coordinates, strokeColor: '#244a57', strokeWeight: 3, strokeOpacity: .92, lineJoin: 'round', lineCap: 'round', zIndex: 10 })
    map.add([routeCasing, routeLine])

    for (const station of props.stations) {
      const element = createMarkerElement(station)
      const marker = new AMap.Marker({ position: positionOf(station), content: element, offset: new AMap.Pixel(-11, -11), zIndex: 20 })
      stationMarkers.set(station.city_id, { marker, element })
      map.add(marker)
    }

    trainElement = createTrainElement()
    trainMarker = new AMap.Marker({ position: positionOf(stationByCityId(props.selectedCityId) || props.stations[0]), content: trainElement, offset: new AMap.Pixel(-19, -19), zIndex: 30 })
    map.add(trainMarker)
    if (mapElement.value.clientWidth < 700) {
      map.setFitView([...stationMarkers.values()].map(({ marker }) => marker).concat(routeCasing, routeLine), false, [50, 56, 50, 56])
    } else {
      map.setZoomAndCenter(ROUTE_ZOOM, ROUTE_CENTER)
    }
    updateSelectedMarker()
    moveTrainToDestination(props.trainDestinationCityId)
  } catch (error) {
    unavailableReason.value = error.message || '高德地图暂时不可用。'
  }
}

watch(() => props.selectedCityId, () => {
  updateSelectedMarker()
  if (props.trainDestinationCityId === null) {
    cancelTrainAnimation()
    relocateTrainToSelected()
  }
})
watch(() => props.trainDestinationCityId, (cityId) => {
  if (cityId === null) {
    cancelTrainAnimation()
    relocateTrainToSelected()
  } else {
    moveTrainToDestination(cityId)
  }
})

onMounted(initializeMap)
onBeforeUnmount(() => {
  cancelTrainAnimation()
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
    <button class="autoplay-toggle" type="button" :aria-pressed="autoplayEnabled" @click="emit('toggle-autoplay')">
      <span aria-hidden="true">{{ autoplayEnabled ? 'Ⅱ' : '▶' }}</span>{{ autoplayEnabled ? '暂停巡游' : '继续巡游' }}
    </button>
    <div class="route-caption"><span>CTN / 1245 KM</span><span>重庆北 → 南京南</span></div>
  </section>
</template>
