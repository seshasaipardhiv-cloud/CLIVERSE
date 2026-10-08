# Member 1 CLI Usage

Run from a source checkout with Python 3.11; no package installation is
required:

```bash
python3.11 env.py --help
```

## Initialize a project

```bash
python3.11 env.py init --root /path/to/project
python3.11 env.py status --root /path/to/project
```

Initialization creates `.envcore/config.json` and refuses to overwrite an
existing configuration.

## Plan a task

Member 2's memory/rules provider is not yet connected to the CLI. Explicitly
select context-free mode and provide any known project context:

```bash
python3.11 env.py plan "Add a CLI status command" \
  --context "Python 3.11 project using SQLite" \
  --requirement "Use only the standard library" \
  --constraint "Do not call hosted services" \
  --without-memory
```

Unresolved critical questions can be supplied explicitly; the planner returns
`needs_clarification` without a structured task:

```bash
python3.11 env.py plan "Add authentication" \
  --clarification "Which identity provider should be used?" \
  --without-memory
```

The current planner does not infer ambiguity with a live model. A configured
caller may use Laya to classify requests and pass unresolved questions; live
Laya inference is not verified.

## Persist sessions and inspect Git

```bash
python3.11 env.py session start --root /path/to/project --request "Add status"
python3.11 env.py session list --root /path/to/project
python3.11 env.py session show --root /path/to/project <session-id>
python3.11 env.py session finish --root /path/to/project <session-id>

python3.11 env.py git status --root /path/to/project
python3.11 env.py git diff --root /path/to/project
python3.11 env.py git history --root /path/to/project
python3.11 env.py git undo-preview --root /path/to/project --session-id <id>
```

Git inspection is read-only. A history entry has a CLIVERSE session ID only
when the commit contains a `CLIVERSE-Session:` trailer. Undo preview is
read-only and will only show the current clean `HEAD` if it has the requested
session trailer.

## Execution status and data boundaries

- `execute_guarded()` is a library API only. It requires an injected
  authorizer; the CLI does not launch an external AI CLI until Member 4 confirms
  an authenticated, scoped integration.
- Session-linked Git commit and revert are library APIs only and also require
  explicit confirmation and an authorizer. The CLI does not perform Git
  mutations until Member 4 confirms a safe integration.
- Session requests and events are stored locally in
  `.envcore/cliverse.sqlite3`. The data is not encrypted at rest.
- No RAG provider, model weights, hosted API or AI CLI is bundled or started.
