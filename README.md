# takeout

Export a Codex conversation and its workspace into a portable checkpoint that another agent can inspect and continue. The MVP includes a dependency-free Python CLI, source records, a handoff template, hash verification, and restoration into a separate directory.

## Quick start

Requires Python 3.9+, Git, and an installed, authenticated Codex CLI for live history reads. No model API key or model calls are required. Tested against `codex-cli 0.169.0-alpha.11.1`; app-server history APIs are experimental and may change.

```sh
python3 -m pip install -e .
takeout threads list
takeout export --thread THREAD_ID --workspace /absolute/repository \
  --output ../my-checkpoint \
  --objective 'Finish the parser' --next-action 'Reproduce and fix the failing test'
takeout inspect ../my-checkpoint
takeout verify ../my-checkpoint
takeout prepare ../my-checkpoint --destination ../continued-work --target gemini-cli
cd ../continued-work/workspace
# Give the receiving agent ../BOOTSTRAP.md
```

Without installation, use `python3 -m takeout` in this checkout. If Codex is not on PATH, pass `--codex /absolute/path/to/codex` before the command. Targets are `generic`, `gemini-cli`, and `antigravity`. The latter provides a plain bootstrap prompt, not a native session import. Gemini gets a `GEMINI.md` in the restored directory's parent, without replacing workspace instructions.

An offline source can be supplied with `export --source-json source.json` instead of `--thread`. It must contain `{"thread":{"id":"...","turns":[{"id":"...","items":[...]}]}}`. Its completeness is the caller's responsibility.

## Bundle format (version 1)

| Path | Purpose |
| --- | --- |
| `manifest.json` | Version, source, cutoff, hashes, file sizes, consistency and limitations |
| `START_HERE.md` | Reading order and continuation instructions |
| `project/tasks.json` | Objective, next action, evidence references, review/validation status |
| `threads/<id>/source.json` | Original accessible app-server record |
| `threads/<id>/events.jsonl` | All returned items, including unknown types and tool results |
| `threads/<id>/handoff.md` | Small handoff template |
| `workspaces/main/workspace.json` | Original HEAD, file modes, inventory and omissions |
| `workspaces/main/{baseline,index,working}/` | HEAD file tree, staged tree, working files |

The client consumes every page of thread discovery and turn history, requests full persisted items, and refuses summary-only responses. It never starts a turn or approves an action. Workspace capture is read-only and rechecked for changes before atomic publication. Conversation reads have a last-event cutoff; they are not an atomic snapshot across conversation and filesystem.

Restoration initializes a fresh local repository with a synthetic baseline commit, reconstructs the staged tree, then restores working files. Original HEAD identity is recorded for reference; original Git history and remotes are not transferred. This preserves selected file state and staged/unstaged differences without carrying repository configuration. Output and restore destinations must be new directories outside the source workspace/checkpoint.

## Boundaries and exclusions

This is the single-thread portable MVP. Project-wide selection, incremental exports, ZIP packaging, reference mode, attachment downloads, native destination APIs, and optional LLM summaries are future work. Multiple threads/workspaces are not yet supported.

The handoff is marked `requires_review`; it does not invent completed tasks or test results. Supply an objective/next action, then have the receiving agent inspect the evidence. Hidden reasoning, inaccessible context, credentials, running processes, and external attachments are not transferable; URLs remain in the source record.

Ignored Git files are omitted. Common credential files/directories, `.env*`, private-key files, dependency directories, symlinks, and submodules are omitted and listed in `workspace.json`. Tracked excluded files are omitted from baseline/index too. A heuristic scanner rejects common token/private-key patterns in conversation records and included file trees. This is not comprehensive secret detection: review checkpoints before sharing. A source containing a detected secret fails closed; it is never silently redacted. Plaintext files inherit local filesystem permissions. Manifest hashes detect corruption, not authenticity against an attacker who can rewrite the manifest.

## Validation

```sh
python3 -m unittest discover -s tests -v
```

Tests cover staged/unstaged edits, binary and untracked files, deletions, executable modes, unknown events, pagination, tampering, unsafe paths, secret rejection, and destination protection.

Keep real exports in the private checkpoint repository, outside this public checkout. Only synthetic fixtures belong in this repository.
