/* DSH browser module: deliberately a side-effect script, not an ESM bundle.
 * It uses the host's React and the official shell.overlay slot. */
window.__ModuleLoader__.load({
  id: 'comi-bridge',
  factory(require) {
    const React = require('react')
    const { createElement: h, useEffect, useRef, useState } = React
    const PREFIX = '/comi-pet'
    const SPEED = 0.75
    const zh = (navigator.language || '').toLowerCase().startsWith('zh')
    const text = (cn, en) => zh ? cn : en
    const labels = {
      IDLE: text('眨眼休息', 'Rest'), GREET: text('挥手', 'Wave'), BOUNCE: text('小跳', 'Bounce'),
      HAPPY: text('开心', 'Happy'), SHY: text('害羞', 'Shy'), CHEER: text('打板', 'Clapperboard'),
      SPIN: text('观察四周', 'Look around'), STRETCH: text('伸懒腰', 'Stretch'),
      DOZE: text('打瞌睡', 'Doze'), RUBIK: text('玩魔方', 'Rubik’s cube'),
      THINKING: text('苦思冥想', 'Deep thinking'), IMPATIENT: text('等待不耐烦', 'Getting impatient'),
      TOKEN_LOW: text('额度不足（表演）', 'Low tokens (performance)'), RELIEVED: text('松口气', 'A sigh of relief'),
    }
    const clientId = (() => {
      try {
        let value = sessionStorage.getItem('comi-pet-client')
        if (!value) { value = `web_${crypto.randomUUID().replaceAll('-', '')}`; sessionStorage.setItem('comi-pet-client', value) }
        return value
      } catch { return `web_${Date.now()}_${Math.random().toString(36).slice(2)}` }
    })()
    const button = { border: '1px solid #ddd5ea', background: '#fff', color: '#514261', borderRadius: 10,
      padding: '7px 11px', fontSize: 12, cursor: 'pointer', fontFamily: 'inherit', boxShadow: '0 2px 10px #21132a12' }
    const request = async (path, body) => {
      const response = await fetch(`${PREFIX}/api/${path}`, body === undefined
        ? { credentials: 'same-origin', cache: 'no-store' }
        : { method: 'POST', credentials: 'same-origin', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })
      const data = await response.json()
      if (!response.ok) { const error = new Error(data.error || `HTTP ${response.status}`); error.data = data; throw error }
      return data
    }
    function Overlay() {
      const [display, setDisplay] = useState({ mode: 'desktop' })
      const [host, setHost] = useState({ phase: 'idle', label: '', tool: '' })
      const [manifest, setManifest] = useState(null)
      const [error, setError] = useState('')
      const [now, setNow] = useState(Date.now())
      const [menu, setMenu] = useState(false)
      const image = useRef(null), card = useRef(null), stateRef = useRef(host), manifestRef = useRef(null)
      const behavior = useRef({ actions: {} }), leaseRef = useRef(display), drag = useRef(null)
      const position = useRef({ x: Math.max(0, innerWidth - 235), y: Math.max(100, innerHeight - 235) })
      const action = useRef(null)
      stateRef.current = host
      leaseRef.current = display
      const embedded = display.mode === 'embedded' && display.client_id === clientId && display.lease_until > now
      const selectMode = async mode => {
        if (mode === 'embedded' && !manifestRef.current) return
        try { const data = await request('display', { mode, client_id: clientId }); setDisplay(data.display); setError(''); setMenu(false) }
        catch { setError(text('模式切换失败，请检查 DSH 连接', 'Could not switch modes. Check DSH.')) }
      }
      useEffect(() => {
        let disposed = false
        Promise.all([request('manifest'), request('behaviors')]).then(([data, rules]) => {
          if (!disposed) { manifestRef.current = data; behavior.current = rules; setManifest(data) }
        }).catch(() => { if (!disposed) setError(text('未能读取 Comi 动画素材', 'Could not load Comi’s animations')) })
        const poll = async () => {
          try {
            const data = await request('state')
            if (disposed) return
            setHost(data.state)
            setDisplay(data.display)
            setError('')
            // A native-menu request has no client id. The first visible DSH tab
            // claims it atomically; other tabs cannot prolong that lease.
            if (!document.hidden && manifestRef.current && data.display.mode === 'embedded' && !data.display.client_id) {
              try { const claimed = await request('heartbeat', { client_id: clientId }); if (!disposed) setDisplay(claimed.display) }
              catch { /* another DSH tab won the claim */ }
            }
          } catch { if (!disposed) setError(text('DSH 连接已断开；桌面模式将在 30 秒内恢复', 'DSH disconnected; desktop mode returns within 30 seconds')) }
        }
        poll()
        const pollTimer = setInterval(poll, 1500)
        const expiryTimer = setInterval(() => setNow(Date.now()), 1000)
        const leaseTimer = setInterval(async () => {
          const current = leaseRef.current
          if (document.hidden || current.mode !== 'embedded' || current.client_id !== clientId) return
          try { const data = await request('heartbeat', { client_id: clientId }); if (!disposed) setDisplay(data.display) }
          catch (failure) { if (!disposed && failure.data?.display) setDisplay(failure.data.display) }
        }, 5000)
        const visibility = () => { if (!document.hidden) poll() }
        document.addEventListener('visibilitychange', visibility)
        return () => { disposed = true; clearInterval(pollTimer); clearInterval(leaseTimer); clearInterval(expiryTimer); document.removeEventListener('visibilitychange', visibility) }
      }, [])
      useEffect(() => {
        if (!embedded || !manifest) return
        const clips = manifest.clips
        let raf, previous = performance.now(), clip = 'IDLE', elapsed = 0, repeats = 1, shown = '', lastAction = ''
        let previousPhase = 'idle', previousHostKey = '', terminalPlayed = false, direction = Math.random() > .5 ? 1 : -1
        const randomInt = (range, fallback) => {
          const pair = Array.isArray(range) && range.length === 2 ? range : fallback
          return Math.floor(pair[0] + Math.random() * (pair[1] - pair[0] + 1))
        }
        const choose = name => {
          clip = clips[name] ? name : 'IDLE'; elapsed = 0
          const configured = behavior.current.actions?.[clip]?.cycles
          if (['THINKING', 'IMPATIENT', 'TOKEN_LOW', 'RELIEVED'].includes(clip)
            || (stateRef.current.phase === 'working' && clip === 'WORK')) repeats = 1
          else if (clip === 'IDLE') repeats = Math.max(1, Math.round(randomInt(behavior.current.idle_seconds, [3, 5]) * 1000 * SPEED / clips.IDLE.durations.reduce((a, b) => a + b, 0)))
          else if (clip.startsWith('WALK')) repeats = randomInt(behavior.current.walk_cycles, [5, 8])
          else repeats = randomInt(configured, ['GREET', 'BOUNCE', 'HAPPY', 'CHEER'].includes(clip) ? [3, 5] : [2, 3])
        }
        const next = () => {
          const phase = stateRef.current.phase
          if (phase === 'working') return choose(clip === 'WORK' ? 'THINKING' : 'WORK')
          if (phase === 'waiting') return choose(Date.now() - (stateRef.current.phase_since || Date.now()) >= 30_000 ? 'IMPATIENT' : 'WAITING')
          if (phase === 'success') {
            if (terminalPlayed) return choose('IDLE')
            terminalPlayed = true
            return choose('RELIEVED')
          }
          if (phase === 'failed') return choose('FAILED')
          // TOKEN_LOW is a manual performance, never an inferred account state.
          const choices = ['IDLE', 'IDLE', 'IDLE', 'WALK', ...Object.keys(labels).filter(name => name !== 'IDLE' && name !== 'TOKEN_LOW' && name !== lastAction && clips[name])]
          let name = choices[Math.floor(Math.random() * choices.length)]
          if (name === 'WALK') { direction = Math.random() > .5 ? 1 : -1; name = direction > 0 ? 'WALK_r' : 'WALK_l' }
          lastAction = name
          choose(name)
        }
        choose('IDLE')
        const frame = now => {
          const dt = Math.min(100, now - previous); previous = now
          const phase = stateRef.current.phase
          const hostKey = `${stateRef.current.session_id || ''}:${phase}:${stateRef.current.phase_since || ''}`
          if (hostKey !== previousHostKey) {
            previousHostKey = hostKey
            const finishingRelief = phase === 'idle' && previousPhase === 'success' && clip === 'RELIEVED'
            previousPhase = phase
            terminalPlayed = false
            // A 7-second result bubble may expire before this 9-second theme;
            // let its current timeline finish unless another task interrupts.
            if (!finishingRelief) next()
          }
          if (phase === 'waiting' && clip === 'WAITING' && Date.now() - (stateRef.current.phase_since || Date.now()) >= 30_000) choose('IMPATIENT')
          if (action.current) { choose(action.current); action.current = null }
          if (drag.current) {
            if (clip !== 'GRAB') choose('GRAB')
          } else if (clip === 'GRAB') choose('IDLE')
          elapsed += dt * SPEED
          let selected = clips[clip] || clips.IDLE
          let duration = selected.durations.reduce((a, b) => a + b, 0)
          if (elapsed >= duration * repeats) { next(); selected = clips[clip] || clips.IDLE; duration = selected.durations.reduce((a, b) => a + b, 0) }
          let phaseTime = elapsed % duration, index = 0
          while (index < selected.frames.length - 1 && phaseTime >= selected.durations[index]) { phaseTime -= selected.durations[index]; index++ }
          const source = `${PREFIX}/frames/${selected.frames[index]}.png`
          if (source !== shown && image.current) { image.current.src = source; shown = source }
          if (image.current) image.current.dataset.animation = clip
          if (!drag.current && clip.startsWith('WALK')) {
            const pos = position.current
            pos.x += direction * 28 * dt / 1000 * SPEED
            if (pos.x <= 0 || pos.x >= innerWidth - 200) { direction *= -1; choose(direction > 0 ? 'WALK_r' : 'WALK_l') }
          }
          const pos = position.current
          pos.x = Math.max(0, Math.min(Math.max(0, innerWidth - 200), pos.x))
          pos.y = Math.max(Math.min(120, Math.max(0, innerHeight - 200)), Math.min(Math.max(0, innerHeight - 200), pos.y))
          if (card.current) { card.current.style.left = `${pos.x}px`; card.current.style.top = `${pos.y}px` }
          raf = requestAnimationFrame(frame)
        }
        raf = requestAnimationFrame(frame)
        return () => cancelAnimationFrame(raf)
      }, [embedded, manifest])
      const phases = { working: text('工作中', 'Working'), waiting: text('等你确认', 'Needs your input'), success: text('任务完成', 'Task complete'), failed: text('遇到问题', 'Needs attention') }
      const status = phases[host.phase]
      const startDrag = event => {
        if (event.button !== 0) return
        drag.current = { x: event.clientX - position.current.x, y: event.clientY - position.current.y, moved: false }
        event.currentTarget.setPointerCapture(event.pointerId); setMenu(false)
      }
      const moveDrag = event => {
        if (!drag.current) return
        const x = event.clientX - drag.current.x, y = event.clientY - drag.current.y
        if (Math.abs(x - position.current.x) + Math.abs(y - position.current.y) > 3) drag.current.moved = true
        position.current = { x, y }
      }
      const endDrag = event => {
        if (!drag.current) return
        if (!drag.current.moved) action.current = 'BOUNCE'
        drag.current = null
        if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
      }
      const entries = Object.keys(labels).filter(name => manifest?.clips[name]).map(name => h('button', {
        key: name, style: { ...button, boxShadow: 'none', textAlign: 'left', padding: '5px 9px' },
        onClick: () => { action.current = name; setMenu(false) },
      }, labels[name]))
      return h('div', { style: { position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 1000, fontFamily: 'system-ui, sans-serif' } },
        h('button', { type: 'button', disabled: !manifest, style: { ...button, position: 'absolute', right: 16, top: 76, pointerEvents: 'auto', opacity: manifest ? 1 : .6 },
          title: error || text('切换 Comi 显示位置', 'Switch Comi’s display mode'),
          onClick: () => selectMode(embedded ? 'desktop' : 'embedded') },
        error ? text('Comi · 连接中断', 'Comi · disconnected') : embedded ? text('Comi · 切到桌面 ↗', 'Comi · move to desktop ↗') : text('Comi · 移入界面 ↙', 'Comi · bring into DSH ↙')),
        embedded && manifest ? h('div', { ref: card, style: { position: 'absolute', width: 200, height: 200, left: position.current.x, top: position.current.y, pointerEvents: 'auto' } },
          status ? h('div', { style: { position: 'absolute', bottom: 160, left: -35, width: 270, boxSizing: 'border-box', background: '#fffffff5', color: '#302638',
            padding: '11px 14px', border: '1px solid #ddd4e7', borderRadius: 16, boxShadow: '0 4px 20px #25122a24', fontSize: 12, pointerEvents: 'none', overflowWrap: 'anywhere' } },
          h('strong', { style: { display: 'block', color: '#7954a2', marginBottom: host.label || host.tool ? 5 : 0 } }, `DSH · ${status}`),
          host.label ? h('div', null, host.label) : null,
          host.tool ? h('div', { style: { marginTop: 3, opacity: .8 } }, `${text('当前工具', 'Tool')} · ${host.tool}`) : null) : null,
          h('img', { ref: image, src: `${PREFIX}/frames/idle_0.png`, draggable: false, alt: 'Comi',
            style: { display: 'block', width: 200, height: 200, userSelect: 'none', touchAction: 'none', cursor: 'grab' },
            onPointerDown: startDrag, onPointerMove: moveDrag, onPointerUp: endDrag, onPointerCancel: endDrag,
            onContextMenu: event => { event.preventDefault(); setMenu(value => !value) } }),
          menu ? h('div', { style: { position: 'absolute', bottom: 180, right: 0, width: 180, maxHeight: '50vh', overflowY: 'auto', padding: 8,
            display: 'grid', gap: 4, background: '#fff', border: '1px solid #ddd5ea', borderRadius: 14, boxShadow: '0 6px 25px #24122a30' } },
          h('button', { style: button, onClick: () => selectMode('desktop') }, text('移到独立桌面 ↗', 'Move to desktop ↗')), ...entries) : null) : null)
    }
    return {
      name: 'comi-pet', inject: ['slots'],
      apply(ctx) {
        ctx.slots.inject('shell.overlay', function* () {
          yield ctx.slots.register({ name: 'shell.overlay', id: 'comi-pet', order: 1000 }, () => h(Overlay))
        })
      },
    }
  },
})
