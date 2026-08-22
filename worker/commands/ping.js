// Ping command - Test connectivity
// Returns: { message: "pong", timestamp: ISO_STRING }

async function handlePing(args, env) {
  return {
    message: "pong",
    timestamp: new Date().toISOString(),
  };
}

export default handlePing;
