import nemotron from "../../worker/utils/nemotron.js";

function sseResponse(chunks) {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(stream, { status: 200 });
}

describe("nemotron streaming", () => {
  let originalFetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("requests stream_options.include_usage when streaming", async () => {
    let capturedBody;
    globalThis.fetch = async (_url, opts) => {
      capturedBody = JSON.parse(opts.body);
      return sseResponse([`data: [DONE]\n\n`]);
    };

    await nemotron.chat("hi", "key", { stream: true });
    expect(capturedBody.stream_options).toEqual({ include_usage: true });
  });

  it("does not set stream_options for non-streaming requests", async () => {
    let capturedBody;
    globalThis.fetch = async (_url, opts) => {
      capturedBody = JSON.parse(opts.body);
      return {
        ok: true,
        json: async () => ({
          choices: [{ message: { content: "hi" } }],
          usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 },
        }),
      };
    };

    await nemotron.chat("hi", "key", { stream: false });
    expect(capturedBody.stream_options).toBeUndefined();
  });

  it("assembles streamed text and reads real usage from the final chunk", async () => {
    globalThis.fetch = async () =>
      sseResponse([
        `data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n`,
        `data: {"choices":[{"delta":{"content":" world"}}]}\n\n`,
        `data: {"choices":[],"usage":{"prompt_tokens":5,"completion_tokens":2,"total_tokens":7}}\n\n`,
        `data: [DONE]\n\n`,
      ]);

    const result = await nemotron.chat("hi", "key", { stream: true });
    expect(result.text).toBe("Hello world");
    expect(result.tokens).toEqual({ input: 5, output: 2, total: 7 });
  });

  it("defaults to zeroed tokens if the API never sends a usage chunk", async () => {
    globalThis.fetch = async () =>
      sseResponse([
        `data: {"choices":[{"delta":{"content":"Hi"}}]}\n\n`,
        `data: [DONE]\n\n`,
      ]);

    const result = await nemotron.chat("hi", "key", { stream: true });
    expect(result.text).toBe("Hi");
    expect(result.tokens).toEqual({ input: 0, output: 0, total: 0 });
  });

  it("tolerates SSE frames split across chunk boundaries", async () => {
    const full = `data: {"choices":[{"delta":{"content":"Hello world"}}]}\n\ndata: [DONE]\n\n`;
    const mid = Math.floor(full.length / 2);
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(full.slice(0, mid)));
        controller.enqueue(encoder.encode(full.slice(mid)));
        controller.close();
      },
    });
    globalThis.fetch = async () => new Response(stream, { status: 200 });

    const result = await nemotron.chat("hi", "key", { stream: true });
    expect(result.text).toBe("Hello world");
  });
});
