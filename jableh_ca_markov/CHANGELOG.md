# Changelog

## v1.0.0 (2026)

Initial packaging of the full Jableh CA-Markov pipeline into a
reproducible, tested Python package, consolidating code developed
across the manuscript's revision process.

### Fixed

Two numerical issues were caught while writing `tests/test_markov_ipf.py`
and are corrected in this release. Both are documented in detail in the
relevant docstrings (`config.build_seed_matrix`, `markov_ipf.seeded_ipf`).

1. **Structural zero column for `grass` in the seed transition matrix.**
   The domain-informed `off_pref` dictionaries in `build_seed_matrix()`
   listed only the ecologically "plausible" destination classes for each
   origin class, and none of them listed `grass` as a possible
   destination. This made the `grass` column of the seed matrix
   unreachable from any class other than grass itself -- a "structural
   zero" that IPF/RAS cannot repair (the algorithm can only *rescale*
   existing nonzero cells, never create new ones). As a result, the
   fitted transition probabilities *into* grass were not reliable.
   **Fix:** every class now carries a small (`min_reachability=0.02`)
   default weight toward every other class not explicitly listed in
   `off_pref`, guaranteeing every column has at least one nonzero
   off-diagonal contributor -- a necessary condition for IPF/RAS to be
   able to match arbitrary observed marginals.

2. **Marginal-total mismatch between consecutive Dynamic World epochs.**
   `sum(area_t1)` and `sum(area_t2)` for any given year pair are not
   *exactly* equal in the real Jableh data (differing by up to ~2.7e-5
   relative, i.e. up to ~0.02 km^2 across the full 2015-2026 record),
   because the number of valid, non-cloud-masked pixels differs
   slightly between annual Dynamic World composites. IPF/RAS can only
   satisfy two marginals *exactly and simultaneously* when their totals
   are equal; left unaddressed, the alternating row/column rescaling
   settles into a small, stable, non-vanishing oscillation instead of a
   true fixed point, and the previous convergence check (comparing
   cell-wise change between full iterations) could falsely report
   convergence mid-oscillation.
   **Fix:** `seeded_ipf()` now (a) proportionally rescales the target
   marginal to match the source marginal's total before fitting
   (`rescale_to_common_total=True` by default -- standard practice for
   IPF with inconsistent marginal totals), and (b) checks convergence
   via the actual residual against both target marginals directly,
   rather than via cell-wise change between iterations.

### Practical impact on previously reported figures

Re-running the corrected pipeline against the full 2015-2026 Jableh
area series changes the built-up, trees, and crops trajectories by
**less than 0.6%** relative to the previously reported values (e.g.
2030 built-up area: 57.12 km^2 corrected vs. 57.19-57.43 km^2
previously reported across earlier manuscript drafts) -- within
existing rounding and not material to any conclusion in the
manuscript. The `grass` class (already flagged in the manuscript's own
text as the highest-uncertainty, "noisy bookkeeping" class, given its
CV > 0.49 across the eleven fitted year-pairs) is now computed
correctly rather than being artificially forced toward zero
persistence; this does not affect any claim made in the manuscript,
since grass was never used to support a substantive finding.

No other class or table in the manuscript is affected.
