import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from './api'

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve({ data: { ok: true } }),
  }))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('API 路由契约', () => {
  it.each([
    ['线路', () => api.getRoute(3), '/api/v1/routes/3', undefined],
    ['城市天气', () => api.getWeather(4), '/api/v1/cities/4/weather', undefined],
    ['气象剖面', () => api.getProfile(3), '/api/v1/routes/3/weather-profile', undefined],
    ['随机旅行', () => api.getRandomTrip(3), '/api/v1/routes/3/random-trip', undefined],
    ['行路建议', () => api.getTravelAdvice(3), '/api/v1/routes/3/travel-advice', undefined],
  ])('%s 请求正确的后端路径', async (_name, request, path, options) => {
    await expect(request()).resolves.toEqual({ ok: true })
    expect(fetch).toHaveBeenCalledWith(path, ...(options ? [options] : []))
  })

  it('将后端错误信息传递给界面', async () => {
    fetch.mockResolvedValueOnce({
      ok: false,
      status: 503,
      json: () => Promise.resolve({ message: '天气服务暂不可用' }),
    })

    await expect(api.getWeather(3)).rejects.toThrow('天气服务暂不可用')
  })

  it('公开 API 客户端没有写操作或管理员令牌', () => {
    expect(Object.keys(api)).toEqual([
      'getRoute',
      'getWeather',
      'getProfile',
      'getRandomTrip',
      'getTravelAdvice',
    ])
  })
})
