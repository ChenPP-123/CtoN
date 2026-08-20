import { beforeAll, describe, expect, it } from 'vitest'


let createVercelConfig

beforeAll(async () => {
  process.env.BACKEND_ORIGIN = 'https://cton-api.vercel.app'
  ;({ createVercelConfig } = await import('./vercel.mjs'))
})

describe('Vercel routing configuration', () => {
  it('requires the backend origin', () => {
    expect(() => createVercelConfig({})).toThrow('BACKEND_ORIGIN is required')
  })

  it('proxies API and AMap paths before the SPA fallback', () => {
    const config = createVercelConfig({
      BACKEND_ORIGIN: 'https://cton-api.vercel.app/',
    })

    expect(config.rewrites).toEqual([
      {
        source: '/api/:path*',
        destination: 'https://cton-api.vercel.app/api/:path*',
      },
      {
        source: '/_AMapService/:path*',
        destination: 'https://cton-api.vercel.app/_AMapService/:path*',
      },
      { source: '/:path*', destination: '/index.html' },
    ])
  })
})
