// Capture real app screenshots for the /about splash page.
// Usage: BASE=http://localhost:8000 PHONE=+1555... CODE=000000 node scripts/capture-about.mjs
// Requires the server running with DEV_AUTH_BYPASS=1.
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const BASE = process.env.BASE ?? 'http://localhost:8000'
const PHONE = process.env.PHONE ?? ''
const CODE = process.env.CODE ?? '000000'
const OUT = join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'assets', 'about')
mkdirSync(OUT, { recursive: true })

// login via API, grab the session cookie
await fetch(`${BASE}/api/auth/request-otp`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ phone: PHONE }),
})
const verify = await fetch(`${BASE}/api/auth/verify`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ phone: PHONE, code: CODE }),
})
const setCookie = verify.headers.get('set-cookie') ?? ''
const m = setCookie.match(/bra_session=([^;]+)/)
if (!m) throw new Error(`login failed: ${verify.status} ${setCookie}`)

const browser = await chromium.launch()
const ctx = await browser.newContext({
  viewport: { width: 1280, height: 800 },
  deviceScaleFactor: 2,
})
await ctx.addCookies([{ name: 'bra_session', value: m[1], url: BASE }])
const page = await ctx.newPage()

const shot = (name) =>
  page.screenshot({ path: join(OUT, `${name}.jpg`), type: 'jpeg', quality: 80 })

// Home: hero + stats + discover grid
await page.goto(`${BASE}/`, { waitUntil: 'networkidle' })
await page.waitForSelector('.grid .card', { timeout: 20000 })
await shot('home')

// Semantic search results
await page.goto(`${BASE}/search?q=${encodeURIComponent('documentary filmmaker')}`, { waitUntil: 'networkidle' })
await page.waitForSelector('.grid .card', { timeout: 30000 })
await shot('search')

// Profile: a vivid alumnus profile where header + interests + page receipts fit one screen
await page.setViewportSize({ width: 1280, height: 1040 })
await page.goto(`${BASE}/p/${encodeURIComponent('bobby ng|2003')}`, { waitUntil: 'networkidle' })
await page.waitForSelector('.profile-head', { timeout: 20000 })
await page.waitForSelector('.featured img', { timeout: 20000 })
await page.waitForTimeout(500)
await shot('profile')
await page.setViewportSize({ width: 1280, height: 800 })

// Directory
await page.goto(`${BASE}/browse`, { waitUntil: 'networkidle' })
await page.waitForSelector('.dirgrid .dcard, table.dirtable', { timeout: 20000 })
await shot('browse')

// Assistant: biotech group with matches + reasoning
await page.goto(`${BASE}/assistant?g=7`, { waitUntil: 'networkidle' })
await page.waitForSelector('.match', { timeout: 20000 })
await shot('assistant')

// Shuffle deck: pick the first theme chip if none active
await page.goto(`${BASE}/shuffle`, { waitUntil: 'networkidle' })
const hasCard = await page.$('.swipe-card')
if (!hasCard) {
  await page.click('.chip')
  await page.waitForSelector('.swipe-card', { timeout: 20000 })
}
await page.waitForTimeout(800)
await shot('shuffle')

await browser.close()
console.log(`saved 6 screenshots to ${OUT}`)
