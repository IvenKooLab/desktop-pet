/**
 * Iven 桌宠桥接 · DSH 宿主插件。
 *
 * 订阅 dsh 的 session/event，归约为统一事件写入本地收件箱（默认
 * ~/.iven-pet/events），由 Iven 桌宠（Mac 原生版 / Windows Tk 版）消费。
 * 语义参考 dsh-pet（MIT）的 work-status 归约：turn/end 只是"本轮结束"，
 * 只有 update_goal 显式 complete/blocked 才算任务级结果；goal 自动续跑的
 * 轮次不误报任务完成。
 *
 * 事件文本一律当数据清洗后转发，不执行；不调用任何模型；桌宠离线时写
 * 文件照常成功，绝不阻塞宿主。
 */
import { existsSync, mkdirSync, renameSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { homedir } from 'node:os'
import { createWebIntegration } from './web.js'

export const name = 'iven-bridge'
export const inject = []

export const DEFAULT_CONFIG = {
  /** 收件箱目录；空 = IVEN_BRIDGE_DIR 环境变量或 ~/.iven-pet/events */
  eventsDir: '',
  /** 摘要开关：默认只传状态；开启后附带 todo 提炼的任务标签 */
  summary: false,
}

export function sessionIdOf(session) {
  return String(session?.header?.id ?? session?.id ?? 'unknown')
}

/** 每 turn 一次的标志：goalRound（goal 自动续跑）与 closing（显式结束动作）。 */
export function newTurnFlags() {
  return { goalRound: false, closing: null, label: null }
}

function clean(value, limit) {
  if (typeof value !== 'string') return null
  const cleaned = value.replace(/[\x00-\x1f\x7f]/g, ' ').trim().slice(0, limit)
  return cleaned || null
}

/** 从 todo/write 提炼当前任务文本：第一个未完成项（与 dsh-pet 口径一致）。 */
export function currentTaskFromTodo(todos) {
  if (!Array.isArray(todos)) return null
  const current = todos.find(t => t?.status === 'in_progress') ?? todos[0]
  return clean(current?.content, 80)
}

/**
 * 纯映射：DSH session/event → 统一事件列表（空数组 = 不发）。
 * flags 为该会话当前 turn 的状态（会被就地更新），便于测试。
 */
export function mapEvent(flags, event) {
  const type = event?.type
  const data = event?.data ?? {}
  switch (type) {
    case 'turn/start':
      Object.assign(flags, newTurnFlags())
      return [{ kind: 'turn.started' }]
    case 'user/message':
      if (data.source?.kind === 'goal') flags.goalRound = true
      return []
    case 'tool/call': {
      const toolName = clean(data.name, 48)
      if (toolName === 'update_goal') {
        const action = data.arguments?.action ?? data.arguments
        if (action === 'complete' || action === 'blocked') flags.closing = action
      }
      return [{ kind: 'tool.started', toolName }]
    }
    case 'tool/result':
      return [{ kind: 'tool.finished' }]
    case 'approval/asked':
      return [{ kind: 'permission.required' }]
    case 'todo/write':
      flags.label = currentTaskFromTodo(data.todos)
      return [{ kind: 'task.updated' }]
    case 'turn/end':
      if (flags.closing === 'complete') return [{ kind: 'task.completed' }]
      if (flags.closing === 'blocked') return [{ kind: 'turn.failed' }]
      return [{ kind: 'turn.ended' }]
    default:
      return []
  }
}

function writeInbox(dir, kind, extra) {
  mkdirSync(dir, { recursive: true })
  const id = `dsh-${process.pid}-${Date.now().toString(36)}-${Math.random().toString(16).slice(2, 10)}`
  const stamp = new Date().toISOString().replace('+00:00', 'Z')
  const payload = {
    version: 1,
    event_id: id,
    source: 'dsh',
    session_id: extra.sessionId,
    turn_id: null,
    timestamp: stamp,
    kind,
    task_label: extra.label ?? null,
    summary: null,
    tool_name: extra.toolName ?? null,
    severity: 'info',
  }
  const final = join(dir, `${String(Date.now()).padStart(19, '0')}-${id}.json`)
  const tmp = `${final}.tmp-${process.pid}`
  writeFileSync(tmp, JSON.stringify(payload))
  renameSync(tmp, final)
}

export function apply(ctx, config) {
  const cfg = { ...DEFAULT_CONFIG, ...(config ?? {}) }
  const eventsDir = cfg.eventsDir
    || process.env.IVEN_BRIDGE_DIR
    || join(homedir(), '.iven-pet', 'events')
  const summary = () => cfg.summary || !['', '0', 'false'].includes(process.env.IVEN_BRIDGE_SUMMARY ?? '') || existsSync(join(homedir(), '.iven-pet', 'summary'))
  const flagsBySession = new Map()
  const web = createWebIntegration(ctx, {
    eventsDir,
    summary,
  })

  ctx.effect(() => {
    const dispose = ctx.on('session/event', (session, event) => {
      try {
        const sessionId = sessionIdOf(session)
        let flags = flagsBySession.get(sessionId)
        if (!flags) {
          flags = newTurnFlags()
          flagsBySession.set(sessionId, flags)
          writeInbox(eventsDir, 'session.started', { sessionId })
        }
        for (const mapped of mapEvent(flags, event)) {
          web.record(sessionId, mapped, summary() ? flags.label : undefined)
          writeInbox(eventsDir, mapped.kind, {
            sessionId,
            toolName: mapped.toolName,
            label: summary() ? flags.label : undefined,
          })
        }
      } catch (error) {
        ctx.logger?.warn?.(`[iven-bridge] ${error instanceof Error ? error.message : String(error)}`)
      }
    })
    return () => { dispose?.(); flagsBySession.clear() }
  }, 'iven-bridge: inbox writer')
}
