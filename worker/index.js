import { validateRequest, decryptRequest } from "./utils/validate.js";
import { checkRateLimit, checkRequestDeduplication } from "./utils/security.js";
import {
  respondSuccess,
  respondError,
  respondEncrypted,
} from "./utils/respond.js";
import handlePing from "./commands/ping.js";
import handleAi from "./commands/ai.js";
import handleGh, { ghOpen, ghPush, ghPull } from "./commands/gh.js";
import handleSys from "./commands/sys.js";

const COMMAND_HANDLERS = {
  ping: handlePing,
  ai: handleAi,
  gh: handleGh,
  "warnetech-gh-open": ghOpen,
  "warnetech-gh-push": ghPush,
  "warnetech-gh-pull": ghPull,
  sys: handleSys,
};

async function handleRequest(request, env, ctx) {
  const url = new URL(request.url);

  // Health check endpoint
  if (url.pathname === "/health" && request.method === "GET") {
    return new Response(
      JSON.stringify({
        status: "ok",
        version: "0.1.0",
        timestamp: new Date().toISOString(),
      }),
      {
        headers: { "Content-Type": "application/json" },
      },
    );
  }

  // Main command endpoint
  if (url.pathname === "/cli" && request.method === "POST") {
    try {
      const body = await request.json();

      // Validate request and decrypt if needed
      const validation = await validateRequest(body, request.headers, env);
      if (!validation.ok) {
        return new Response(
          JSON.stringify(respondError(new Error(validation.error), 400)),
          { status: 400, headers: { "Content-Type": "application/json" } },
        );
      }

      let commandData = validation;
      if (body.encrypted_data) {
        try {
          commandData = await decryptRequest(
            body.encrypted_data,
            validation.signature,
            request.headers,
            env,
          );
        } catch (error) {
          return new Response(
            JSON.stringify(
              respondError(new Error(`Decryption failed: ${error.message}`), 400),
            ),
            { status: 400, headers: { "Content-Type": "application/json" } },
          );
        }
      }

      // Rate limit & replay checks (no-op without a KV binding — see
      // worker/utils/security.js).
      try {
        const apiKeyHash = request.headers.get("x-api-key-hash");
        const requestId = request.headers.get("x-request-id");
        await checkRateLimit(apiKeyHash, env);
        await checkRequestDeduplication(requestId, env);
      } catch (error) {
        return new Response(JSON.stringify(respondError(error, 429)), {
          status: 429,
          headers: { "Content-Type": "application/json" },
        });
      }

      const { command, args } = commandData;

      // Get handler
      const handler = COMMAND_HANDLERS[command];
      if (!handler) {
        return new Response(
          JSON.stringify(
            respondError(new Error(`Unknown command: ${command}`), 400),
          ),
          { status: 400, headers: { "Content-Type": "application/json" } },
        );
      }

      // Execute command
      const result = await handler(args, env);

      // Return success response
      return new Response(JSON.stringify(respondSuccess(result, command)), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    } catch (error) {
      console.error("Command error:", error);
      return new Response(JSON.stringify(respondError(error, 500)), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      });
    }
  }

  // 404
  return new Response(JSON.stringify({ error: "Not found" }), {
    status: 404,
    headers: { "Content-Type": "application/json" },
  });
}

export default {
  fetch: handleRequest,
};
