import { readdir, stat } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { cityVisuals } from '../src/content/cityVisuals.js'


const frontendDirectory = join(dirname(fileURLToPath(import.meta.url)), '..')
const ignoredNames = new Set(['.env', '.vercel', 'coverage', 'dist', 'node_modules'])
const uploadLimitBytes = 100 * 1024 * 1024

async function deploymentSourceSize(directory) {
  let totalBytes = 0
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if (ignoredNames.has(entry.name) || entry.name.startsWith('.env.')) continue
    const path = join(directory, entry.name)
    totalBytes += entry.isDirectory() ? await deploymentSourceSize(path) : (await stat(path)).size
  }
  return totalBytes
}

for (const visual of Object.values(cityVisuals)) {
  for (const file of Object.keys(visual.scenes)) {
    if (!file.endsWith('.webp')) throw new Error(`Weather image must use WebP: ${file}`)
    const imagePath = join(frontendDirectory, 'public', 'weather', visual.slug, file)
    try {
      await stat(imagePath)
    } catch {
      throw new Error(`Referenced weather image does not exist: ${imagePath}`)
    }
  }
}

const sourceSizeBytes = await deploymentSourceSize(frontendDirectory)
if (sourceSizeBytes >= uploadLimitBytes) {
  throw new Error(`Frontend deployment source is ${sourceSizeBytes} bytes; limit is ${uploadLimitBytes}`)
}

console.log(`Frontend deployment source check passed: ${(sourceSizeBytes / 1024 / 1024).toFixed(1)} MiB`)
