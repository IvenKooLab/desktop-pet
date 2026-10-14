// DSH 适配器纯映射自测：node adapters/dsh/self-test.mjs
// 场景与 tests/test_host_bridge.py / Swift self-test 同语义。
import assert from 'node:assert/strict'
import { mapEvent, newTurnFlags, currentTaskFromTodo, sessionIdOf } from './iven-bridge/index.js'

let n = 0
const check = (actual, expected, what) => {
  assert.deepEqual(actual.map(e => e.kind), expected, what)
  n++
}

// 1) 普通 turn：start → tool×2 → end = 本轮结束，不是任务完成
let flags = newTurnFlags()
check(mapEvent(flags, { type: 'turn/start' }), ['turn.started'], 'turn/start')
assert.deepEqual(mapEvent(flags, { type: 'user/message', data: { source: { kind: 'user' } } }), [], 'user message no event')
check(mapEvent(flags, { type: 'tool/call', data: { name: 'shell' } }), ['tool.started'], 'tool/call')
check(mapEvent(flags, { type: 'tool/result' }), ['tool.finished'], 'tool/result')
check(mapEvent(flags, { type: 'turn/end' }), ['turn.ended'], 'plain turn/end ≠ task.completed')

// 2) goal 自动续跑：goal 来源的 user/message 后 turn/end 仍只是本轮结束
flags = newTurnFlags()
mapEvent(flags, { type: 'turn/start' })
mapEvent(flags, { type: 'user/message', data: { source: { kind: 'goal' } } })
assert.equal(flags.goalRound, true, 'goalRound marked')
check(mapEvent(flags, { type: 'turn/end' }), ['turn.ended'], 'goal auto-continue round is not completion')

// 3) update_goal complete → task.completed；blocked → turn.failed
flags = newTurnFlags()
mapEvent(flags, { type: 'turn/start' })
mapEvent(flags, { type: 'tool/call', data: { name: 'update_goal', arguments: { action: 'complete' } } })
check(mapEvent(flags, { type: 'turn/end' }), ['task.completed'], 'explicit goal complete')
flags = newTurnFlags()
mapEvent(flags, { type: 'tool/call', data: { name: 'update_goal', arguments: { action: 'blocked' } } })
check(mapEvent(flags, { type: 'turn/end' }), ['turn.failed'], 'goal blocked')

// 4) 审批等待与 todo 标签
flags = newTurnFlags()
check(mapEvent(flags, { type: 'approval/asked' }), ['permission.required'], 'approval')
assert.deepEqual(mapEvent(flags, { type: 'todo/write', data: { todos: [
  { content: '已完成项', status: 'completed' },
  { content: '修复登录页', status: 'in_progress' },
] } }), [], 'todo only updates label')
assert.equal(flags.label, '修复登录页', 'label from first in_progress todo')

// 5) 会话 id 兜底与杂项
assert.equal(sessionIdOf({ header: { id: 's1' } }), 's1')
assert.equal(sessionIdOf(undefined), 'unknown')
assert.equal(currentTaskFromTodo(null), null)
assert.equal(mapEvent(newTurnFlags(), { type: 'whatever' }).length, 0, 'unknown event dropped')
// 控制字符清洗
flags = newTurnFlags()
mapEvent(flags, { type: 'todo/write', data: { todos: [{ content: 'A\nB\x00C', status: 'in_progress' }] } })
assert.equal(flags.label, 'A B C', 'control chars stripped')

console.log(`PASS: dsh adapter mapping (${n} scenario groups)`)
