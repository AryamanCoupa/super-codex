# Contributing

Use Python 3.11+ on macOS or Linux. Run:

```bash
python3.11 -m unittest discover -s tests -v
python3.11 -m codex_harness demo --output .harness/contributor-demo
git diff --check
```

Keep runtime dependencies minimal. Add behavioral tests when changing orchestration, accounting, process cleanup, verification or pack promotion. Keep smoke simulations clearly separate from live-model results. Test configuration snippets against the supported Codex version and cite upstream documentation when adding integrations.

The default `sc` controller must not fall back to native editing when preparation, accounting or verification fails. Preserve pack acceptance requirements, include preparation spending, and derive completion claims from run evidence. Keep `--native` explicitly advisory. Controller changes should exercise failure paths and source/base checks as well as successful patch application; do not replace meaningful acceptance criteria with always-passing checks.

The default suite skips the real GEPA integration when its optional dependency is absent. To exercise that optimizer with offline rollouts:

```bash
python -m pip install -e '.[gepa]'
python -m unittest discover -s tests -p test_experimental_gepa.py -v
```

Fine-tuning contract tests inject lightweight dependencies and do not train a model. Changes to the optional training backend should also document a real hardware smoke run when available. See [experimental workflows](docs/EXPERIMENTS.md) and [research coverage](docs/RESEARCH_COVERAGE.md) before adding another technique.

A performance PR should state the failure being fixed, the proposed change, the dataset split, model/policy versions, checks, total costs and uncertainty. Do not advertise a quality gain from a hand-picked successful trace. Avoid committing raw private artifacts or licensed benchmark datasets. Link upstream work and implement original code rather than copying unlicensed harness implementations.

Roadmap priorities are representative public evaluations, stronger container isolation, calibrated task routing, and validated open-model adapters. Parallel specialists should demonstrate a benefit under equal quality/cost constraints before becoming defaults.

For a versioned distribution, follow [the release guide](docs/RELEASING.md). The tag, Python package version and CLI version must match. Public users can install the resulting wheel directly using [the setup guide](docs/INSTALLATION.md); no source checkout is needed.
