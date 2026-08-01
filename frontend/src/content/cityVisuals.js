const cityVisuals = {
  重庆: {
    slug: 'chongqing', phrase: '江峡叠城，云雨巴渝', textTone: 'light', primary: '#d97847', accent: '#f5c76f', overlay: .46,
    files: ['winter-fog.png', 'summer-storm.png', 'autumn-clear.png', 'spring-fog.png', 'spring-rain.png', 'summer-clear.png'],
  },
  万州: {
    slug: 'wanzhou', phrase: '江城入峡，平湖万州', textTone: 'light', primary: '#6f8e97', accent: '#d9c477', overlay: .42,
    files: ['winter-fog.png', 'summer-storm.png', 'autumn-clear.png', 'summer-clear.png', 'spring-rain-fog.png'],
  },
  恩施: {
    slug: 'enshi', phrase: '绝壁云栖，山川清嘉', textTone: 'light', primary: '#577c69', accent: '#cdd880', overlay: .45,
    files: ['summer-storm.png', 'autumn-clear.png', 'spring-rain-cloud.png', 'winter-rain-cloud.png', 'summer-clear.png'],
  },
  宜昌: {
    slug: 'yichang', phrase: '三峡门户，江阔山青', textTone: 'light', primary: '#507f91', accent: '#e4c168', overlay: .42,
    files: ['spring-clear.png', 'autumn-clear.png', 'summer-rain.png', 'winter-fog-rain.png', 'summer-clear.png'],
  },
  荆州: {
    slug: 'jingzhou', phrase: '古城临水，楚韵平畴', textTone: 'light', primary: '#847c4f', accent: '#e7c671', overlay: .43,
    files: ['winter-fog.png', 'spring-clear.png', 'autumn-clear.png', 'summer-rain.png', 'summer-clear.png'],
  },
  武汉: {
    slug: 'wuhan', phrase: '两江交汇，百湖晴热', textTone: 'light', primary: '#b06e52', accent: '#f0c875', overlay: .45,
    files: ['spring-clear.png', 'autumn-clear.png', 'summer-rain.png', 'summer-clear.png', 'winter-rain.png'],
  },
  合肥: {
    slug: 'hefei', phrase: '湖光润城，淮风和畅', textTone: 'light', primary: '#5f8990', accent: '#dfcc82', overlay: .41,
    files: ['spring-clear.png', 'summer-storm.png', 'autumn-clear.png', 'summer-rain.png'],
  },
  南京: {
    slug: 'nanjing', phrase: '山水金陵，六朝烟雨', textTone: 'light', primary: '#8a715c', accent: '#ead080', overlay: .44,
    files: ['spring-clear.png', 'autumn-clear.png', 'summer-rain.png', 'summer-clear.png', 'winter-rain.png'],
  },
}

function seasonFor(date) {
  const month = date ? new Date(`${date}T12:00:00`).getMonth() + 1 : new Date().getMonth() + 1
  if (month >= 3 && month <= 5) return 'spring'
  if (month >= 6 && month <= 8) return 'summer'
  if (month >= 9 && month <= 11) return 'autumn'
  return 'winter'
}

function weatherKind(text = '') {
  if (/雷|暴/.test(text)) return 'storm'
  if (/雾|霾/.test(text)) return 'fog'
  if (/雨|雪/.test(text)) return 'rain'
  if (/云|阴/.test(text)) return 'cloud'
  if (/晴/.test(text)) return 'clear'
  return ''
}

export function visualForCity(cityName, weatherText, date) {
  const visual = cityVisuals[cityName] || cityVisuals.重庆
  const season = seasonFor(date)
  const exactFile = `${season}-${weatherKind(weatherText)}.png`
  const normal = `${season}-normal.png`
  const file = visual.files.includes(exactFile) ? exactFile : normal
  const image = `/weather/${visual.slug}/${file}`
  const fallbackImage = `/weather/${visual.slug}/${normal}`
  return { ...visual, season, image, fallbackImage, gradient: `linear-gradient(135deg, ${visual.primary}, #172c32 82%)` }
}
