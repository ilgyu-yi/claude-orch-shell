# Changelog fragments

Each PR with an observable change drops **one** fragment here so releases can be
consolidated mechanically (Keep a Changelog).

## Contract

- Path: `changelog_unreleased/<category>/<N>.md` where `<N>` is the PR number.
- Category ∈ `added` · `changed` · `deprecated` · `removed` · `fixed` · `security`.
- Content: a single one-line markdown bullet starting with `- `, containing `(#<N>)`
  where `<N>` matches the filename stem. No frontmatter, no multi-line prose.

Example — `changelog_unreleased/added/12.md`:

```
- Add the `validation/` strategic-mode guard that asserts a strategic research document cites no code. (#12)
```

PRs with no end-user-observable change (pure internal refactor, CI-only) carry the
`skip-changelog` label instead of a fragment. At release time `CHANGELOG.md` gains a
`## [X.Y.Z] — DATE` section and consumed fragments are deleted.
