import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import RouteMap from './RouteMap.vue'

const amapMocks = vi.hoisted(() => ({
  loadAMap: vi.fn(),
  add: vi.fn(),
  destroy: vi.fn(),
  resize: vi.fn(),
  setFitView: vi.fn(),
  setZoomAndCenter: vi.fn(),
}))

vi.mock('../map/amapLoader', () => ({
  loadAMap: amapMocks.loadAMap,
}))

const stations = [
  { city_id: 1, city_name: '重庆', station_name: '重庆北站', distance_from_origin_km: 0, longitude: 106.55, latitude: 29.61 },
  { city_id: 2, city_name: '武汉', station_name: '武汉站', distance_from_origin_km: 850, longitude: 114.42, latitude: 30.61 },
]

afterEach(() => {
  vi.restoreAllMocks()
})

describe('地图降级交互', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    amapMocks.loadAMap.mockRejectedValue(new Error('未配置地图 Key'))
    window.matchMedia = vi.fn().mockReturnValue({ matches: false })
  })

  it('地图 SDK 不可用时仍可切换站点和暂停巡游', async () => {
    const wrapper = mount(RouteMap, {
      props: {
        stations,
        geometry: { type: 'LineString', coordinates: [] },
        selectedCityId: 1,
        trainDestinationCityId: null,
        trainDurationMs: 1200,
        autoplayEnabled: true,
      },
    })
    await flushPromises()

    expect(wrapper.get('[role="status"]').text()).toContain('未配置地图 Key')
    expect(wrapper.findAll('.map-station-list button')).toHaveLength(2)
    expect(wrapper.get('.map-station-list button.selected').text()).toContain('重庆')

    await wrapper.findAll('.map-station-list button')[1].trigger('click')
    await wrapper.get('.autoplay-toggle').trigger('click')

    expect(wrapper.emitted('select')).toEqual([[2]])
    expect(wrapper.emitted('toggle-autoplay')).toHaveLength(1)
    wrapper.unmount()
  })
})

function workingAMap() {
  const map = {
    add: amapMocks.add,
    destroy: amapMocks.destroy,
    resize: amapMocks.resize,
    setFitView: amapMocks.setFitView,
    setZoomAndCenter: amapMocks.setZoomAndCenter,
  }
  const Map = vi.fn(function () { return map })
  const Polyline = vi.fn(function (options) { this.options = options })
  const Marker = vi.fn(function (options) {
    this.options = options
    this.position = options.position
    this.getPosition = () => this.position
    this.setPosition = (position) => { this.position = position }
  })
  const Pixel = vi.fn(function (x, y) { this.x = x; this.y = y })
  return { sdk: { Map, Polyline, Marker, Pixel }, map }
}

describe('地图线路视野', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.matchMedia = vi.fn().mockReturnValue({ matches: true })
  })

  it('在手机端完整适配线路，并在视口变化后重新计算', async () => {
    const { sdk } = workingAMap()
    amapMocks.loadAMap.mockResolvedValue(sdk)
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(390)
    const wrapper = mount(RouteMap, {
      props: {
        stations,
        geometry: { type: 'LineString', coordinates: stations.map((station) => [station.longitude, station.latitude]) },
        selectedCityId: 1,
      },
    })
    await flushPromises()

    expect(amapMocks.setFitView).toHaveBeenCalledWith(expect.any(Array), false, [42, 46, 42, 46])
    expect(amapMocks.setFitView.mock.calls[0][0]).toHaveLength(4)
    expect(amapMocks.setZoomAndCenter).not.toHaveBeenCalled()

    window.dispatchEvent(new Event('resize'))
    expect(amapMocks.resize).toHaveBeenCalledTimes(1)
    expect(amapMocks.setFitView).toHaveBeenCalledTimes(2)

    wrapper.unmount()
    window.dispatchEvent(new Event('resize'))
    expect(amapMocks.resize).toHaveBeenCalledTimes(1)
    expect(amapMocks.destroy).toHaveBeenCalledTimes(1)
  })

  it('在桌面端保留固定的路线中心和缩放级别', async () => {
    const { sdk } = workingAMap()
    amapMocks.loadAMap.mockResolvedValue(sdk)
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(900)
    const wrapper = mount(RouteMap, { props: { stations, selectedCityId: 1 } })
    await flushPromises()

    expect(amapMocks.setZoomAndCenter).toHaveBeenCalledWith(6.2, [112.6741, 30.7831])
    expect(amapMocks.setFitView).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
