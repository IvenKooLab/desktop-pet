/** DSH web overlay host half. Reuses the repository's approved PNG assets.
 * The event inbox is single-consumer, so the overlay keeps its own reducer and
 * never removes files that the standalone app still needs to consume.
 */
import { readFileSync, writeFileSync, renameSync, mkdirSync } from 'node:fs'
import { dirname, resolve, basename } from 'node:path'
import { fileURLToPath } from 'node:url'
import { isTrustedApiRequest } from './trust-fence.js'

export const PREFIX = '/iven-pet'
export const LEASE_MS = 30_000
const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
const clean = (value, limit = 80) => typeof value === 'string'
  ? value.replace(/[\x00-\x1f\x7f]/g, ' ').trim().slice(0, limit) : ''

export function readDisplay(path, now = Date.now()) {
  try {
    const value = JSON.parse(readFileSync(path, 'utf8'))
    if (value?.version === 1 && value.owner === 'dsh' && value.mode === 'embedded'
      && Number.isFinite(value.lease_until) && value.lease_until > now && value.lease_until <= now + 35_000) {
      return { version: 1, owner: 'dsh', mode: 'embedded', lease_until: value.lease_until,
        client_id: clean(value.client_id, 96) || null }
    }
  } catch { /* absent/corrupt/expired means standalone stays visible */ }
  return { version: 1, owner: 'dsh', mode: 'desktop', lease_until: 0, client_id: null }
}

export function writeDisplay(path, mode, clientId, now = Date.now()) {
  const value = { version: 1, owner: 'dsh', mode, lease_until: mode === 'embedded' ? now + LEASE_MS : 0,
    client_id: mode === 'embedded' ? clientId : null }
  mkdirSync(dirname(path), { recursive: true })
  const tmp = `${path}.tmp-${process.pid}-${Math.random().toString(16).slice(2)}`
  writeFileSync(tmp, JSON.stringify(value))
  renameSync(tmp, path)
  return value
}

export function reduceSession(sessions, id, event, label, now = Date.now()) {
  const session = sessions.get(id) ?? { phase: 'idle', label: '', tool: '', updated: now, phaseSince: now, order: 0, id }
  const previousPhase = session.phase
  session.updated = now
  session.order++
  if (event.kind === 'turn.started') Object.assign(session, { phase: 'working', label: '', tool: '' })
  if (label) session.label = clean(label)
  if (event.kind === 'tool.started') Object.assign(session, { phase: 'working', tool: clean(event.toolName, 48) })
  if (event.kind === 'permission.required') session.phase = 'waiting'
  if (event.kind === 'tool.finished') session.phase = 'working'
  if (['turn.ended', 'task.completed', 'turn.failed', 'interrupted', 'session.ended'].includes(event.kind)) {
    session.phase = event.kind === 'task.completed' ? 'success' : event.kind === 'turn.failed' ? 'failed' : 'idle'
    session.tool = ''
  }
  if (session.phase !== previousPhase || event.kind === 'turn.started') session.phaseSince = now
  sessions.set(id, session)
  for (const [key, value] of sessions) if (now - value.updated > 1_200_000) sessions.delete(key)
}

export function currentSession(sessions, now = Date.now()) {
  const all = [...sessions.values()].filter(s => now - s.updated <= 900_000)
  all.sort((a, b) => Number(b.phase === 'waiting') - Number(a.phase === 'waiting') || b.updated - a.updated)
  const active = all.find(s => ['working', 'waiting'].includes(s.phase))
  const selected = active ?? all[0]
  if (!selected) return { phase: 'idle', label: '', tool: '' }
  if (['success', 'failed'].includes(selected.phase) && now - selected.updated > 7_000) {
    return { phase: 'idle', label: '', tool: '' }
  }
  return { phase: selected.phase, label: selected.label, tool: selected.tool,
    session_id: selected.id, phase_since: selected.phaseSince }
}

function json(res, code, value) {
  res.writeHead(code, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' })
  res.end(JSON.stringify(value))
}

async function readBody(req) {
  return new Promise((resolveBody, reject) => {
    let text = '', exceeded = false
    req.on('data', chunk => {
      if (exceeded) return
      text += chunk.toString('utf8')
      if (text.length > 4096) { exceeded = true; text = ''; reject(new Error('body too large')) }
    })
    req.on('end', () => {
      if (exceeded) return
      try { resolveBody(JSON.parse(text || '{}')) } catch { reject(new Error('invalid JSON')) }
    })
    req.on('error', reject)
  })
}

export function createRouteHandler({ eventsDir, root = ROOT, sessions = new Map(), trustedHosts = () => [], clock = Date.now }) {
  const displayPath = resolve(dirname(eventsDir), 'display.json')
  const manifestPath = resolve(root, 'frames3d/animation.json')
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))
  const frames = new Set(Object.values(manifest.clips).flatMap(clip => clip.frames))
  return async function handler(req, res) {
    if (!isTrustedApiRequest(req, trustedHosts())) return json(res, 403, { ok: false, error: 'forbidden' })
    const path = new URL(req.url ?? '/', 'http://dsh.internal').pathname
    if (req.method === 'GET' && path === `${PREFIX}/api/state`) {
      return json(res, 200, { ok: true, display: readDisplay(displayPath, clock()), state: currentSession(sessions, clock()) })
    }
    if (req.method === 'GET' && path === `${PREFIX}/api/manifest`) return json(res, 200, manifest)
    if (req.method === 'GET' && path === `${PREFIX}/api/behaviors`) {
      try { return json(res, 200, JSON.parse(readFileSync(resolve(root, 'animation_behaviors.json'), 'utf8'))) }
      catch { return json(res, 200, { version: 1, actions: {} }) }
    }
    if (req.method === 'GET' && path.startsWith(`${PREFIX}/frames/`)) {
      const file = path.slice(`${PREFIX}/frames/`.length)
      const name = file.endsWith('.png') ? file.slice(0, -4) : ''
      if (!name || basename(file) !== file || !frames.has(name)) return json(res, 404, { ok: false, error: 'unknown frame' })
      try {
        const data = readFileSync(resolve(root, 'frames3d', file))
        res.writeHead(200, { 'content-type': 'image/png', 'cache-control': 'public, max-age=3600' })
        return res.end(data)
      } catch { return json(res, 404, { ok: false, error: 'missing frame' }) }
    }
    if (req.method === 'POST' && [`${PREFIX}/api/display`, `${PREFIX}/api/heartbeat`].includes(path)) {
      let body
      try { body = await readBody(req) } catch { return json(res, 400, { ok: false, error: 'invalid body' }) }
      const clientId = clean(body?.client_id, 96)
      if (!/^[a-zA-Z0-9_-]{8,96}$/.test(clientId)) return json(res, 400, { ok: false, error: 'invalid client id' })
      const current = readDisplay(displayPath, clock())
      const heartbeat = path.endsWith('/heartbeat')
      if (heartbeat && (current.mode !== 'embedded' || (current.client_id && current.client_id !== clientId))) {
        return json(res, 409, { ok: false, display: current, error: 'lease not owned' })
      }
      if (!heartbeat && !['embedded', 'desktop'].includes(body.mode)) return json(res, 400, { ok: false, error: 'invalid mode' })
      // Explicit mode selection can take over; an ordinary heartbeat cannot.
      const display = writeDisplay(displayPath, heartbeat ? 'embedded' : body.mode, clientId, clock())
      return json(res, 200, { ok: true, display })
    }
    return json(res, 404, { ok: false, error: 'not found' })
  }
}

export function createWebIntegration(ctx, options) {
  const sessions = new Map()
  if (typeof ctx.inject === 'function') ctx.inject(['webServer'], wctx => {
    wctx.effect(() => wctx.webServer.register({
      kind: 'prefix', path: PREFIX,
      handler: createRouteHandler({ ...options, sessions, trustedHosts: () => wctx.webRuntime?.trustedHosts ?? [] }),
    }), 'iven-bridge: approved pet frames and display lease')
  })
  return { record: (id, event, label) => reduceSession(sessions, id, event, label) }
}
