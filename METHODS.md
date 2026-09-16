# Measurement and Reproduction Notes

## Corpus and Identity

The retained-source manifest identifies each repository, Markdown path, and
pinned latest commit. `data/h/` contains only retained sources. Historical
snapshots remain unchanged. `history.json` links commit metadata, file changes,
and snapshots. Repeated SHAs across Markdown paths represent different file
events, not duplicate repository commits.

The cleaning manifests record the original decisions. Non-English detection
used `langdetect`, with a fixed seed, on body text excluding code and frontmatter.
Empty bodies were excluded. The cleaning summary records the thresholds and
the handling of uncertain text. The replication starts from that frozen retained
population rather than redetecting or fetching a changing population.

## RQ1

`analyze_rq1.py` selects the latest available snapshot per retained source.
Markdown tokens distinguish headings, lists, tables, and fenced code. YAML
frontmatter is measured separately. Body-word counts exclude fenced and inline
code contents, URL targets, image alternative text, and HTML comments.

Readability uses paragraph and list text, excluding headings, tables, and code
blocks. Inline code and template expressions become neutral placeholders.
Sentence, syllable, and readability statistics require at least 100 words and
an English detection score of 0.80. Other metrics use the full retained corpus.
Flesch Reading Ease is
`206.835 - 1.015 * (words / sentences) - 84.6 * (syllables / words)`.
The exact tokenization and sentence rules are in the pinned `textstat` version.
The bundled CMU dictionary and pinned hyphenation package stabilize syllable counts.

Pictographic symbols are Unicode `Extended_Pictographic` code points, not model
tokens or syllables. The heading cloud uses parser-recognized headings, frozen
stopwords, and a fixed random seed. The CSV of frequencies is the numerical
reference, independently of image layout.

## RQ2

The event reconstruction script reads recorded GitHub additions/deletions and
compares consecutive available snapshots to attribute changes to frontmatter
or body. Initial observed events are not maintenance. Unknown transitions
remain explicit rather than being silently counted as unchanged.

The published monthly analysis selects paths with at least 120 days between
their first and last observed changes. File day zero is that path's first
appearance. Project day zero is its earliest collected Markdown appearance.
Project measurements include every retained path in the selected repositories,
including paths introduced during the window.

The implementation uses fixed elapsed-day windows `[0,28]`, `(28,56]`,
`(56,84]`, and `(84,112]`, displayed as months in the paper. It does not use
calendar-month boundaries. Zero-activity windows are retained.

- File commits count maintenance events. Project commits deduplicate SHAs
  across Markdown paths within the project.
- Churn is additions plus deletions, divided by the time-weighted mean snapshot
  line count during that window, multiplied by 100. It is not cumulative churn.
- Size is physical lines at the window endpoint, with snapshots carried forward
  between changes. Deleted or renamed-away paths have zero size until reappearing.
- Repository share divides distinct Markdown maintenance commits by all repository
  commits in the identical window. A zero denominator yields a missing share,
  not zero percent. The frozen baseline includes every Markdown commit used.
- Adjacent-month tests are project-paired, exact two-sided sign tests. Ties are
  omitted from the binomial test. Holm correction covers the full family of
  metric-by-month tests. File panels are descriptive.
- Change-location observations are per-project percentages of maintenance
  commit-file events. Both-region events enter both numerators. Unknown and
  non-content events remain in the denominator. Projects with no maintenance
  events appear as zero in both distributions, matching the paper's convention.

This selected sample describes sustained-activity sources, not the probability
that a newly created workflow will receive maintenance. The project-commit share
provides context, not a causal control.

## RQ3

Both author exports are aligned by stable sample ID, repository, and workflow
name. The second author's original CSV did not record commit hashes. Its export
therefore uses the shared sample manifest's pinned URL, not an independently
verified record of which commit the author viewed. Missing, non-English, and
cannot-label statuses are preserved and excluded where appropriate.

Agreement and Cohen's kappa pool binary file-label decisions over shared
labelable files. Jointly absent labels contribute to agreement. A category is
present when any of its subcategories is present. Undefined kappa for a constant
vector is represented by JSON `null`.

Prevalence uses only resolved semantic labels. Each label counts once per file,
and a category counts once regardless of the number of assigned children.
Percentages need not sum to 100. The script verifies that resolved assignments
retain shared labels and are drawn from the union of the author assignments.
The exports contain assignments and statuses, not application session metadata.

## RQ4

The saved outputs are evaluated against the same resolved reference as RQ3.
Cannot-label cases are excluded from scoring but their saved predictions remain
available. IDs and snapshot hashes must match. Missing or failed predictions
raise errors and are never imputed as empty predictions.

Agreement and Cohen's kappa use pooled binary file-label decisions. Precision,
recall, and F1 are micro-averaged over the positive-label confusion counts.
Independent scikit-learn calculations check the implementation.

Evidence lines are checked against the pinned source text. This verifies that
the cited text exists, not that the predicted label is semantically correct.
Few-shot source examples exclude the target file. These experiments are not
independent train/test splits: other sampled files may supply demonstrations.
Reported model differences are descriptive, without repeated-generation tests.
