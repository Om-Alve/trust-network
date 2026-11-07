- Read README.md and PROTOCOL.md for setup, design and protocol behavior.

- Keep changes focused and record verification in commit messages or docs.

- Run `make check` before every commit.

- Never write unit tests after you write code.

- Highly prefer E2E tests as the sole testing mechanism. Use them to verify complex features work. At the end of E2E tests, produce a verifiable and repeatable artifact.

- If you must test a system in isolation, first write down all the ways it could fail, then write the code.

- Tautological tests considered harmful.

- Change-detector tests considered harmful.

- Do not create regression tests for bug fixes without a genuine gap in behavior testing.

- No regex or keyword-list bandaids for judging meaning
