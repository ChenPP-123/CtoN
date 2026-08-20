function backendOrigin(environment) {
  const value = environment.BACKEND_ORIGIN?.trim().replace(/\/+$/, '')
  if (!value) throw new Error('BACKEND_ORIGIN is required')

  const url = new URL(value)
  if (url.protocol !== 'https:' || url.pathname !== '/' || url.search || url.hash) {
    throw new Error('BACKEND_ORIGIN must be an HTTPS origin without a path')
  }
  return value
}

export function createVercelConfig(environment = process.env) {
  const origin = backendOrigin(environment)
  return {
    framework: 'vite',
    rewrites: [
      { source: '/api/:path*', destination: `${origin}/api/:path*` },
      { source: '/_AMapService/:path*', destination: `${origin}/_AMapService/:path*` },
      { source: '/:path*', destination: '/index.html' },
    ],
    headers: [
      {
        source: '/assets/:path*',
        headers: [{ key: 'Cache-Control', value: 'public, max-age=31536000, immutable' }],
      },
      {
        source: '/weather/:path*',
        headers: [{ key: 'Cache-Control', value: 'public, max-age=2592000' }],
      },
    ],
  }
}

export const config = createVercelConfig()
