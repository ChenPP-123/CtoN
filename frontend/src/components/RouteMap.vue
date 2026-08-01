<script setup>
import { computed } from 'vue'

const props = defineProps({
  stations: { type: Array, default: () => [] },
  selectedCityId: { type: Number, default: 1 },
})
const emit = defineEmits(['select'])

const placedStations = computed(() => props.stations.map((station, index) => ({
  ...station,
  x: [13, 52, 88][index] ?? 50,
  y: [72, 42, 22][index] ?? 50,
})))
const selectedStation = computed(() => placedStations.value.find((station) => station.city_id === props.selectedCityId))
</script>

<template>
  <section class="route-map" aria-label="重庆至南京气象旅行路线">
    <div class="map-grid"></div>
    <div class="terrain terrain-one"></div>
    <div class="terrain terrain-two"></div>
    <svg class="route-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
      <path d="M 13 72 C 30 70, 39 52, 52 42 S 76 28, 88 22" class="route-shadow" />
      <path d="M 13 72 C 30 70, 39 52, 52 42 S 76 28, 88 22" class="route-line" />
      <line v-if="selectedStation" x1="0" :x2="selectedStation.x" y1="96" :y2="selectedStation.y" class="focus-line" />
    </svg>

    <button
      v-for="station in placedStations"
      :key="station.city_id"
      class="station"
      :class="{ selected: station.city_id === selectedCityId }"
      :style="{ left: `${station.x}%`, top: `${station.y}%` }"
      :aria-pressed="station.city_id === selectedCityId"
      @click="emit('select', station.city_id)"
    >
      <span class="station-dot"></span>
      <span class="station-copy"><strong>{{ station.city_name }}</strong><small>{{ station.distance_from_origin_km }} km</small></span>
    </button>

    <div v-if="selectedStation" class="train" :style="{ left: `${selectedStation.x}%`, top: `${selectedStation.y}%` }" aria-label="当前高铁位置">
      <span>🚄</span>
    </div>
    <div class="route-caption"><span>CTN / 1200 KM</span><span>重庆北 → 南京南</span></div>
  </section>
</template>
