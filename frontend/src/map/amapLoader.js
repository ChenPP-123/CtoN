let loadingPromise

export function loadAMap() {
  const key = import.meta.env.VITE_AMAP_JS_KEY
  if (!key) return Promise.reject(new Error('未配置 VITE_AMAP_JS_KEY'))
  if (window.AMap) return Promise.resolve(window.AMap)
  if (loadingPromise) return loadingPromise

  window._AMapSecurityConfig = { serviceHost: '/_AMapService' }
  loadingPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(key)}`
    script.async = true
    script.onload = () => window.AMap ? resolve(window.AMap) : reject(new Error('高德地图脚本未提供 AMap 对象'))
    script.onerror = () => reject(new Error('高德地图脚本加载失败'))
    document.head.append(script)
  })
  return loadingPromise
}
