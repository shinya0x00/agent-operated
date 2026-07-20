# GTP v1 adapter boundary

## Authority

- Protocol owner: `github-task-protocol` `GTP.md`.
- Observed compatibility target: published CLI `1.0.1`, protocol projection `gtp: "1.0"`.
- Observation source:
  <https://github.com/shinya0x00/github-task-protocol/blob/4390cee29c1f7433666d19ffbdd6ff02c9b44178/GTP.md>

The adapter executes the public `gtp status ISSUE_URL` command and preserves its machine JSON under
`gtp_projection`. It does not parse Issue comments, fold Record history, validate Evidence, or derive state.

## Compatibility checks

Require all of the following before accepting a projection:

- `gtp --version` equals the configured executable compatibility version.
- `gtp_projection.gtp == "1.0"`.
- `gtp_projection.command == "status"`.
- `gtp_projection.issue_url` equals the requested canonical Issue URL.
- `gtp_projection.authority == "none"`.

Do not translate `state`, `halt_reason`, `next_action`, `primary_url`, `acquisition`, or Record content.

## Exit boundary

- CLI exit `0`: state acquisition completed. The state may still be `halt`; inspect the projection.
- CLI exit `2` with `state: null` and `acquisition: incomplete`: required GitHub observation was not acquired.
- Other exit or malformed projection: adapter incompatibility or execution failure.

None of these results authorizes mutation, merge, completion, or post-merge recovery.

## Stdout extraction

CLI 1.0.1 emits Japanese human text followed by deterministic formatted JSON and has no JSON-only flag.
The adapter searches for the first line containing exactly `{` whose remaining text parses as one JSON object.
Keep this behavior pinned to the executable compatibility test; do not generalize it into a GTP parser.
