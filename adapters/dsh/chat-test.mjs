// Comi 对话自测：node adapters/dsh/chat-test.mjs（无需启动 dsh）。
// 覆盖：纯函数（记忆截断/情绪标记/流归拢）+ 假 llm 全流程（回落链/白名单防幻觉/结构化失败/记忆封顶）。
import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, readdirSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import {
  MOODS, cleanText, sliceRounds, buildUserText, extractMood, collectText,
  buildMessages, systemPrompt,
} from './comi-bridge/chat.js'
import { createChatIntegration } from './comi-bridge/chat-host.js'

let n = 0
const ok = (what) => { n++ }

// ---------- 纯函数 ----------
// 记忆截断：按问答轮保留，去悬空半轮
const history = [
  { role: 'assistant', text: '悬空半轮' },
  { role: 'user', text: 'q1' }, { role: 'assistant', text: 'a1' },
  { role: 'user', text: 'q2' }, { role: 'assistant', text: 'a2' },
]
assert.deepEqual(sliceRounds(history, 1).map(m => m.text), ['q2', 'a2'])
ok()
assert.equal(sliceRounds(null, 8).length, 0); ok()
assert.equal(sliceRounds(history, 0).length, 0); ok()

// 情绪指令块与标记解析
assert.ok(buildUserText('你好').startsWith('你好'))
assert.ok(buildUserText('你好').includes('happy/shy/cheer/greet/relieved')); ok()
const parsed = extractMood('好呀！\n[表情:happy]', MOODS)
assert.equal(parsed.mood, 'happy')
assert.equal(parsed.text, '好呀！'); ok()
const faked = extractMood('好呀 [表情:unicorn]', MOODS)
assert.equal(faked.mood, null, '幻觉情绪名必须被拒绝')
assert.equal(faked.text, '好呀'); ok()
assert.deepEqual(extractMood('没有标记', MOODS).mood, null); ok()

// 流归拢
const collected = collectText([
  { type: 'block-start', index: 0, blockType: 'text' },
  { type: 'text-delta', index: 0, text: '你' },
  { type: 'reasoning-delta', index: 1, text: '思考不计入' },
  { type: 'text-delta', index: 0, text: '好呀' },
  { type: 'finish', reason: { kind: 'stop' } },
])
assert.equal(collected.text, '你好呀')
assert.equal(collected.finish.kind, 'stop'); ok()

// 消息构造与清洗
assert.equal(cleanText(' A\x00B '), 'A B'); ok()
assert.equal(cleanText('   '), null); ok()
const messages = buildMessages(history.slice(-2), '在吗')
assert.equal(messages.length, 3)
assert.equal(messages[0].role, 'user')
assert.ok(messages[2].source.kind === 'user' && typeof messages[0].id === 'string'); ok()
assert.ok(systemPrompt().includes('Comi')); ok()

// ---------- 全流程（假 llm + 真文件协议） ----------
const dir = mkdtempSync(join(tmpdir(), 'comi-chat-'))
try {
  const fakeLlm = (reply, failFirst = false) => ({
    stream(options) {
      return failFirst
        ? { async *[Symbol.asyncIterator]() { throw new Error('boom') } }
        : (async function* () {
            for (const piece of ['你', reply]) {
              yield { type: 'text-delta', index: 0, text: piece }
              await new Promise(r => setTimeout(r, 1))
            }
            yield { type: 'finish', reason: { kind: 'stop' } }
          })()
    },
  })
  const calls = []
  const services = {
    get llm() {
      calls.push(1)
      return fakeLlm('好呀！\n[表情:happy]')
    },
    agentDefaultModel: { currentSelection: () => ({ provider: 'p1', model: 'm1' }) },
  }
  const chat = createChatIntegration({
    services, dir,
    config: { memoryRounds: 8, pollMs: 20 },
    logger: { warn: () => {}, info: () => {} },
  })

  // 1. 快乐路径：回复 + 白名单情绪 + 记忆写入 + 请求文件清理
  chat.start()
  writeFileSync(join(dir, 'request-r1.json'),
                JSON.stringify({ version: 1, id: 'r1', text: '在吗' }))
  const deadline = Date.now() + 5000
  let reply1 = null
  while (Date.now() < deadline && !reply1) {
    chat.scan()
    await new Promise(r => setTimeout(r, 30))
    try { reply1 = JSON.parse(readFileSync(join(dir, 'reply-r1.json'), 'utf8')) } catch {}
  }
  assert.ok(reply1, 'reply file must appear')
  assert.equal(reply1.ok, true)
  assert.equal(reply1.mood, 'happy')
  assert.equal(reply1.text, '你好呀！')
  const mem = chat.readMemory()
  assert.equal(mem.length, 2)
  assert.equal(mem[0].text, '在吗')
  assert.equal(mem[1].mood, undefined, '标记不落盘')
  assert.ok(!readdirSync(dir).some(f => f.startsWith('request-')), '请求已清理')
  ok()

  // 2. 坏请求：空文本 → 结构化 bad-request，不碰 llm
  const before = calls.length
  await chat.handleRequest({ version: 1, id: 'r2', text: '   ' })
  const reply2 = JSON.parse(readFileSync(join(dir, 'reply-r2.json'), 'utf8'))
  assert.equal(reply2.ok, false)
  assert.equal(reply2.reason, 'bad-request')
  assert.equal(calls.length, before, '坏请求不得调用 llm')
  ok()

  // 3. provider 缺失：结构化 provider-missing，不伪造回复
  const bare = createChatIntegration({ services: {}, dir, config: {} })
  await bare.handleRequest({ version: 1, id: 'r3', text: '在吗' })
  const reply3 = JSON.parse(readFileSync(join(dir, 'reply-r3.json'), 'utf8'))
  assert.equal(reply3.ok, false)
  assert.equal(reply3.reason, 'provider-missing'); ok()

  // 4. 回落链：首选模型抛错 → 回落到当前会话模型成功
  let toggle = false
  const fallbackServices = {
    llm: {
      stream(options) {
        if (options.model === 'preferred') {
          return { async *[Symbol.asyncIterator]() { throw new Error('quota') } }
        }
        toggle = true
        return fakeLlm('回落成功').stream(options)
      },
    },
    agentDefaultModel: { currentSelection: () => ({ provider: 'p2', model: 'fallback' }) },
  }
  const fb = createChatIntegration({
    services: fallbackServices, dir,
    config: { chatProvider: 'px', chatModel: 'preferred' },
  })
  await fb.handleRequest({ version: 1, id: 'r4', text: '在吗' })
  const reply4 = JSON.parse(readFileSync(join(dir, 'reply-r4.json'), 'utf8'))
  assert.equal(reply4.ok, true, '首选失败必须回落到会话模型')
  assert.ok(toggle, '确实回落到了第二个候选'); ok()

  // 5. 记忆封顶：rounds=1 时只留最近一轮
  const capped = createChatIntegration({ services: {}, dir, config: { memoryRounds: 1 } })
  capped.appendMemory([
    { role: 'user', text: 'q-old' }, { role: 'assistant', text: 'a-old' },
    { role: 'user', text: 'q-new' }, { role: 'assistant', text: 'a-new' },
  ], 1)
  assert.deepEqual(capped.readMemory().map(m => m.text), ['q-new', 'a-new']); ok()
} finally {
  chatStopCleanup(dir)
}
function chatStopCleanup(dir) {
  try { rmSync(dir, { recursive: true, force: true }) } catch {}
}

console.log(`PASS: comi chat (${n} checks)`)
