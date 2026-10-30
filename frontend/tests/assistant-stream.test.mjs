import test from 'node:test'
import assert from 'node:assert/strict'
import { consumeAssistantEvents } from '../src/utils/assistantStream.ts'

test('UTF-8 and CRLF frames are delivered incrementally across byte boundaries', async () => {
  const seen = [], encoder = new TextEncoder()
  let controller
  const body = new ReadableStream({ start(c) { controller = c } })
  const reading = consumeAssistantEvents(body, (kind, data) => seen.push([kind, data]))
  const frame = 'event: answer_delta\r\ndata: {"run_id":"a","offset":0,"text":"你好🙂"}\r\n\r\n'
  for (const byte of encoder.encode(frame)) controller.enqueue(Uint8Array.of(byte))
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(seen.length, 1) // Stream remains open; no final result yet.
  assert.deepEqual(seen[0], ['answer_delta', {run_id:'a',offset:0,text:'你好🙂'}])
  controller.enqueue(encoder.encode('event: done\ndata: {"id":"a"}\n\n'))
  controller.close()
  await reading
  assert.equal(seen[1][0], 'done')
})
test('parse or handler failures cancel the underlying stream', async () => {
  let cancelled = false
  const body = new ReadableStream({start(c) { c.enqueue(new TextEncoder().encode('event: answer_delta\ndata: invalid-json\n\n')) },cancel() { cancelled = true }})
  await assert.rejects(consumeAssistantEvents(body, () => {}), SyntaxError)
  assert.equal(cancelled, true)
})
test('comments are ignored and reset events arrive before the next answer', async () => {
  const seen = []
  const body = new Response(': heartbeat\n\nevent: answer_reset\ndata: {"run_id":"a"}\n\nevent: answer_delta\ndata: {"run_id":"a","offset":0,"text":"新回答"}\n\n').body
  await consumeAssistantEvents(body, (kind, data) => seen.push([kind, data]))
  assert.deepEqual(seen.map(e => e[0]), ['answer_reset','answer_delta'])
})
