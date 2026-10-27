/**
 * Comi 桌宠对话 · DSH 宿主半边：监听本地对话目录，用宿主 LLM 服务生成回复。
 *
 * 协议（与桌宠端 host_chat.py / ComiPet.swift 对齐，均为本机原子文件）：
 *   请求 chat/request-<id>.json  {version:1, id, text}
 *   回复 chat/reply-<id>.json    {version:1, id, ok, text?, mood?, reason?, message?}
 *   记忆 chat/memory.json        {version:1, messages:[{role,text,provider?,model?,ts}]}
 *
 * 语义与 dsh-pet（MIT）同构：模型候选链（配置覆盖 → 当前会话模型）逐级回落；
 * 失败返回结构化原因，绝不伪造回复；情绪标记只认白名单，防幻觉。
 */
import { existsSync, mkdirSync, readdirSync, readFileSync, renameSync, rmSync, statSync, unlinkSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { homedir } from 'node:os'
import {
  MOODS, MAX_TEXT, cleanText, buildMessages, buildUserText,
  extractMood, collectText, systemPrompt,
} from './chat.js'

export function resolveChatDir(explicit) {
  // 与 comi_home.py 同规则：旧 ~/.iven-pet 存在则沿用，避免升级后数据分叉
  const root = existsSync(join(homedir(), '.iven-pet'))
    ? join(homedir(), '.iven-pet')
    : join(homedir(), '.comi-pet')
  return explicit || process.env.COMI_CHAT_DIR || process.env.IVEN_CHAT_DIR
    || join(root, 'chat')
}

function atomicWrite(path, payload) {
  const tmp = `${path}.tmp-${process.pid}`
  writeFileSync(tmp, JSON.stringify(payload))
  renameSync(tmp, path)
}

export function createChatIntegration({ services, dir, config = {}, logger }) {
  const cfg = {
    memoryRounds: 8,
    timeoutMs: 60000,
    pollMs: 1500,
    staleRequestMs: 15 * 60_000,
    staleReplyMs: 5 * 60_000,
    ...config,
  }
  const log = (level, message) => logger?.[level]?.(`[comi-bridge:chat] ${message}`)
  const memoryPath = join(dir, 'memory.json')
  const inFlight = new Set()
  let chain = Promise.resolve()      // 串行化请求处理，防记忆交错
  let timer = null

  function readMemory() {
    try {
      const data = JSON.parse(readFileSync(memoryPath, 'utf8'))
      if (data?.version === 1 && Array.isArray(data.messages)) return data.messages
    } catch { /* 缺失或损坏都从空记忆开始 */ }
    return []
  }

  function appendMemory(entries, rounds) {
    const messages = [...readMemory(), ...entries].slice(-(rounds * 2))
    atomicWrite(memoryPath, { version: 1, messages })
  }

  function modelCandidates() {
    const out = []
    if (config.chatProvider && config.chatModel) {
      out.push({ provider: String(config.chatProvider), model: String(config.chatModel) })
    }
    const sel = services?.agentDefaultModel?.currentSelection?.()
    const provider = sel?.provider ?? sel?.providerId
    const model = sel?.model ?? sel?.modelId
    if (provider && model) out.push({ provider: String(provider), model: String(model) })
    return out
  }

  async function generate(system, history, text) {
    if (!services?.llm || typeof services.llm.stream !== 'function') {
      return { ok: false, reason: 'provider-missing', message: 'LLM 服务不可用' }
    }
    const candidates = modelCandidates()
    if (!candidates.length) {
      return { ok: false, reason: 'provider-missing', message: '未配置可用模型' }
    }
    const messages = buildMessages(history, buildUserText(text, MOODS))
    let last = null
    for (const candidate of candidates) {
      try {
        const chunks = []
        const stream = services.llm.stream({
          provider: candidate.provider,
          model: candidate.model,
          sessionId: 'comi-pet-chat',
          system,
          messages,
          temperature: 1,
          signal: AbortSignal.timeout(cfg.timeoutMs),
        })
        for await (const chunk of stream) chunks.push(chunk)
        const { text: reply, finish } = collectText(chunks)
        if (reply) {
          return { ok: true, reply, provider: candidate.provider, model: candidate.model }
        }
        last = { ok: false, reason: 'no-text', message: `finish=${JSON.stringify(finish)}` }
      } catch (error) {
        last = { ok: false, reason: 'generate-error',
                 message: error instanceof Error ? error.message : String(error) }
      }
      log('warn', `对话用 ${candidate.model} 生成失败，尝试下一个候选`)
    }
    return last
  }

  /** 处理单个请求对象——文件扫描与测试共用的核心入口。 */
  function handleRequest(request) {
    const id = typeof request?.id === 'string' ? request.id.slice(0, 64) : null
    const finish = reply => {
      if (id) atomicWrite(join(dir, `reply-${id}.json`), { version: 1, id, ...reply })
    }
    if (request?.version !== 1 || !id) return Promise.resolve()
    const text = cleanText(request.text, MAX_TEXT)
    if (!text) {
      finish({ ok: false, reason: 'bad-request', message: '消息为空' })
      return Promise.resolve()
    }
    return generate(systemPrompt(), readMemory().slice(-(cfg.memoryRounds * 2)), text)
      .then(result => {
        if (!result?.ok) {
          log('warn', `回复失败：${result?.reason} ${result?.message ?? ''}`)
          finish({ ok: false, reason: result?.reason ?? 'generate-error',
                   message: result?.message ?? null })
          return
        }
        const { text: replyText, mood } = extractMood(result.reply, MOODS)
        appendMemory([
          { role: 'user', text, ts: Date.now() },
          { role: 'assistant', text: replyText, provider: result.provider,
            model: result.model, ts: Date.now() },
        ], cfg.memoryRounds)
        finish({ ok: true, text: replyText, mood })
      })
  }

  function scan() {
    mkdirSync(dir, { recursive: true })
    let names = []
    try {
      names = readdirSync(dir)
    } catch {
      return
    }
    for (const name of names) {
      const path = join(dir, name)
      try {
        if (name.startsWith('request-') && name.endsWith('.json')) {
          if (inFlight.has(path)) continue
          if (Date.now() - statSync(path).mtimeMs > cfg.staleRequestMs) {
            rmSync(path)
            continue
          }
          const request = JSON.parse(readFileSync(path, 'utf8'))
          inFlight.add(path)
          chain = chain
            .then(() => handleRequest(request))
            .catch(error => log('warn', `请求处理异常：${error?.message ?? error}`))
            .finally(() => {
              try { unlinkSync(path) } catch { /* 已被清理 */ }
              inFlight.delete(path)
            })
        } else if (name.startsWith('reply-') && name.endsWith('.json')) {
          // 回复超过 staleReplyMs 无人认领（桌宠没开）→ 清理
          if (Date.now() - statSync(path).mtimeMs > cfg.staleReplyMs) rmSync(path)
        }
      } catch (error) {
        log('warn', `跳过 ${name}：${error?.message ?? error}`)
      }
    }
  }

  return {
    memoryPath,
    readMemory,
    appendMemory,
    modelCandidates,
    handleRequest,
    scan,
    start() {
      mkdirSync(dir, { recursive: true })
      scan()
      timer = setInterval(() => { try { scan() } catch { /* 下一轮再试 */ } }, cfg.pollMs)
      if (timer.unref) timer.unref()
    },
    stop() {
      if (timer) clearInterval(timer)
      timer = null
    },
  }
}
