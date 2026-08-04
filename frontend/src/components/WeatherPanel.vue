<script setup>
defineProps({ weatherData: { type: Object, default: null }, city: { type: Object, default: null } })

function value(value, suffix = '') {
  return value === null || value === undefined ? '暂无数据' : `${value}${suffix}`
}

const periodLabels = { day: '白天', night: '夜间' }
const insolationLabels = { strong: '强日照', moderate: '中等日照', slight: '弱日照', weak: '微弱日照' }
</script>

<template>
  <aside class="weather-panel" aria-live="polite">
    <template v-if="weatherData?.weather">
      <div class="panel-kicker">观测台 / {{ weatherData.date }}</div>
      <div class="weather-head">
        <div><h2>{{ weatherData.city.name }}</h2><p>{{ city?.description }}</p></div>
        <div class="temperature">{{ weatherData.weather.temperature_c }}<sup>°C</sup></div>
      </div>
      <div class="weather-status"><span class="weather-glyph">◔</span><span>{{ weatherData.weather.text }}</span><span>体感 {{ weatherData.weather.feels_like_c }}°C</span></div>
      <dl class="weather-grid">
        <div><dt>湿度</dt><dd>{{ value(weatherData.weather.humidity_percent, '%') }}</dd></div>
        <div><dt>风况</dt><dd>{{ value(weatherData.weather.wind_speed_ms, ' m/s') }}</dd></div>
        <div v-if="weatherData.weather.precipitation_probability_percent !== null && weatherData.weather.precipitation_probability_percent !== undefined"><dt>降水概率</dt><dd>{{ value(weatherData.weather.precipitation_probability_percent, '%') }}</dd></div>
        <div v-else><dt>风向</dt><dd>{{ value(weatherData.weather.wind_direction) }}</dd></div>
        <div><dt>能见度</dt><dd>{{ value(weatherData.weather.visibility_km, ' km') }}</dd></div>
      </dl>
      <section class="air-quality"><div><span>AQI</span><strong>{{ weatherData.air_quality?.aqi ?? '—' }}</strong></div><p>PM2.5 {{ value(weatherData.air_quality?.pm25_ug_m3, ' µg/m³') }}<br>{{ weatherData.air_quality?.primary_pollutant || '暂无首要污染物' }}</p></section>
      <section v-if="weatherData.atmosphere" class="stability-analysis">
        <header><span>Pasquill 稳定度</span><small>近似判级</small></header>
        <div class="stability-reading">
          <strong>{{ weatherData.atmosphere.stability_class }}</strong>
          <div><b>{{ weatherData.atmosphere.stability_level }}</b><span>{{ weatherData.atmosphere.explanation }}</span></div>
        </div>
        <dl>
          <div><dt>时段</dt><dd>{{ periodLabels[weatherData.atmosphere.period] }}</dd></div>
          <div><dt>判级天气</dt><dd>{{ weatherData.atmosphere.insolation_category ? insolationLabels[weatherData.atmosphere.insolation_category] : '夜间云量' }}</dd></div>
          <div><dt>云量</dt><dd>{{ value(weatherData.atmosphere.inputs.cloud_cover_percent, '%') }}</dd></div>
          <div><dt>太阳高度</dt><dd>{{ value(weatherData.atmosphere.inputs.solar_elevation_deg, '°') }}</dd></div>
        </dl>
        <p>基于地面风速、云量和太阳位置估算，不用于监管判定。</p>
      </section>
      <section v-else class="stability-analysis stability-unavailable">
        <header><span>Pasquill 稳定度</span><small>数据不足</small></header>
        <p>观测缺少风速或云量，暂无法判级。</p>
      </section>
    </template>
    <div v-else class="empty-panel">正在读取这座城市的气象记录…</div>
  </aside>
</template>
