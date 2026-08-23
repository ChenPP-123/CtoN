import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App.vue'

const apiMocks = vi.hoisted(() => ({
  getRoute: vi.fn(),
  getProfile: vi.fn(),
  getWeather: vi.fn(),
  getRandomTrip: vi.fn(),
  getTravelAdvice: vi.fn(),
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
        <button data-test="select-first" @click="$emit('select', stations[0].city_id)">选择重庆</button>
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

let imageBehavior
let imageRequests

class MockImage {
  set src(source) {
    this.source = source
    imageRequests.push(this)
    if (imageBehavior === 'resolve') queueMicrotask(() => this.succeed())
    if (imageBehavior === 'reject') queueMicrotask(() => this.fail())
  }

  succeed() {
    this.onload?.()
  }

  fail() {
    this.onerror?.(new Error(`无法加载 ${this.source}`))
  }
}

function deferred() {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
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

beforeEach(() => {
  imageBehavior = 'resolve'
  imageRequests = []
  vi.stubGlobal('Image', MockImage)
})

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
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

  it('刷新时只并行读取天气、剖面和最新建议', async () => {
    wrapper = await mountLoadedApp()
    const refreshedAdvice = { ...advice, content: '沿线有雨，请将雨具放在随手可取处。' }
    apiMocks.getTravelAdvice.mockResolvedValue(refreshedAdvice)

    await wrapper.get('.refresh-button').trigger('click')
    await flushPromises()

    expect(apiMocks.getProfile).toHaveBeenCalledTimes(2)
    expect(apiMocks.getWeather).toHaveBeenCalledTimes(2)
    expect(apiMocks.getTravelAdvice).toHaveBeenCalledTimes(2)
    expect(apiMocks.getTravelAdvice).toHaveBeenLastCalledWith(1)
    expect(wrapper.get('.travel-advice').text()).toContain(refreshedAdvice.content)
    expect(wrapper.get('.refresh-button').text()).toBe('刷新数据')
  })

  it('建议读取失败时保留原建议并显示错误', async () => {
    wrapper = await mountLoadedApp()
    apiMocks.getTravelAdvice.mockRejectedValueOnce(new Error('建议暂不可用'))

    await wrapper.get('.refresh-button').trigger('click')
    await flushPromises()

    expect(wrapper.get('.travel-advice').text()).toContain(advice.content)
    expect(wrapper.get('.advice-error').text()).toContain('建议暂不可用')
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

  it('天气请求未完成时保留旧图并显示目的地加载层', async () => {
    wrapper = await mountLoadedApp()
    const wuhanWeather = deferred()
    apiMocks.getWeather.mockReturnValueOnce(wuhanWeather.promise)
    const oldImage = wrapper.get('.hero-image').attributes('src')

    await wrapper.get('[data-test="select-next"]').trigger('click')

    expect(wrapper.get('[data-test="route-map"]').attributes('data-selected')).toBe('2')
    expect(wrapper.get('.hero-image').attributes('src')).toBe(oldImage)
    expect(wrapper.get('.hero-journey').text()).toContain('正在抵达')
    expect(wrapper.get('.hero-journey').text()).toContain('武汉')
  })

  it('图片预加载完成后直接切换到准确天气图', async () => {
    wrapper = await mountLoadedApp()
    imageBehavior = 'deferred'
    const oldImage = wrapper.get('.hero-image').attributes('src')
    const oldCopy = wrapper.get('.hero-copy').element

    await wrapper.get('[data-test="select-next"]').trigger('click')
    await flushPromises()

    const pendingImage = imageRequests.at(-1)
    expect(pendingImage.source).toBe('/weather/wuhan/summer-clear.webp')
    expect(wrapper.get('.hero-image').attributes('src')).toBe(oldImage)
    expect(wrapper.html()).not.toContain('/weather/wuhan/summer-normal.webp')

    pendingImage.succeed()
    await flushPromises()

    expect(wrapper.get('.hero-image').attributes('src')).toBe('/weather/wuhan/summer-clear.webp')
    expect(wrapper.get('.hero-copy').element).not.toBe(oldCopy)
    expect(wrapper.get('.hero-title h1').text()).toBe('武汉')
    expect(wrapper.get('.city-phrase').text()).not.toBe('')
    expect(wrapper.get('.hero-poem').text()).not.toBe('')
    expect(wrapper.find('.hero-journey').exists()).toBe(false)
  })

  it('快速连续切换时忽略过期图片回调', async () => {
    wrapper = await mountLoadedApp()
    imageBehavior = 'deferred'

    await wrapper.get('[data-test="select-next"]').trigger('click')
    await flushPromises()
    const staleWuhanImage = imageRequests.at(-1)

    await wrapper.get('[data-test="select-first"]').trigger('click')
    await flushPromises()
    const currentChongqingImage = imageRequests.at(-1)

    currentChongqingImage.succeed()
    await flushPromises()
    expect(wrapper.get('h1').text()).toBe('重庆')
    expect(wrapper.find('.hero-journey').exists()).toBe(false)

    staleWuhanImage.succeed()
    await flushPromises()
    expect(wrapper.get('h1').text()).toBe('重庆')
    expect(wrapper.get('.hero-image').attributes('src')).toBe('/weather/chongqing/summer-clear.webp')
  })

  it('快速连续切换时忽略过期天气响应', async () => {
    wrapper = await mountLoadedApp()
    const staleWuhanWeather = deferred()
    apiMocks.getWeather
      .mockReturnValueOnce(staleWuhanWeather.promise)
      .mockResolvedValueOnce(weatherFor(1))

    await wrapper.get('[data-test="select-next"]').trigger('click')
    await wrapper.get('[data-test="select-first"]').trigger('click')
    await flushPromises()

    staleWuhanWeather.resolve(weatherFor(2))
    await flushPromises()

    expect(wrapper.get('[data-test="weather-panel"]').text()).toBe('重庆 29')
    expect(wrapper.get('.hero-image').attributes('src')).toBe('/weather/chongqing/summer-clear.webp')
    expect(wrapper.find('.hero-journey').exists()).toBe(false)
  })

  it('主图加载失败时改用目的城市季节备用图', async () => {
    wrapper = await mountLoadedApp()
    imageBehavior = 'deferred'

    await wrapper.get('[data-test="select-next"]').trigger('click')
    await flushPromises()
    imageRequests.at(-1).fail()
    await flushPromises()

    const fallbackImage = imageRequests.at(-1)
    expect(fallbackImage.source).toBe('/weather/wuhan/summer-normal.webp')
    fallbackImage.succeed()
    await flushPromises()

    expect(wrapper.get('.hero-image').attributes('src')).toMatch(/^\/weather\/wuhan\/.+-normal\.webp$/)
    expect(wrapper.find('.hero-journey').exists()).toBe(false)
  })

  it('主图和备用图均失败时显示目的城市主题背景和明确错误', async () => {
    wrapper = await mountLoadedApp()
    imageBehavior = 'deferred'

    await wrapper.get('[data-test="select-next"]').trigger('click')
    await flushPromises()
    imageRequests.at(-1).fail()
    await flushPromises()
    imageRequests.at(-1).fail()
    await flushPromises()

    expect(wrapper.find('.hero-image').exists()).toBe(false)
    expect(wrapper.get('.inline-error').text()).toContain('武汉天气图片加载失败')
    expect(wrapper.find('.hero-journey').exists()).toBe(false)
  })

  it('天气请求失败时结束加载、显示备用视觉并允许重试', async () => {
    wrapper = await mountLoadedApp()
    apiMocks.getWeather.mockRejectedValueOnce(new Error('天气暂不可用'))

    await wrapper.get('[data-test="select-next"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('.hero-journey').exists()).toBe(false)
    expect(wrapper.get('.hero-image').attributes('src')).toMatch(/^\/weather\/wuhan\/.+-normal\.webp$/)
    expect(wrapper.get('.inline-error').text()).toContain('天气暂不可用')

    await wrapper.get('.inline-error button').trigger('click')
    await flushPromises()
    expect(apiMocks.getWeather).toHaveBeenLastCalledWith(2)
    expect(wrapper.find('.inline-error').exists()).toBe(false)
  })
})
