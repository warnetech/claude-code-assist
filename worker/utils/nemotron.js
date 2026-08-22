// NVIDIA Nemotron API client

const NVIDIA_API_URL = "https://integrate.api.nvidia.com/v1/chat/completions";
const MODEL = "nvidia/nemotron-3-ultra";

async function chat(prompt, apiKey, options = {}) {
  const { stream = false } = options;

  const request = {
    model: MODEL,
    messages: [
      {
        role: "system",
        content:
          "You are Claude, an AI assistant for the Warnetech command-line system. Provide concise, actionable responses.",
      },
      {
        role: "user",
        content: prompt,
      },
    ],
    temperature: 0.7,
    max_tokens: 2048,
    stream,
  };

  if (stream) {
    // OpenAI-compatible streaming APIs (NVIDIA's included) emit a final
    // chunk carrying `usage` (with an empty `choices` array) when this is
    // set, which is the only way to get real token counts out of a
    // streamed response instead of hardcoding zeros.
    request.stream_options = { include_usage: true };
  }

  try {
    const response = await fetch(NVIDIA_API_URL, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw new Error(
        `NVIDIA API error: ${response.status} ${response.statusText}`,
      );
    }

    if (stream) {
      return handleStreamingResponse(response);
    } else {
      return handleBufferedResponse(response);
    }
  } catch (error) {
    throw new Error(`Nemotron request failed: ${error.message}`);
  }
}

async function handleBufferedResponse(response) {
  const data = await response.json();

  if (data.error) {
    throw new Error(`Nemotron error: ${data.error.message}`);
  }

  const choice = data.choices[0];
  const text = choice.text || choice.message?.content || "";

  return {
    text,
    tokens: {
      input: data.usage?.prompt_tokens || 0,
      output: data.usage?.completion_tokens || 0,
      total: data.usage?.total_tokens || 0,
    },
  };
}

async function handleStreamingResponse(response) {
  // Buffer the SSE stream into a single result. We don't forward
  // incremental chunks to the CLI (see docs/07_AI_INTEGRATION.md's
  // streaming section for the aspirational live-relay version) — this
  // buffers server-side and returns the assembled text plus usage, which
  // is captured from the final `data: {...,"usage":{...}}` chunk that
  // stream_options.include_usage triggers.
  const reader = response.body.getReader();
  let text = "";
  let usage = null;
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += new TextDecoder().decode(value, { stream: true });
    const lines = buffer.split("\n");
    // Keep the last (possibly incomplete) line in the buffer for the next read.
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data: ")) continue;

      const payload = trimmed.slice(6);
      if (payload === "[DONE]") continue;

      let data;
      try {
        data = JSON.parse(payload);
      } catch (_error) {
        continue; // Skip malformed/partial SSE frames rather than failing the whole stream.
      }

      if (data.choices?.[0]?.delta?.content) {
        text += data.choices[0].delta.content;
      }
      if (data.usage) {
        usage = data.usage;
      }
    }
  }

  return {
    text,
    tokens: {
      input: usage?.prompt_tokens || 0,
      output: usage?.completion_tokens || 0,
      total: usage?.total_tokens || 0,
    },
  };
}

async function optimizePrompt(userPrompt, context = {}) {
  let optimized = userPrompt;

  // Add context if available
  if (context.language) {
    optimized = `[${context.language}]\n${optimized}`;
  }

  // Add format constraint if applicable
  if (context.wantCode) {
    optimized += "\n\nProvide code only, no explanation.";
  }

  // Ensure completeness
  if (!optimized.includes("?") && !optimized.endsWith(".")) {
    optimized += ".";
  }

  return optimized;
}

export default { chat, optimizePrompt };
