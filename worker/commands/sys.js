// Handles system operations (status, quotas, sync, etc)

const DEFAULT_DAILY_CALL_LIMIT = 100;

async function handleSys(args, env) {
  if (!args || args.length === 0) {
    throw new Error(
      "System action required: status|quota|sync|detect-anomalies|rollup",
    );
  }

  const action = args[0];

  switch (action) {
    case "status":
      return handleStatus(env);
    case "quota":
      return handleQuota(args[1], env);
    case "sync":
      return handleSync(env);
    case "detect-anomalies":
      return handleAnomalies(env);
    case "rollup":
      return handleRollup(env);
    default:
      throw new Error(`Unknown action: ${action}`);
  }
}

async function handleStatus(env) {
  return {
    status: "healthy",
    version: "0.1.0",
    uptime: Math.floor(Date.now() / 1000),
    timestamp: new Date().toISOString(),
    services: {
      nvidia_api: env?.NVIDIA_API_KEY ? "ok" : "not_configured",
      github_api: "ok",
      d1: "ok",
      r2: "ok",
      supabase: "ok",
      kv: env?.KV ? "ok" : "not_configured",
    },
  };
}

function todayKey() {
  return new Date().toISOString().slice(0, 10); // YYYY-MM-DD
}

// Quota tracking needs a KV binding to persist counts across requests (a
// Worker invocation has no memory of previous ones). Without KV bound,
// this returns the illustrative numbers from docs/05_CLI_COMMANDS.md
// clearly marked as such, rather than pretending to track real usage.
async function handleQuota(action, env) {
  if (action === "check") {
    if (!env || !env.KV) {
      return {
        api_calls: { used: 45, limit: 100 },
        storage: { used: 2.3, limit: 10 },
        rate_limit: { used: 60, limit: 100 },
        live: false,
        note: "example data — bind a KV namespace (env.KV) to enable live quota tracking",
      };
    }

    const limit = Number(env.DAILY_CALL_LIMIT) || DEFAULT_DAILY_CALL_LIMIT;
    const key = `quota:calls:${todayKey()}`;
    const used = parseInt((await env.KV.get(key)) || "0", 10) + 1;
    await env.KV.put(key, String(used), { expirationTtl: 60 * 60 * 24 * 2 });

    return {
      api_calls: { used, limit },
      storage: { tracked: false },
      rate_limit: { tracked: false, note: "see sys quota check headers via rate_limit:* KV keys" },
      live: true,
    };
  }

  if (action === "rollup") {
    return handleRollup(env);
  }

  throw new Error(`Unknown quota action: ${action}`);
}

// Baselines/signatures live in warnetech-server + warnetech_control_plane
// (see CLAUDE.md — this legacy Worker is not the canonical architecture),
// which this Worker has no network path to unless WARNETECH_SERVER_URL is
// configured. When it isn't, say so instead of fabricating a sync result.
async function handleSync(env) {
  const serverUrl = env?.WARNETECH_SERVER_URL;
  if (!serverUrl) {
    return {
      synced: false,
      reason: "WARNETECH_SERVER_URL not configured",
      baselines_updated: 0,
      signatures_updated: 0,
      timestamp: new Date().toISOString(),
    };
  }

  try {
    const response = await fetch(`${serverUrl}/api/sync`, { method: "POST" });
    if (!response.ok) {
      throw new Error(`server responded ${response.status}`);
    }
    const data = await response.json();
    return {
      synced: true,
      baselines_updated: data.baselines_updated || 0,
      signatures_updated: data.signatures_updated || 0,
      timestamp: new Date().toISOString(),
    };
  } catch (error) {
    return {
      synced: false,
      reason: `sync request failed: ${error.message}`,
      baselines_updated: 0,
      signatures_updated: 0,
      timestamp: new Date().toISOString(),
    };
  }
}

// Same caveat as handleSync: real anomaly detection lives in
// warnetech_control_plane (anomaly_engine.py), not in this Worker.
async function handleAnomalies(env) {
  const serverUrl = env?.WARNETECH_SERVER_URL;
  if (!serverUrl) {
    return {
      anomalies_detected: 0,
      source: "not_configured",
      timestamp: new Date().toISOString(),
    };
  }

  try {
    const response = await fetch(`${serverUrl}/api/anomalies`);
    if (!response.ok) {
      throw new Error(`server responded ${response.status}`);
    }
    const data = await response.json();
    return {
      anomalies_detected: data.anomalies_detected || 0,
      source: "warnetech-server",
      timestamp: new Date().toISOString(),
    };
  } catch (error) {
    return {
      anomalies_detected: 0,
      source: "error",
      error: error.message,
      timestamp: new Date().toISOString(),
    };
  }
}

// Aggregates this Worker's own KV-tracked quota counters. Without a KV
// binding there's nothing local to aggregate.
async function handleRollup(env) {
  if (!env || !env.KV) {
    return {
      rollup_completed: false,
      records_aggregated: 0,
      note: "bind a KV namespace (env.KV) to enable rollups",
      timestamp: new Date().toISOString(),
    };
  }

  const list = await env.KV.list({ prefix: "quota:calls:" });
  return {
    rollup_completed: true,
    records_aggregated: list.keys.length,
    timestamp: new Date().toISOString(),
  };
}

export default handleSys;
