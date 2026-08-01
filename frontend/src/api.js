async function get(path) {
  const response = await fetch(`/api/v1${path}`)
  if (!response.ok) throw new Error(`请求失败（${response.status}）`)
  const payload = await response.json()
  return payload.data
}

export const api = {
  getRoute: (routeId) => get(`/routes/${routeId}`),
  getWeather: (cityId) => get(`/cities/${cityId}/weather`),
  getProfile: (routeId) => get(`/routes/${routeId}/weather-profile`),
  generatePoem: async (cityId) => {
    const response = await fetch(`/api/v1/cities/${cityId}/poem`, { method: 'POST' })
    if (!response.ok) {
      const payload = await response.json().catch(() => null)
      throw new Error(payload?.message || `生成失败（${response.status}）`)
    }
    return (await response.json()).data
  },
  refreshWeather: async () => {
    const response = await fetch('/api/v1/weather/refresh', { method: 'POST' })
    if (!response.ok) throw new Error(`更新失败（${response.status}）`)
    return (await response.json()).data
  },
}
