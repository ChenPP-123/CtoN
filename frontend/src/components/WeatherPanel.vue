<script setup>
defineProps({ weatherData: { type: Object, default: null }, city: { type: Object, default: null } })

function value(value, suffix = '') {
  return value === null || value === undefined ? '暂无数据' : `${value}${suffix}`
}
</script>

<template>
  <aside class="weather-panel" aria-live="polite">
    <template v-if="weatherData?.weather">
      <div class="panel-kicker">当前站点 / {{ weatherData.date }}</div>
      <div class="weather-head">
        <div><h2>{{ weatherData.city.name }}</h2><p>{{ city?.description }}</p></div>
        <div class="temperature">{{ weatherData.weather.temperature_c }}<sup>°C</sup></div>
      </div>
      <div class="weather-status"><span class="weather-glyph">◔</span><span>{{ weatherData.weather.text }}</span><span>体感 {{ weatherData.weather.feels_like_c }}°C</span></div>
      <dl class="weather-grid">
        <div><dt>湿度</dt><dd>{{ value(weatherData.weather.humidity_percent, '%') }}</dd></div>
        <div><dt>风况</dt><dd>{{ value(weatherData.weather.wind_speed_ms, ' m/s') }}</dd></div>
        <div><dt>能见度</dt><dd>{{ value(weatherData.weather.visibility_km, ' km') }}</dd></div>
        <div><dt>降水概率</dt><dd>{{ value(weatherData.weather.precipitation_probability_percent, '%') }}</dd></div>
      </dl>
      <section class="air-quality"><div><span>AQI</span><strong>{{ weatherData.air_quality?.aqi ?? '—' }}</strong></div><p>PM2.5 {{ value(weatherData.air_quality?.pm25_ug_m3, ' µg/m³') }}<br>{{ weatherData.air_quality?.primary_pollutant || '暂无首要污染物' }}</p></section>
      <section v-if="weatherData.atmosphere" class="atmosphere"><span>大气状态</span><h3>{{ weatherData.atmosphere.stability_level }}</h3><p>{{ weatherData.atmosphere.explanation }}</p><small>温度直减率 {{ weatherData.atmosphere.lapse_rate_c_per_km }} °C/km</small></section>
    </template>
    <div v-else class="empty-panel">正在读取这座城市的气象记录…</div>
  </aside>
</template>
