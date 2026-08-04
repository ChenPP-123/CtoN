import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import WeatherPanel from './WeatherPanel.vue'

const weatherData = {
  date: '2026-08-04',
  city: { name: '武汉' },
  weather: {
    temperature_c: 31,
    feels_like_c: 35,
    text: '晴',
    humidity_percent: 65,
    wind_speed_ms: 3.4,
    wind_direction: '南风',
    precipitation_probability_percent: 15,
    visibility_km: 12,
  },
  air_quality: { aqi: 48, pm25_ug_m3: 24, primary_pollutant: null },
  atmosphere: {
    stability_class: 'B-C',
    stability_level: '不稳定至弱不稳定',
    period: 'day',
    insolation_category: 'moderate',
    inputs: { wind_speed_ms: 3.4, cloud_cover_percent: 35, solar_elevation_deg: 52.1 },
    explanation: '当前处于白天，近地层估算为不稳定至弱不稳定。',
  },
}


describe('WeatherPanel', () => {
  it('shows the Pasquill class and its observable inputs', () => {
    const wrapper = mount(WeatherPanel, { props: { weatherData } })

    expect(wrapper.text()).toContain('Pasquill 稳定度')
    expect(wrapper.text()).toContain('B-C')
    expect(wrapper.text()).toContain('不稳定至弱不稳定')
    expect(wrapper.text()).toContain('35%')
    expect(wrapper.text()).toContain('52.1°')
    expect(wrapper.text()).toContain('不用于监管判定')
    expect(wrapper.text()).toContain('降水概率15%')
  })

  it('shows wind direction when current weather has no precipitation probability', () => {
    const wrapper = mount(WeatherPanel, {
      props: {
        weatherData: {
          ...weatherData,
          weather: { ...weatherData.weather, precipitation_probability_percent: null },
        },
      },
    })

    expect(wrapper.text()).toContain('风向南风')
    expect(wrapper.text()).not.toContain('降水概率')
  })

  it('explains when the observation cannot be classified', () => {
    const wrapper = mount(WeatherPanel, {
      props: { weatherData: { ...weatherData, atmosphere: null } },
    })

    expect(wrapper.text()).toContain('Pasquill 稳定度')
    expect(wrapper.text()).toContain('数据不足')
    expect(wrapper.text()).toContain('暂无法判级')
  })
})
