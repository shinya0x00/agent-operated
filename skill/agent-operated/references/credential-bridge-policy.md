# Credential bridge policy

## Public read

Remove ambient `GH_TOKEN` and `GITHUB_TOKEN`, then execute the GTP reader anonymously. Do not introduce a
credential when the selected GitHub resource is public.

## Private read

1. Remove ambient `GH_TOKEN` and `GITHUB_TOKEN`.
2. Use the isolated GitHub CLI profile already selected by the host.
3. Read `gh api user` and compare login plus numeric ID with the declared Machine Account profile.
4. Only after a match, read `gh auth token` from that same profile.
5. Pass the value as `GITHUB_TOKEN` only in the GTP child process environment.
6. Remove the value from the adapter environment immediately after the child returns.

## Output boundary

Never include any of the following in stdout, stderr, exceptions, findings, tests, or durable records:

- token value or prefix;
- `GH_CONFIG_DIR` value;
- credential file or keychain path;
- raw child stderr;
- environment dump;
- command line containing a credential.

Report only a low-cardinality finding such as `private_read_actor_unverified` or
`private_read_credential_unavailable`.

Credential verification proves the GitHub principal observed through that circuit. It does not prove the model,
runtime process, operator intent, or correctness of the requested mutation.
