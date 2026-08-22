// Handles AI commands via NVIDIA Nemotron API
import nemotron from "../utils/nemotron.js";

async function handleAi(args, env) {
  if (!args || args.length === 0) {
    throw new Error("Prompt required");
  }

  const prompt = args[0];
  const stream = args[1] === "--stream";

  // Call NVIDIA Nemotron API
  const response = await nemotron.chat(prompt, env.NVIDIA_API_KEY, { stream });

  return {
    response: response.text,
    tokens: response.tokens,
    model: "nemotron-3-ultra",
  };
}

export default handleAi;
