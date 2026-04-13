#!/usr/bin/env node
const URL = process.env.MEMORY_URL || "http://localhost:8765";
const SECRET = process.env.MEMORY_SECRET || "";

function headers() {
  const h = { "Content-Type": "application/json" };
  if (SECRET) h["Authorization"] = `Bearer ${SECRET}`;
  return h;
}

async function main() {
  let input = "";
  for await (const chunk of process.stdin) input += chunk;
  let data;
  try { data = JSON.parse(input); } catch { return; }

  try {
    await fetch(`${URL}/session/end`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ sessionId: data.session_id || "unknown" }),
      signal: AbortSignal.timeout(5000),
    });
  } catch {}
}

main();
