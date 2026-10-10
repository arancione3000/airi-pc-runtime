# AIRI-PC runtime reliability — 2026-10-10

Maintenance and supervision now validate readiness response bodies, check actual display availability, respect the workspace and virtual environment, reject invalid recovery levels, and launch restarts without shell interpolation. The contract accepts the configured display only when the observed desktop matches it. Startup probes installed GUI packages without importing them before Xvfb starts.

Persistent job status and attach read bounded UTF-8 log suffixes instead of whole log files. Existing cancellation handling and live telemetry are preserved.

Verification: 136 selected PC regression tests passed locally, with only the test requiring a running desktop excluded. All updated display/health/log/search tests passed. The corresponding private runtime passed 137 tests, complete coding and graphical/browser/MCP self-tests, and recovery after terminating the actual server:
https://github.com/arancione3000/airi-pc/actions/runs/38049085611

Project indexing now excludes caches, binary/oversized files and runtime credentials. File reads and context packs are bounded, and symlinks cannot escape the workspace.

The original AIRI computer has been restored and readiness verified. Its full native self-test passed all 33 checks, and a cold control-plane/index bootstrap completed in 0.457 seconds without disrupting readiness. These changes concern runtime reliability; conversational quality still requires the existing model qualification process.

Publication: GitHub rejected the public repository write with HTTP 403, "Repository is above its size quota." The verified public changes are retained as a patch in the private runtime repository. Public main remains d078e718dfba0d68babd31de90fa55c0beac1951. No repository history was deleted.

## Browser-cache follow-up — 2026-10-10

Cold restore exposed a diagnostic bug: airi-selftest searched HOME/.cache while startup installed Chromium in the workspace cache. The self-test now shares the startup/browser cache and respects an explicit PLAYWRIGHT_BROWSERS_PATH, including paths containing spaces. Two regression cases were added. Cache guard and configured-install checks passed locally; complete native workflow1390fdbc3a3ef365bdc7f19653bb8458e7f93327 passed (139 Python tests plus coding, GUI/MCP and real server recovery): https://github.com/arancione3000/airi-pc/actions/runs/38057870170.

The current provider workspace was restored from private backupa57fb4edf077fccf64ea8d8a43a475e2906e12a5:184 file hashes and213 Git objects verified. Its startup completed and readiness/status GUI/browser/MCP/source checks returned true. Direct provider commands subsequently timed out; deployment/readback of this diagnostic follow-up on that host is pending. The autonomous GitHub training cycle is independent of this provider connection.


## Operational defects corrected — 2026-10-10

Declared scope: computer/requirements.txt, scripts/airi-coding-selftest, tests/test_runtime_reliability.py and operational documentation/public patch. Added httpx/httpx2/requests to bootstrap dependencies, so test clients no longer require manual installation. Coding self-test now runs in an owned temporary workspace, cleans it on success/failure and never deletes the existing live diagnostic folder or overwrites user task/recovery/memory. Two regression tests verify preservation of real state and propagation of child failure.

Native verification: pip check passed;141 tests passed in14.56s;33 graphical/browser/MCP/coding/services checks passed, ALL=True and wrapper exit0. Readiness passed. Old diagnostic task/recovery leftovers were backed up and finished only after matching the exact fixture goal and scope; real user tasks were untouched. Post-test task_active=false and recovery_active=false.

Persistence remains honestly blocked: native private Git origin has no usable Git authentication, so remote_sha=null and persistent=false. Connected GitHub publication by the assistant works, but it does not install standalone Git credentials in the desktop. Original public repository remains over quota; complete patch is published separately without deleting history. Frozen training branch remains unchanged. Current numerical progress5760 new updates /4499.53s compute; last assessment7/16 dialogue vs1/16 baseline but13/28 legacy vs15/28 baseline, so overall improvement and production qualification are not established.
