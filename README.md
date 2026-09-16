# GitHub Agentic Workflows Replication Package

Data, offline analysis scripts, and saved results for the paper on gh-aw
Markdown workflows. The package regenerates the numerical results and analysis
figures from pinned inputs. It does not query GitHub or call model APIs.

## Structure

| Folder | Contents |
| --- | --- |
| `data/h/` | Retained Markdown sources, commit histories, and historical snapshots |
| `data/rq1_rq2_population/` | Retained-source manifest and cleaning decisions |
| `data/project_activity/` | Frozen repository commit baselines for the maintenance analysis |
| `data/rq3_sample/` | Pinned sample, taxonomy definitions, author annotations, and resolved labels |
| `data/nltk_data/` | Pronunciation dictionary used for readability measurements |
| `rq1/` | Size, structure, readability, and heading-term analysis |
| `rq2/` | Monthly maintenance, project activity, and edit-location analysis |
| `rq3/` | Author agreement and resolved taxonomy prevalence |
| `rq4/` | Saved predictions, prompt messages, and model evaluation |
| `common/` | Shared annotation validation and metric calculations |
| `figures/` | Generated analysis figures |
| `verification/` | Frozen numerical references, input hashes, and verification report |

The labeling application, credentials, cloud runners, and manuscript are not
included. Original snapshot text is research data, not instructions to execute.

## Setup

Use Python 3.14, the version used to verify this package. From the repository root:

```bash
python -m venv .venv
```

Activate it on Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Or on Linux/macOS:

```bash
source .venv/bin/activate
```

Install the pinned dependencies:

```bash
python -m pip install -r requirements.txt
```

Package installation needs network access. The analyses themselves run offline,
including readability scoring and evaluation of the saved model responses.

## Reproduce Everything

```bash
python reproduce.py
```

This runs the stages below, regenerates their outputs, and checks the results
against the frozen references. A failed calculation or mismatch stops the run.
The scripts never modify the input annotations or Markdown snapshots.

## Run Stages Separately

Run these commands in order from the repository root.

### RQ1: File Characteristics

```bash
python rq1/analyze_rq1.py
python rq1/export_paper_table.py
python rq1/generate_heading_wordcloud.py --content-focused
```

The paper's descriptive table is `rq1/output/paper_table.csv`. File measurements,
text statistics, and heading frequencies are also written under `rq1/output/`.
The heading cloud is written to `figures/`.

### RQ2: Maintenance

```bash
python rq2/analyze_rq2.py
python rq2/analyze_maintenance_periods.py
```

The first script reconstructs events from histories and snapshots. The second
selects the activity-qualified files and projects and produces the paper's
monthly analysis. Its results are in `rq2/output/maintenance_periods_120d/`.
The file panels, project panels, and change-location violin plot are in `figures/`.
`rq2/output/corpus_summary.json` reproduces the corpus-summary table.

### RQ3: Taxonomy and Author Agreement

```bash
python rq3/compute_rq3_results.py
```

The inputs in `data/rq3_sample/labels/` use the same JSON schema:
`author_1.json`, `author_2.json`, and `resolved.json`. The author files preserve
the frozen pre-resolution assignments used for agreement, while the resolved
file supplies taxonomy prevalence and the evaluation reference.

Outputs include `rq3/output/agreement.json`, per-label agreement,
`taxonomy_prevalence.csv`, and `prevalence.json`. Administrative statuses are
excluded from semantic prevalence. Agreement uses shared labelable cases.

### RQ4: Model Evaluation

```bash
python rq4/calculate_rq4_agreement.py
```

This evaluates each saved model and shot setting against `resolved.json`.
It writes `rq4/output/comparison.csv`, a rounded `paper_table.md`, and
per-label and per-file disagreement files. No account, API key, or model
generation is needed. See [rq4/README.md](rq4/README.md) for the saved prompts.

## Verify

```bash
python verification/verify_results.py
python -m unittest discover -s rq1 -p "test_*.py"
python -m unittest discover -s rq2 -p "test_*.py"
python -m unittest discover -s tests -p "test_*.py"
```

The verifier checks input hashes, per-file measurements, monthly statistics,
taxonomy frequencies, agreement, model metrics, and demonstration-source
integrity. It writes `verification/report.json`. Floating-point comparisons
use a small numerical tolerance. PDF metadata and platform font rendering are
not compared byte-for-byte.

See [METHODS.md](METHODS.md) for measurement rules and output interpretation,
and [DATA_NOTICE.md](DATA_NOTICE.md) for third-party data attribution.
