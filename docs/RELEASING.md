# Publish an installable version

The repository already defines the `sc`, `supercodex`, `super-codex` and `ch` console commands and builds a platform-independent Python wheel. A public GitHub Release makes that wheel installable by URL without a user cloning the repository. Python 3.11+, Git and an installed/authenticated Codex CLI are still prerequisites for using the harness.

The public repository is [AryamanCoupa/super-codex](https://github.com/AryamanCoupa/super-codex). PyPI publishing is not enabled. A normal source push does not publish a package; the version tag triggers the release workflow.

## First public release

1. Push the code, including `.github/workflows/release.yml`, to this repository. For a fork, set `origin` to your fork URL; if `origin` already exists, use `git remote set-url origin URL` instead of adding it again.
2. When publishing a fork, update the repository URLs in the README, installation guide and `pyproject.toml`. Keep the Python distribution name `super-codex-harness` unless you deliberately rename it and update asset examples.
3. Confirm GitHub Actions is enabled and repository policy permits the release job's `contents: write` permission. The workflow uses GitHub's generated token; no personal access token or PyPI credential is required for GitHub Releases.
4. Ensure `pyproject.toml` and `codex_harness/__init__.py` contain the same version. They currently specify `0.5.4`. Commit the changes, then publish that exact version tag:

```bash
git push origin main
git tag -a v0.5.4 -m "SuperCodex 0.5.4"
git push origin v0.5.4
```

Pushing a `v*` tag triggers the release workflow. Only stable `vMAJOR.MINOR.PATCH` tags are accepted; the tag must match both version declarations. The workflow runs the offline tests with the optional GEPA contract installed, builds wheel/source distributions, checks package metadata, installs the wheel into a fresh environment outside the checkout, exercises launch previews and the offline demo, and then publishes the release.

The build job has read-only repository access. Only the separate publish job receives content-write permission. Tag values are passed through environment variables, and `gh release create --verify-tag` requires the pushed tag to exist. Existing releases are not overwritten by this workflow; fix a failed pre-publication build and rerun it, or publish a new version rather than moving a released tag.

The release contains:

```text
super_codex_harness-0.5.4-py3-none-any.whl
super_codex_harness-0.5.4.tar.gz
SHA256SUMS
```

After the workflow succeeds, the user-facing installation is:

```bash
pipx install "https://github.com/AryamanCoupa/super-codex/releases/download/v0.5.4/super_codex_harness-0.5.4-py3-none-any.whl"
pipx ensurepath
```

Reopen the terminal and use `sc` from a project. The versioned wheel URL remains explicit; users do not need a source checkout. The tag archive provides a no-manual-clone fallback if a release asset is temporarily unavailable. Both methods are explained in [INSTALLATION.md](INSTALLATION.md).

## Local release check

Use a Python 3.11+ environment. The following builds packages locally and does not publish them:

```bash
python -m pip install build twine '.[gepa]'
python scripts/check_release.py --tag v0.5.4
python -m unittest discover -s tests -v
python -m build
python -m twine check --strict dist/*.whl dist/*.tar.gz
```

Use a fresh `dist` directory for a release so it cannot include old version artifacts. Download all three assets after publication to verify the release. On macOS use `shasum -a 256 -c SHA256SUMS`; on Linux use `sha256sum -c SHA256SUMS`. Checksums detect changes relative to that checksum file; they are not independent signatures.

Check the [Release workflow](https://github.com/AryamanCoupa/super-codex/actions/workflows/release.yml) after pushing a tag. Do not announce a new version's download URL as available before that run succeeds.

## Later versions and optional PyPI distribution

For a new release, update both version declarations, update the pinned installation examples, commit, and push a new matching tag. Do not reuse or move published tags. This workflow intentionally does not publish prereleases as stable releases; add explicit prerelease handling before using `rc`/`beta` versions.

GitHub Releases are sufficient for no-clone installation. If you later own the corresponding project name on PyPI, publish the same checked wheel/source distributions there, preferably with [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/). That requires configuring the correct repository/workflow/environment on PyPI; it is not enabled here. Only after a successful PyPI publication should the public guide advertise `pipx install super-codex-harness` as an available registry installation.

The workflow follows the primary [Python packaging guide](https://packaging.python.org/en/latest/tutorials/packaging-projects/), [GitHub release CLI documentation](https://cli.github.com/manual/gh_release_create), and [GitHub token guidance](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token), reviewed with Playwright MCP.
