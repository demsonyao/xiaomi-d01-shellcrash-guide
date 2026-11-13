# Third-party assets are intentionally not committed

Place the tested private recovery assets in a sibling directory named `shellcrash-package`:

```text
shellcrash-package/
├─ ShellCrash.tar.gz
├─ zashboard.tar.gz                 optional dashboard
└─ cores/
   └─ mihomo-shellcrash-armv7.upx
```

See `SHA256SUMS.tested` and the repository-level `THIRD_PARTY.md`.

For a public GitHub release, prefer linking to the upstream projects and documenting the tested hashes. Do not redistribute XMiR-Patcher as a vendored copy while its repository lacks a clear root license file.
