// @vitest-environment jsdom

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import ProfileChart from './ProfileChart.vue'


const echartsMocks = vi.hoisted(() => ({
  init: vi.fn(),
  setOption: vi.fn(),
  resize: vi.fn(),
  dispose: vi.fn(),
}))

vi.mock('echarts', () => ({ init: echartsMocks.init }))

const points = Array.from({ length: 8 }, (_, index) => ({
  city_id: index + 1,
  city_name: `城市${index + 1}`,
  distance_from_origin_km: index * 100,
  temperature_c: 25 + index,
  humidity_percent: 60 + index,
  aqi: 40 + index,
  wind_speed_ms: 2 + index / 10,
}))

let resizeCallback
const observe = vi.fn()
const disconnect = vi.fn()

beforeEach(() => {
  vi.clearAllMocks()
  echartsMocks.init.mockReturnValue({
    setOption: echartsMocks.setOption,
    resize: echartsMocks.resize,
    dispose: echartsMocks.dispose,
  })
  resizeCallback = undefined
  global.ResizeObserver = class {
    constructor(callback) { resizeCallback = callback }
    observe = observe
    disconnect = disconnect
  }
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
    width: 320,
    height: 155,
    top: 0,
    right: 320,
    bottom: 155,
    left: 0,
    x: 0,
    y: 0,
    toJSON: () => {},
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ProfileChart', () => {
  it('initializes once with SVG and renders all route stations', async () => {
    mount(ProfileChart, { props: { points } })
    await flushPromises()

    expect(echartsMocks.init).toHaveBeenCalledTimes(1)
    expect(echartsMocks.init).toHaveBeenCalledWith(expect.any(HTMLElement), null, { renderer: 'svg' })
    expect(echartsMocks.setOption).toHaveBeenCalled()
    const option = echartsMocks.setOption.mock.calls.at(-1)[0]
    expect(option.xAxis.data).toHaveLength(8)
    expect(option.yAxis.axisLabel.fontSize).toBe(9)
    expect(option.series[0].data).toHaveLength(8)
  })

  it('resizes on container changes and redraws after metric and theme updates', async () => {
    const wrapper = mount(ProfileChart, { props: { points } })
    await flushPromises()
    echartsMocks.resize.mockClear()
    echartsMocks.setOption.mockClear()

    resizeCallback()
    expect(echartsMocks.resize).toHaveBeenCalledTimes(1)

    await wrapper.setProps({ themeColor: '#123456' })
    expect(echartsMocks.setOption.mock.calls.at(-1)[0].series[0].lineStyle.color).toBe('#123456')

    await wrapper.setProps({ metric: 'humidity' })
    expect(echartsMocks.setOption).toHaveBeenCalled()
    expect(echartsMocks.setOption.mock.calls.at(-1)[0].yAxis.axisLabel.formatter).toBe('{value}%')
  })

  it('shows a clear state when the selected metric has no observations', async () => {
    const emptyPoints = points.map((point) => ({ ...point, aqi: null }))
    const wrapper = mount(ProfileChart, { props: { points: emptyPoints, metric: 'aqi' } })
    await flushPromises()

    expect(wrapper.text()).toContain('暂无该指标的沿线观测')
    expect(echartsMocks.setOption).not.toHaveBeenCalled()
  })

  it('shows an error when ECharts initialization fails', async () => {
    echartsMocks.init.mockImplementationOnce(() => { throw new Error('init failed') })
    const wrapper = mount(ProfileChart, { props: { points } })
    await flushPromises()

    expect(wrapper.text()).toContain('剖面绘制失败，请刷新页面')
  })

  it('releases the observer, listener, and chart on unmount', async () => {
    const removeEventListener = vi.spyOn(window, 'removeEventListener')
    const wrapper = mount(ProfileChart, { props: { points } })
    await flushPromises()
    wrapper.unmount()

    expect(disconnect).toHaveBeenCalledTimes(1)
    expect(removeEventListener).toHaveBeenCalledWith('resize', expect.any(Function))
    expect(echartsMocks.dispose).toHaveBeenCalledTimes(1)
  })
})
