# Writ turn rule (Grok)

Grok's `UserPromptSubmit` hook cannot inject text into the model. Writ writes the retrieved rule bundle to `$GROK_PLUGIN_DATA/current-rules.md` (or `$WRIT_DATA/current-rules.md`).

Before you write or edit source, or run a mutating shell command:

1. Read that file if it exists.
2. Treat its `--- WRIT RULES ---` / always-on blocks as binding for this turn.
3. In Work mode, do not write implementation until the user has typed `/writ-approve` after approving the Grok plan with `a`. A denied write means the gate is still closed.

Do not invent rule IDs. If the sidecar is missing, continue, and expect the write gate to refuse illegal writes.
