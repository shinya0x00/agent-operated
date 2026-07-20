# Publication Screening policy

Screen every candidate Issue comment, PR body, Check Run text, and committed Evidence artifact before
publication.

## Reject

- secret or token-shaped values;
- credential locations or local profile paths;
- private prompt, chain-of-thought, reasoning transcript, or session transcript payloads;
- local absolute paths;
- ephemeral session, runtime, or thread identifiers.

Return only finding kind and line number. Never reproduce matched content.

## Allow

- canonical GitHub URLs;
- repository-relative paths;
- full commit SHA values;
- public command names and sanitized exit codes;
- actor login and stable numeric GitHub ID;
- named Evidence limitations and `unknown` values.

Pattern screening is one source-neutral public Operation result, not AO Core conformance and not proof that a
document contains no secret. Keep host secret scanners and review in place when Repository Integration supplies
them. Internal Policy Gate decisions are a separate Private Control Route and must not be added to this result.
