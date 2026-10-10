# Runtime source migration — 2026-10-10

The original airi-pc-bootstrap repository exceeds GitHub size quota. This clean public repository contains its current tracked source at d078e718 plus the verified runtime fixes (public tree a7a39fc), followed by bootstrap URL updates. Old history, Windows release links and model/training checkpoints remain in the original repository; nothing was purged or rewritten. The active offline training continues using its exact frozen source commits.

Runtime reconstruction scripts now use arancione3000/airi-pc-runtime. The private desktop workspace stays on arancione3000/airi-pc and has its own repository-scoped SSH deploy key. Private key files remain outside Git.

Only the runtime regression workflow is enabled in this new source repository. Original Generalist/training workflow definitions remain in the historical repository and active dedicated training repository. Runtime regression executes shared runtime/security/recovery tests and full coding/GUI/MCP/recovery checks.
