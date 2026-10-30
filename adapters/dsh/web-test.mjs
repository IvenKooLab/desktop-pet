// Hermetic host/overlay tests: no real DSH, API keys, browser or bound port.
import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import { mkdtempSync, rmSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createRouteHandler, readDisplay, writeDisplay, reduceSession, currentSession, LEASE_MS } from './comi-bridge/web.js'
import { isTrustedApiRequest } from './comi-bridge/trust-fence.js'
import vm from 'node:vm'
import { dataRoot } from './comi-bridge/data-home.js'
import { resolveChatDir } from './comi-bridge/chat-host.js'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const temp = mkdtempSync(join(tmpdir(), 'comi-overlay-'))
let now = 1_800_000_000_000
let checks = 0
const ok = (value, message) => { assert.ok(value, message); checks++ }
try {
  const displayPath = join(temp, 'display.json')
  const sessions = new Map()
  const handler = createRouteHandler({ eventsDir: join(temp, 'events'), root, sessions, clock: () => now })
  const call = async (method, url, body, extraHeaders = {}) => {
    const req = new EventEmitter()
    req.method = method; req.url = url
    req.headers = { host: '127.0.0.1:3080', ...extraHeaders }
    let status, headers, data
    const res = { writeHead(code, fields) { status = code; headers = fields }, end(value) { data = value } }
    const pending = handler(req, res)
    if (body !== undefined) { req.emit('data', Buffer.from(typeof body === 'string' ? body : JSON.stringify(body))); req.emit('end') }
    await pending
    return { status, headers, data, json: () => JSON.parse(data) }
  }
  ok(readDisplay(displayPath, now).mode === 'desktop', 'missing display never hides native pet')
  writeFileSync(displayPath, '{broken')
  ok(readDisplay(displayPath, now).mode === 'desktop', 'invalid JSON is safe')
  writeFileSync(displayPath, JSON.stringify({ version: 1, owner: 'dsh', mode: 'embedded', lease_until: now + 999_999 }))
  ok(readDisplay(displayPath, now).mode === 'desktop', 'unbounded future lease is refused')
  writeDisplay(displayPath, 'embedded', null, now)
  let result = await call('POST', '/comi-pet/api/heartbeat', { client_id: 'browser_a' })
  ok(result.status === 200 && result.json().display.client_id === 'browser_a', 'first DSH tab claims native menu intent')
  result = await call('POST', '/comi-pet/api/heartbeat', { client_id: 'browser_b' })
  ok(result.status === 409, 'second tab cannot steal heartbeat lease')
  result = await call('GET', '/comi-pet/api/state')
  ok(result.json().display.lease_until === now + LEASE_MS, '60-second renewable lease returned')
  now += 61_000
  result = await call('GET', '/comi-pet/api/state')
  ok(result.json().display.mode === 'desktop', 'lost browser recovers independent desktop')
  result = await call('POST', '/comi-pet/api/heartbeat', { client_id: 'browser_a' })
  ok(result.status === 409, 'expired heartbeat cannot re-hide independent pet')
  result = await call('POST', '/comi-pet/api/display', { client_id: 'browser_b', mode: 'embedded' })
  ok(result.status === 200 && result.json().display.client_id === 'browser_b', 'explicit mode selection may transfer tabs')
  result = await call('POST', '/comi-pet/api/display', { client_id: 'browser_b', mode: 'desktop' })
  ok(result.status === 200 && readDisplay(displayPath, now).mode === 'desktop', 'desktop selection releases lease')
  result = await call('POST', '/comi-pet/api/display', { client_id: 'browser_b', mode: 'forever-hidden' })
  ok(result.status === 400, 'unknown display mode refused')
  result = await call('POST', '/comi-pet/api/display', 'x'.repeat(5000))
  ok(result.status === 400, 'oversized body refused')
  result = await call('POST', '/comi-pet/api/display', { client_id: 'browser_b', mode: 'embedded' }, { origin: 'https://evil.example' })
  ok(result.status === 403, 'cross-origin display mutation refused')
  ok(!isTrustedApiRequest({ headers: { host: '127.0.0.1:3080', origin: 'http://127.0.0.1:4000' } }), 'different-port origin refused')
  ok(!isTrustedApiRequest({ headers: { host: 'evil.example' } }), 'DNS rebinding Host refused')
  ok(!isTrustedApiRequest({ headers: { host: 'localhost:3080', 'sec-fetch-site': 'cross-site' } }), 'cross-site browser marker refused')
  ok(isTrustedApiRequest({ headers: { host: 'harness.local:3080', origin: 'http://harness.local:3080' } }, ['harness.local:3080']), 'explicit trusted deployment accepted')
  result = await call('GET', '/comi-pet/api/manifest')
  ok(result.status === 200 && result.json().clips.STRETCH.frames.length > 0, 'approved animation manifest served')
  result = await call('GET', '/comi-pet/frames/idle_0.png')
  ok(result.status === 200 && result.headers['content-type'] === 'image/png' && Buffer.isBuffer(result.data), 'approved transparent PNG served')
  result = await call('GET', '/comi-pet/frames/package.json.png')
  ok(result.status === 404, 'non-manifest file refused')
  result = await call('GET', '/comi-pet/frames/fall_0.png')
  ok(result.status === 200, 'runtime-synthesized fall frame is served for web fling physics')
  result = await call('GET', '/comi-pet/frames/land_0.png')
  ok(result.status === 200, 'runtime-synthesized land frame is served for web landing')
  const appVersion = readFileSync(join(root, 'VERSION'), 'utf8').trim()
  result = await call('GET', '/comi-pet/api/state')
  ok(typeof result.json().language === 'string' && result.json().version === appVersion,
     'state exposes language preference and app version for web menu parity')
  result = await call('POST', '/comi-pet/api/language', { value: 'zh' })
  ok(result.status === 200 && result.json().language === 'zh', 'language preference can be set from the web menu')
  result = await call('POST', '/comi-pet/api/language', { value: 'klingon' })
  ok(result.status === 400, 'invalid language values refused')
  result = await call('GET', '/comi-pet/frames/%2e%2e%2fpackage.json.png')
  ok(result.status === 404, 'encoded traversal refused')
  reduceSession(sessions, 's1', { kind: 'turn.started' }, undefined, now)
  reduceSession(sessions, 's1', { kind: 'tool.started', toolName: 'Read' }, '  Inspect\nproject ', now + 1)
  reduceSession(sessions, 's2', { kind: 'permission.required' }, undefined, now + 2)
  ok(currentSession(sessions, now + 3).phase === 'waiting', 'approval priority across DSH sessions')
  reduceSession(sessions, 's2', { kind: 'task.updated' }, 'Waiting task label', now + 10)
  ok(currentSession(sessions, now + 11).phase_since === now + 2, 'waiting clock survives label and status polling updates')
  reduceSession(sessions, 's2', { kind: 'turn.ended' }, undefined, now + 4)
  ok(currentSession(sessions, now + 5).phase === 'working' && currentSession(sessions, now + 5).label === 'Inspect project', 'other working session survives one turn ending')
  reduceSession(sessions, 's1', { kind: 'turn.ended' }, undefined, now + 6)
  ok(currentSession(sessions, now + 7).phase === 'idle', 'turn end is not task success')
  reduceSession(sessions, 's1', { kind: 'task.completed' }, undefined, now + 8)
  ok(currentSession(sessions, now + 9).phase === 'success', 'explicit goal completion celebrates')
  ok(currentSession(sessions, now + 8009).phase === 'idle', 'terminal result expires instead of looping forever')

  // Custom roots must be identical for events, chat and the native/Python consumers.
  const envKeys = ['COMI_HOME', 'IVEN_HOME', 'COMI_CHAT_DIR', 'IVEN_CHAT_DIR']
  const savedEnv = Object.fromEntries(envKeys.map(key => [key, process.env[key]]))
  try {
    for (const key of envKeys) delete process.env[key]
    process.env.IVEN_HOME = join(temp, 'old-custom-root')
    ok(dataRoot() === process.env.IVEN_HOME, 'legacy root override remains supported')
    ok(resolveChatDir() === join(process.env.IVEN_HOME, 'chat'), 'chat follows the custom root')
    process.env.COMI_HOME = join(temp, 'new-custom-root')
    ok(dataRoot() === process.env.COMI_HOME, 'new root override takes precedence')
    ok(resolveChatDir() === join(process.env.COMI_HOME, 'chat'), 'chat stays with events after root override')
    process.env.COMI_CHAT_DIR = join(temp, 'explicit-chat')
    ok(resolveChatDir() === process.env.COMI_CHAT_DIR, 'specific chat override still wins')
  } finally {
    for (const key of envKeys) {
      if (savedEnv[key] === undefined) delete process.env[key]
      else process.env[key] = savedEnv[key]
    }
  }

  // Verify the real DSH loader contract without a DOM or duplicating its internals.
  let moduleInfo, registration
  const clientCode = readFileSync(new URL('./comi-bridge/client.js', import.meta.url), 'utf8')
  vm.runInNewContext(clientCode, { navigator: { language: 'en' }, window: { __ModuleLoader__: { load(info) { moduleInfo = info } } } })
  const plugin = moduleInfo.factory(name => {
    assert.equal(name, 'react')
    return { createElement: (type, props) => ({ type, props }) }
  })
  const slots = {
    inject(name, generator) { assert.equal(name, 'shell.overlay'); [...generator()] },
    register(info, component) { registration = { info, component }; return () => {} },
  }
  plugin.apply({ slots })
  ok(moduleInfo.id === 'comi-bridge' && plugin.inject.includes('slots') && registration.info.name === 'shell.overlay', 'official shell.overlay registered through ModuleLoader factory')

  // Run the production React component/RAF scheduler with actual exported
  // timelines. This catches native/browser behavior drifting independently.
  const realManifest = JSON.parse(readFileSync(join(root, 'frames3d/animation.json'), 'utf8'))
  const realBehaviors = JSON.parse(readFileSync(join(root, 'animation_behaviors.json'), 'utf8'))
  const simulate = (initialHost, { language = 'en', random = Math.random } = {}) => {
    let callback, time = 0, hook = 0, refIndex = 0, module, mounted
    const refs = [], effects = []
    const fakeImage = { src: '', dataset: {}, style: {}, className: '' }, fakeCard = { style: {} }
    const host = { session_id: 'test-session', phase_since: now, label: '', tool: '', ...initialHost }
    class ClockDate extends Date { static now() { return now + time } }
    const react = {
      createElement: (type, props, ...children) => ({ type, props: { ...props, children } }),
      useState(initial) {
        const states = [{ mode: 'embedded', client_id: 'browser_test', lease_until: now + 30_000 }, host, realManifest, '', now, true]
        return [states[hook++] ?? initial, () => {}]
      },
      useRef(initial) {
        const index = refIndex++
        const overrides = { 0: fakeImage, 1: fakeCard, 3: realManifest, 4: realBehaviors }
        const value = { current: Object.hasOwn(overrides, index) ? overrides[index] : initial }
        refs.push(value); return value
      },
      useEffect(effect) { effects.push(effect) },
    }
    const context = {
      navigator: { language }, sessionStorage: { getItem: () => 'browser_test' },
      window: { __ModuleLoader__: { load(info) { module = info } } },
      innerWidth: 1000, innerHeight: 800, Date: ClockDate,
      Math: Object.assign(Object.create(Math), { random }),
      performance: { now: () => time }, requestAnimationFrame: fn => { callback = fn; return 1 }, cancelAnimationFrame: () => { callback = null },
      setTimeout: () => 1, clearTimeout: () => {},
    }
    vm.runInNewContext(clientCode, context)
    const componentPlugin = module.factory(() => react)
    componentPlugin.apply({ slots: { inject(_name, gen) { [...gen()] }, register(_info, Component) { mounted = Component; return () => {} } } })
    const element = mounted()
    const tree = element.type(element.props)
    effects[1]() // real animation useEffect; skip network-polling effect
    const step = (milliseconds = 100) => { time += milliseconds; callback(time); return fakeImage.dataset.animation }
    const advance = milliseconds => { for (let elapsed = 0; elapsed < milliseconds; elapsed += 100) step(Math.min(100, milliseconds - elapsed)); return fakeImage.dataset.animation }
    return { step, advance, refs, host, fakeImage, tree }
  }
  const working = simulate({ phase: 'working' })
  ok(working.step() === 'WORK', 'DSH work begins with one clapperboard cycle')
  ok(working.advance(1200) === 'THINKING', 'DSH work changes to long thinking theme after one cycle')
  let workReturned = false
  for (let tick = 0; tick < 160; tick++) if (working.step() === 'WORK') { workReturned = true; break }
  ok(workReturned, 'long thinking timeline returns to one WORK cycle')
  const waiting = simulate({ phase: 'waiting' })
  ok(waiting.step() === 'WAITING', 'waiting starts calmly')
  ok(waiting.advance(30_000) === 'IMPATIENT', 'same session waiting becomes impatient after 30 seconds')
  waiting.host.phase_since = now + 30_100
  waiting.step()
  ok(waiting.fakeImage.dataset.animation === 'WAITING', 'new waiting phase resets the impatient timer')
  const success = simulate({ phase: 'success' })
  ok(success.step() === 'RELIEVED', 'success plays relief instead of repeated clapperboard')
  success.advance(7000); success.host.phase = 'idle'; success.host.phase_since = now + 7100
  ok(success.step() === 'RELIEVED', 'relief finishes even when the result card expires at seven seconds')
  const manual = simulate({ phase: 'idle' })
  manual.refs[8].current = 'TOKEN_LOW'
  ok(manual.step() === 'TOKEN_LOW', 'quota theme is available for manual performance')
  const autoplay = simulate({ phase: 'idle' })
  let falselyLow = false
  for (let tick = 0; tick < 10_000; tick++) if (autoplay.step() === 'TOKEN_LOW') { falselyLow = true; break }
  ok(!falselyLow, 'autoplay never fabricates a low-token account state')

  // Exercise the actual menu callbacks and idle scheduler: a registered manifest
  // clip alone is insufficient if the browser's labels/menu omit its action ID.
  const halloween = {
    TRICK_OR_TREAT: ['不给糖就捣蛋', 'Trick or treat'],
    GHOST_SHEET: ['白布幽灵', 'Ghost sheet'],
    VAMPIRE_CAPE: ['吸血鬼披风亮相', 'Vampire cape'],
    WITCH_SPELL: ['小女巫施法', 'Witch spell'],
    BLACK_CAT: ['黑猫', 'Black cat'],
  }
  const findMenuItem = (node, key) => {
    if (!node || typeof node !== 'object') return null
    if (node.props?.key === key) return node
    for (const child of node.props?.children || []) {
      const found = findMenuItem(child, key)
      if (found) return found
    }
    return null
  }
  for (const language of ['zh', 'en']) {
    const themed = simulate({ phase: 'idle' }, { language })
    const life = findMenuItem(themed.tree, 'LITTLE_BREAKS')
    const actions = findMenuItem(themed.tree, 'ACTIONS')
    const holidays = findMenuItem(actions, 'HOLIDAYS')
    const itemText = item => item?.props?.children.filter(child => typeof child === 'string').join('')
    ok(itemText(holidays) === (language === 'zh' ? '节日' : 'Holidays'), `${language}: holidays is nested under actions`)
    ok(!findMenuItem(holidays, 'HALLOWEEN'), `${language}: holidays has no extra Halloween submenu`)
    for (const [name, labels] of Object.entries(halloween)) {
      const item = findMenuItem(holidays, name)
      ok(itemText(item) === labels[language === 'zh' ? 0 : 1], `${language}: ${name} is labeled directly inside holidays`)
      ok(!findMenuItem(life, name), `${language}: ${name} is absent from little breaks`)
      item.props.onClick()
      ok(themed.step() === name, `${language}: ${name} menu click plays the registered clip`)
    }
  }
  let seed = 1
  const random = () => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed / 4294967296 }
  const seasonalAutoplay = simulate({ phase: 'idle' }, { random })
  const seenSeasonal = new Set()
  for (let tick = 0; tick < 100_000 && seenSeasonal.size < 5; tick++) {
    const clip = seasonalAutoplay.step()
    if (Object.hasOwn(halloween, clip)) seenSeasonal.add(clip)
  }
  ok(seenSeasonal.size === 5, 'idle autoplay can select all five Halloween clips from the real browser action list')

  const asleep = simulate({ phase: 'idle' })
  asleep.step(); asleep.refs[8].current = 'SLEEP'; asleep.step()
  ok(asleep.advance(40_000) === 'SLEEP', 'manual sleep persists beyond its animation cycle')
  asleep.host.phase = 'working'; asleep.host.phase_since = now + 40_100
  ok(asleep.step() === 'SLEEP', 'host changes do not wake an explicitly sleeping pet')
  asleep.refs[8].current = 'IDLE'
  ok(asleep.step() !== 'SLEEP', 'explicit wake releases sleep')
  const paused = simulate({ phase: 'idle' })
  paused.refs[10].current = false // autoplayRef: pausing does not loop a manual action forever
  paused.step(); paused.refs[8].current = 'BOUNCE'; paused.step()
  ok(paused.advance(30_000) === 'IDLE', 'manual action finishes while autoplay is paused')
  const held = simulate({ phase: 'idle' })
  held.step(); held.refs[6].current = { x: 0, y: 0, samples: [] }
  let grabOnly = true
  for (let tick = 0; tick < 500; tick++) if (held.step() !== 'GRAB') grabOnly = false
  ok(grabOnly, 'long drag cannot briefly enter a random walk or action')

  // 甩抛物理：纯函数（与 tests/test_throw_physics.py 同一套常量与语义）
  const physics = plugin.__physics
  ok(physics && physics.PHYS.G === 1200 && physics.PHYS.THROW_MIN === 280, 'client exports the shared physics constants')
  // 样本时间轴用毫秒（与 performance.now() 一致）：t=10000 距 now 150ms 已出 120ms 窗口
  let velocity = physics.estimateVelocity([{ t: 10000, x: 0, y: 0 }, { t: 10100, x: 500, y: 0 }, { t: 10150, x: 550, y: 0 }], 10150)
  ok(velocity && Math.abs(velocity.vx - 1000) < 0.01, 'stale samples outside the window are ignored')
  ok(physics.estimateVelocity([{ t: 10000, x: 0, y: 0 }, { t: 10005, x: 30, y: 0 }], 10005) === null, 'short span has no velocity')
  ok(physics.estimateVelocity([{ t: 10000, x: 0, y: 0 }], 10000) === null, 'single sample has no velocity')
  let flight = physics.stepPhysics(500, 500, 0, 1500, 0.25, 0, 1000, 0, 800)
  ok(flight.event === 'bounce' && flight.y === 600 && Math.abs(flight.vy + 990) < 1e-9, 'hard impact bounces with energy loss')
  flight = physics.stepPhysics(500, 600, 0, 180, 0.05, 0, 1000, 0, 800)
  ok(flight.event === 'land' && flight.vx === 0 && flight.vy === 0, 'soft contact settles in place')
  flight = physics.stepPhysics(1990, 500, 3000, 0, 0.05, 0, 1800, 0, 800)
  ok(flight.x === 1800 && flight.vx < 0, 'viewport edge reflects the throw')

  // 甩抛集成：真实组件里拖拽-松手-飞行-落地（与桌面端手感同源）
  const findPet = node => {
    if (!node || typeof node !== 'object') return null
    if (node.props?.onPointerDown) return node
    for (const child of node.props?.children || []) { const found = findPet(child); if (found) return found }
    return null
  }
  const fling = simulate({ phase: 'idle' })
  fling.step()
  const pet = findPet(fling.tree)
  ok(!!pet, 'pet image with pointer handlers rendered')
  const grabTarget = { setPointerCapture() {}, hasPointerCapture() { return false }, releasePointerCapture() {} }
  pet.props.onPointerDown({ button: 0, clientX: 300, clientY: 400, pointerId: 1, currentTarget: grabTarget })
  for (const [advance, x, y] of [[20, 400, 420], [20, 520, 440], [20, 640, 460]]) {
    fling.step(advance)
    pet.props.onPointerMove({ clientX: x, clientY: y })
  }
  pet.props.onPointerUp({ pointerId: 1, currentTarget: grabTarget })
  fling.step()
  ok(fling.fakeImage.dataset.animation === 'FALL', 'released fling switches to the fall frame')
  let sawFlight = false, sawLand = false
  for (let tick = 0; tick < 400; tick++) {
    const clip = fling.step(50)
    if (clip === 'FALL') sawFlight = true
    if (clip === 'LAND') { sawLand = true; break }
  }
  ok(sawFlight && sawLand, 'flight plays FALL through the bounces and ends in LAND')
  const settled = fling.refs[7].current
  ok(Math.abs(settled.y - 600) < 1, `pet settles on the viewport floor (y=${settled.y})`)
  console.log(`PASS: DSH overlay (${checks} checks)`)
} finally { rmSync(temp, { recursive: true, force: true }) }
