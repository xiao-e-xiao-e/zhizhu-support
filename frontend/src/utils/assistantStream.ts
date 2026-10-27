/** Parse SSE at byte boundaries, including split UTF-8 and CRLF frames. */
export async function consumeAssistantEvents(
  stream: ReadableStream<Uint8Array>,
  dispatch: (event: string, data: unknown) => void,
) {
  const reader = stream.getReader(), decoder = new TextDecoder()
  let buffer = ''
  function frame(raw: string) {
    let event = 'message'
    const data: string[] = []
    for (const line of raw.split(/\r?\n/)) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''))
    }
    if (data.length) dispatch(event, JSON.parse(data.join('\n')))
  }
  try {
    while (true) {
      const { done, value } = await reader.read()
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true })
      let match: RegExpExecArray | null
      while ((match = /\r?\n\r?\n/.exec(buffer))) {
        frame(buffer.slice(0, match.index))
        buffer = buffer.slice(match.index + match[0].length)
      }
      if (buffer.length > 1_000_000) throw new Error('回复事件过大，请刷新查看记录')
      if (done) { if (buffer.trim()) frame(buffer); break }
    }
  } finally {
    await reader.cancel().catch(() => {})
    reader.releaseLock()
  }
}
