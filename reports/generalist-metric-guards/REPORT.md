# Learning metric integrity — 2026-11-02

Source baseline: `291b688` in `arancione3000/airi-pc-runtime`.

The language gates treated a measured repetition rate of zero as missing and
replaced it with 1.0. A candidate reducing repetition from 0.10 to 0.00 was
therefore rejected as a regression. Conversely, an anchor with zero repetition
was interpreted as 1.0, silently losing its existing +0.08 repetition boundary.
The quality score also replaced zero NLL with 1,000,000. NaN diagnostic values
could pass the segment gate because comparisons with NaN all return false.

The correction distinguishes missing values from measured zero and rejects
missing core metrics or non-finite/malformed numeric evidence in the durable,
segment, anti-collapse and rehabilitation gates. Invalid metrics also cannot
justify widening through the fragility decision. Numeric thresholds, the
protected suite, anchor, optimizer, model and token accounting are unchanged.

Regression tests exercise acceptance of genuine zero-repetition improvement,
the unchanged zero-anchor boundary, zero NLL scoring, and invalid evidence in
each of the before/candidate/anchor reports across all compared diagnostics.

Validation:

- Focused affected checks: **113 passed** (repeated after restoring snapshots).
- Broader Phase-5, learning-efficiency, LM and retention suites: **345 passed,
  1 skipped, 17 failed**. All 17 failures reproduce on the pristine source:
  16 need historical Generalist workflow files absent from this migrated
  runtime repository; one Mathesis proof fixture lacks the proof dependency in
  the selected environment. No tests or workflows were changed to hide them.
- Python compilation and `git diff --check`: passed.

The patch was saved and snapshots restored after the broader verification
failure, as required by `AGENTS.md`. Baseline failures were reproduced, then the
same patch was reapplied and the affected checks rerun successfully.

This is a correctness and evidence-integrity repair. It does not establish
improved language capability, sustained accepted learning, or a higher benchmark
score, and it has not modified or deployed the frozen offline-training source.
