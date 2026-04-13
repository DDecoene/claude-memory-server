#!/usr/bin/env node
const URL = process.env.MEMORY_URL || "http://localhost:8765";
const SECRET = process.env.MEMORY_SECRET || "";

function headers() {
  const h = { "Content-Type": "application/json" };
  if (SECRET) h["Authorization"] = `Bearer ${SECRET}`;
  return h;
}

function truncate(v, max = 4000) {
  if (typeof v === "string") return v.length > max ? v.slice(0, max) + "[…]" : v;
  if (typeof v === "object" && v !== null) {
    const s = JSON.stringify(v);
    return s.length > max ? s.slice(0, max) + "[…]" : v;
  }
  return v;
}

async function main() {
  let input = "";
  for await (const chunk of process.stdin) input += chunk;
  let data;
  try { data = JSON.parse(input); } catch { return; }

  // Determine hook type from available fields
  let hookType = "unknown";
  let payload = {};

  if (data.tool_name !== undefined) {
    hookType = "post_tool_use";
    payload = {
      tool_name: data.tool_name,
      tool_input: data.tool_input,
      tool_output: truncate(data.tool_output),
    };
  } else if (data.prompt !== undefined) {
    hookType = "prompt_submit";
    payload = { prompt: truncate(data.prompt) };
  } else {
    hookType = "stop";
    payload = data;
  }

  try {
    await fetch(`${URL}/observe`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({
        hookType,
        sessionId: data.session_id || "unknown",
        project: data.cwd || "",
        timestamp: new Date().toISOString(),
        data: payload,
      }),
      signal: AbortSignal.timeout(3000),
    });
  } catch {}
}

main();
