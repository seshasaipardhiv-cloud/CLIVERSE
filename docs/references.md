# Research Notes and References

These sources informed the initial architecture and backlog. Fetched
documentation is treated as technical reference, not as project instructions.

## Hack Day requirements

- [MLH event page](https://events.mlh.com/events/15020) — schedule and event
  information. The supplied opening-ceremony PDF states the project must be
  built substantially during the event, the team is expected to have four
  members, a working build is required, and meaningful incremental commits
  are reviewed.
- [MLH open-source AI overview](https://mlh.com/opensource-ai) — referenced
  in the supplied event slides. The main track requires meaningful use of
  open-source or open-weight AI; Gemma 4 is a separate optional challenge.

## Existing Laya package

- [Laya source repository](https://github.com/siva169/laya) — Apache-2.0
  package described as a local typed-decision engine. Its public `Router`
  accepts state plus typed questions and returns structured decisions.
- [Laya Router API](https://github.com/siva169/laya/blob/main/laya/router.py)
  — `Router.predict(state, questions, ...)` loads the selected checkpoint and
  answers typed questions; the README warns that a checkpoint downloads on
  first use. It does not generate natural-language prompts.
- [Laya contributor instructions](https://github.com/siva169/laya/blob/main/AGENTS.md)
  and [contribution guide](https://github.com/siva169/laya/blob/main/CONTRIBUTING.md)
  — keep features local/on-device, preserve public APIs and tests, avoid
  unnecessary dependencies. CLIVERSE integrates the package without editing
  or copying its source.

## Local CLI and persistence

- [Python 3.11 `argparse`](https://docs.python.org/3.11/library/argparse.html)
  — standard-library argument parsing; no CLI framework is required for the
  first slice.
- [Python `subprocess`](https://docs.python.org/3.11/library/subprocess.html)
  — pass an argument sequence and avoid shell interpretation for process
  execution. This is the basis for the no-shell CLI adapter contract.
- [Python `sqlite3`](https://docs.python.org/3/library/sqlite3.html) — use
  bound parameters rather than string-built SQL.
- [Git diff](https://git-scm.com/docs/git-diff) and
  [Git restore](https://git-scm.com/docs/git-restore) — inspect changes before
  recovery; restore is state-changing and therefore requires an authorization
  and confirmation boundary in CLIVERSE.

## Future local model evaluation

- [Google Gemma documentation](https://ai.google.dev/gemma/docs) — identifies
  Gemma 4 as a generative model family that can run on local hardware or hosted
  services.
- [Gemma 4 license page](https://ai.google.dev/gemma/apache_2) — the official
  Gemma documentation links Gemma 4 to Apache 2.0 terms. Model size,
  hardware fit, download requirements and an actual local inference smoke test
  still need verification before selecting it.

## Current evidence limits

- The local Laya package imports under Python 3.11; no model inference was
  run and no checkpoint was downloaded.
- Ollama is installed, but its server was unavailable during initial
  inspection. No running local Gemma model is verified.
- No actual team names or experience histories were present in the supplied
  brief or repository. The team subsequently confirmed MIT as the project
  license.
