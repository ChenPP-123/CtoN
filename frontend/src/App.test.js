import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import App from './App.vue'

const apiMocks = vi.hoisted(() => ({
  getRoute: vi.fn(),
  getProfile: vi.fn(),
  getWeather: vi.fn(),
  getRandomTrip: vi.fn(),
  getTravelAdvice: vi.fn(),
  refreshWeather: vi.fn(),
  generateTravelAdvice: vi.fn(),
}))

vi.mock('./api', () => ({ api: apiMocks }))

const route = {
  stations: [
    { city_id: 1, city_name: '重庆', station_name: '重庆北站', station_order: 1, distance_from_origin_km: 0 },
    { city_id: 2, city_name: '武汉', station_name: '武汉站', station_order: 2, distance_from_origin_km: 850 },
  ],
  geometry: { type: 'LineString', coordinates: [] },
}
const profile = {
  points: route.stations.map((station, index) => ({
    ...station,
    temperature_c: 29 + index,
    humidity_percent: 70 - index,
    aqi: 40 + index,
    wind_speed_ms: 2 + index,
  })),
}
const advice = { content: '沿线天气宜人，请适时补水。', travel_date: '2026-08-04', is_stale: false }

function weatherFor(cityId) {
  const station = route.stations.find((item) => item.city_id === cityId)
  return {
    city: { id: cityId, name: station.city_name },
    date: '2026-08-04',
    weather: { text: '晴', temperature_c: cityId === 1 ? 29 : 30 },
  }
}

const stubs = {
  RouteMap: {
    props: ['stations', 'selectedCityId', 'autoplayEnabled'],
    emits: ['select', 'toggle-autoplay'],
    template: `
      <div data-test="route-map" :data-selected="selectedCityId" :data-autoplay="autoplayEnabled">
        <button data-test="select-next" @click="$emit('select', stations[1].city_id)">选择武汉</button>
        <button data-test="toggle-autoplay" @click="$emit('toggle-autoplay')">切换巡游</button>
      </div>
    `,
  },
  WeatherPanel: {
    props: ['weatherData'],
    template: '<div data-test="weather-panel">{{ weatherData?.city?.name }} {{ weatherData?.weather?.temperature_c }}</div>',
  },
  ProfileChart: {
    props: ['metric', 'selectedCityId'],
    template: '<div data-test="profile-chart" :data-metric="metric" :data-selected="selectedCityId" />',
  },
}

async function mountLoadedApp() {
  apiMocks.getRoute.mockResolvedValue(route)
  apiMocks.getProfile.mockResolvedValue(profile)
  apiMocks.getWeather.mockImplementation((cityId) => Promise.resolve(weatherFor(cityId)))
  apiMocks.getTravelAdvice.mockResolvedValue(advice)
  const wrapper = mount(App, { global: { stubs } })
  await flushPromises()
  return wrapper
}

let wrapper

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.restoreAllMocks()
})

describe('核心观测交互', () => {
  it('加载默认站点，并在切站和切换指标时同步页面', async () => {
    wrapper = await mountLoadedApp()

    expect(apiMocks.getRoute).toHaveBeenCalledWith(1)
    expect(apiMocks.getProfile).toHaveBeenCalledWith(1)
    expect(apiMocks.getWeather).toHaveBeenCalledWith(1)
    expect(wrapper.get('h1').text()).toBe('重庆')
    expect(wrapper.get('[data-test="weather-panel"]').text()).toBe('重庆 29')

    await wrapper.get('[data-test="select-next"]').trigger('click')
    await flushPromises()

    expect(apiMocks.getWeather).toHaveBeenLastCalledWith(2)
    expect(wrapper.get('h1').text()).toBe('武汉')
    expect(wrapper.get('[data-test="profile-chart"]').attributes('data-selected')).toBe('2')

    await wrapper.get('[role="tablist"] button:nth-child(2)').trigger('click')
    expect(wrapper.get('[data-test="profile-chart"]').attributes('data-metric')).toBe('humidity')
  })

  it('暂停和恢复自动巡游时更新地图状态', async () => {
    wrapper = await mountLoadedApp()
    const routeMap = () => wrapper.get('[data-test="route-map"]')

    expect(routeMap().attributes('data-autoplay')).toBe('true')
    await wrapper.get('[data-test="toggle-autoplay"]').trigger('click')
    expect(routeMap().attributes('data-autoplay')).toBe('false')
    await wrapper.get('[data-test="toggle-autoplay"]').trigger('click')
    expect(routeMap().attributes('data-autoplay')).toBe('true')
  })

  it('随机旅行会加载后端返回的目的地天气', async () => {
    wrapper = await mountLoadedApp()
    apiMocks.getRandomTrip.mockResolvedValue({ station: { city_id: 2 } })

    await wrapper.get('.random-button').trigger('click')
    await flushPromises()

    expect(apiMocks.getRandomTrip).toHaveBeenCalledWith(1)
    expect(apiMocks.getWeather).toHaveBeenLastCalledWith(2)
    expect(wrapper.get('h1').text()).toBe('武汉')
  })

  it('按天气、剖面、建议的顺序刷新，并展示新建议', async () => {
    wrapper = await mountLoadedApp()
    const refreshedAdvice = { ...advice, content: '沿线有雨，请将雨具放在随手可取处。' }
    apiMocks.refreshWeather.mockResolvedValue({ updated_count: 2 })
    apiMocks.generateTravelAdvice.mockResolvedValue(refreshedAdvice)

    await wrapper.get('.refresh-button').trigger('click')
    await flushPromises()

    expect(apiMocks.refreshWeather).toHaveBeenCalledOnce()
    expect(apiMocks.getProfile).toHaveBeenCalledTimes(2)
    expect(apiMocks.getWeather).toHaveBeenCalledTimes(2)
    expect(apiMocks.generateTravelAdvice).toHaveBeenCalledWith(1)
    expect(apiMocks.refreshWeather.mock.invocationCallOrder[0]).toBeLessThan(apiMocks.generateTravelAdvice.mock.invocationCallOrder[0])
    expect(wrapper.get('.travel-advice').text()).toContain(refreshedAdvice.content)
    expect(wrapper.get('.refresh-button').text()).toBe('更新观测')
  })

  it('初始加载失败后可以重试', async () => {
    apiMocks.getRoute
      .mockRejectedValueOnce(new Error('线路加载失败'))
      .mockResolvedValue(route)
    apiMocks.getProfile.mockResolvedValue(profile)
    apiMocks.getWeather.mockImplementation((cityId) => Promise.resolve(weatherFor(cityId)))
    apiMocks.getTravelAdvice.mockResolvedValue(advice)
    wrapper = mount(App, { global: { stubs } })
    await flushPromises()

    expect(wrapper.get('.error-state').text()).toContain('线路加载失败')
    await wrapper.get('.error-state button').trigger('click')
    await flushPromises()

    expect(apiMocks.getRoute).toHaveBeenCalledTimes(2)
    expect(wrapper.get('h1').text()).toBe('重庆')
  })
})
