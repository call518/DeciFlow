export async function readEvents(body, onEvent) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let pending = '';
  let doneEvent = false;
  try {
    while (true) {
      const { value, done } = await reader.read();
      pending += decoder.decode(value, { stream: !done });
      let boundary;
      while ((boundary = pending.indexOf('\n')) !== -1) {
        const line = pending.slice(0, boundary);
        pending = pending.slice(boundary + 1);
        if (!line.trim()) continue;
        const event = JSON.parse(line);
        onEvent(event);
        if (event.type === 'done') doneEvent = true;
      }
      if (done) break;
    }
    if (pending.trim() || !doneEvent) throw new Error('Result stream ended unexpectedly.');
  } finally {
    if (!doneEvent) await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
