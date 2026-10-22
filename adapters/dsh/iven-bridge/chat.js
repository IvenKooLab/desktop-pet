/**
 * Iven 桌宠对话：纯函数半边（消息构造 / 记忆截断 / 情绪标记 / 流文本归拢）。
 *
 * LLM 契约与 dsh-pet 同构（MIT，仅参考语义不复制素材）：消息是
 * {id, role, content:[{type:'text',text}], source} 纯对象；流块取 text-delta
 * 拼文本、finish 块记结束原因。情绪标记 [表情:名称] 参照其表情包池做法——
 * 只接受白名单内的名称，防幻觉。
 */

/** 情绪白名单：键为模型可见名称，值为桌宠 clip 名（须与两端运行时对齐）。 */
export const MOODS = {
  happy: 'HAPPY',
  shy: 'SHY',
  cheer: 'CHEER',
  greet: 'GREET',
  relieved: 'RELIEVED',
}
export const MOOD_MARKER = /\[表情[:：]\s*([a-zA-Z]+)\s*\]/
export const MAX_TEXT = 2000

export function cleanText(value, limit = MAX_TEXT) {
  if (typeof value !== 'string') return null
  const cleaned = value.replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g, ' ').trim()
  return cleaned ? cleaned.slice(0, limit) : null
}

export function makeUserMessage(text) {
  return {
    id: crypto.randomUUID(),
    role: 'user',
    content: [{ type: 'text', text }],
    source: { kind: 'user' },
  }
}

export function makeAssistantMessage(text, provider, model) {
  return {
    id: crypto.randomUUID(),
    role: 'assistant',
    content: [{ type: 'text', text }],
    source: { kind: 'model', provider, model },
  }
}

/** 记忆按轮（一问一答）截断；去掉开头悬空的 assistant 半轮。 */
export function sliceRounds(messages, rounds) {
  if (!Array.isArray(messages)) return []
  if (!Number.isInteger(rounds) || rounds <= 0) return []
  const kept = messages.slice(-rounds * 2)
  while (kept.length && kept[0].role !== 'user') kept.shift()
  return kept
}

/** 把记忆历史映射为 dsh 消息对象，并附带本轮用户输入。 */
export function buildMessages(history, text) {
  const mapped = sliceRounds(history, Number.MAX_SAFE_INTEGER).map(m =>
    m.role === 'assistant'
      ? makeAssistantMessage(m.text, m.provider ?? 'unknown', m.model ?? 'unknown')
      : makeUserMessage(m.text))
  return [...mapped, makeUserMessage(text)]
}

/** 情绪清单指令块：追加到用户消息文本（不进 system prompt，参照 dsh-pet）。 */
export function buildUserText(text, moods = MOODS) {
  const names = Object.keys(moods ?? {})
  if (!names.length) return text
  return `${text}\n\n（回复末尾可另起一行写 [表情:名称] 搭配一个表情，名称只能从 ${names.join('/')} 中选，不合适就不要写。）`
}

/** 解析并校验情绪标记：名称必须在白名单内才生效，标记一律从正文剥除。 */
export function extractMood(text, moods = MOODS) {
  const match = MOOD_MARKER.exec(text)
  if (!match) return { text: text.trim(), mood: null }
  const name = match[1].toLowerCase()
  const mood = Object.hasOwn(moods, name) ? name : null
  return { text: text.replace(MOOD_MARKER, '').trim(), mood }
}

/** 归拢流块：拼 text-delta，记 finish；纯函数便于测试。 */
export function collectText(chunks) {
  let text = ''
  let finish = null
  for (const chunk of chunks ?? []) {
    if (!chunk || typeof chunk !== 'object') continue
    if (chunk.type === 'text-delta' && typeof chunk.text === 'string') text += chunk.text
    else if (chunk.type === 'finish') finish = chunk.reason ?? { kind: 'stop' }
  }
  return { text: text.trim(), finish: finish ?? { kind: 'stop' } }
}

/** 默认人设：独立桌宠的说话风格；实例 whisperPrompt 可覆盖（暂未暴露）。 */
export function systemPrompt(now = new Date()) {
  return [
    '你是 Iven，一只住在用户桌面上的 3D 绒质小桌宠：紫白短发、青蓝耳机、随身场记板。',
    '说话简短、俏皮、口语化，一两句话就好，偶尔用一点表演腔。不讨论你做不到的事：你不能替用户操作系统或执行任务。',
    `当前时间：${now.toISOString()}`,
  ].join('\n')
}
