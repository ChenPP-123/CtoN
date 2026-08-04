async function get(path) {
  const response = await fetch(`/api/v1${path}`)
  const payload = await response.json()
  if (!response.ok) throw new Error(payload.message || `请求失败（${response.status}）`)
  return payload.data
}

async function post(path) {
  const response = await fetch(`/api/v1${path}`, { method: 'POST' })
  const payload = await response.json()
  if (!response.ok) throw new Error(payload.message || `请求失败（${response.status}）`)
  return payload.data
}

export const api = {
  getRoute: (routeId) => get(`/routes/${routeId}`),
  getWeather: (cityId) => get(`/cities/${cityId}/weather`),
  getProfile: (routeId) => get(`/routes/${routeId}/weather-profile`),
  getRandomTrip: (routeId) => get(`/routes/${routeId}/random-trip`),
  getTravelAdvice: (routeId) => get(`/routes/${routeId}/travel-advice`),
  refreshWeather: () => post('/weather/refresh'),
  generateTravelAdvice: (routeId) => post(`/routes/${routeId}/travel-advice`),
}
