# Personal Profile

## Identity
<!-- Fill in your details -->
- Name, location, main projects
- Current focus areas

## Tech Stack
<!-- What you work with day-to-day -->
- Languages, frameworks, tools
- Deployment targets

## Preferences
<!-- How you like to work -->
- Code style preferences (e.g. flat files over heavy ORMs)
- Testing philosophy
- Review/approval preferences

## Projects
<!-- Active repos and their purpose -->
- project-name: one-line description

---

## Memory Instructions

You have access to a `memory` MCP server. Use it as follows:

**At the start of every session:**
1. Call `get_profile()` to load your profile
2. Call `get_recent_sessions(5)` to see what was recently worked on

**During a session — proactively store:**
- Key decisions: `store_memory(content, "decision", project="repo-name")`
- Important facts learned: `store_memory(content, "fact", project="repo-name")`
- Anything you'd want to know next session

**At the end of a session (or when asked):**
- Write a bullet-point summary of what was done and call:
  `store_memory(summary, "session", project="repo-name")`

**Searching past memory:**
- `search_memories("playwright auth")` — find relevant past context
- `list_memories(memory_type="decision")` — review past decisions

Keep the profile up-to-date. If you learn something new about preferences or
working style, call `update_profile()` with the full updated profile text.
