import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import RouteMap from './RouteMap.vue'

vi.mock('../map/amapLoader', () => ({
  loadAMap: vi.fn().mockRejectedValue(new Error('未配置地图 Key')),
}))

const stations = [
  { city_id: 1, city_name: '重庆', station_name: '重庆北站', distance_from_origin_km: 0, longitude: 106.55, latitude: 29.61 },
  { city_id: 2, city_name: '武汉', station_name: '武汉站', distance_from_origin_km: 850, longitude: 114.42, latitude: 30.61 },
]

describe('地图降级交互', () => {
  beforeEach(() => {
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
