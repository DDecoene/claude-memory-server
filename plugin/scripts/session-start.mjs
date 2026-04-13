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
    const res = await fetch(`${URL}/session/start`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({
        session_id: data.session_id,
        cwd: data.cwd,
      }),
      signal: AbortSignal.timeout(5000),
    });
    if (res.ok) {
      const text = await res.text();
      if (text) process.stdout.write(text);
    }
  } catch {}
}

main();
