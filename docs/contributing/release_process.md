# Release process

_Black_'s release process has been standardized and automated. This document explains
what to expect and how to release _Black_ using said automation.

## Release cadence

**We aim to release whatever is on `main` every 1-2 months.** This ensures merged
improvements and bugfixes are shipped to users reasonably quickly, while not massively
fracturing the userbase with too many versions. This also keeps the workload on
maintainers consistent and predictable.

If there's not much new on `main` to justify a release, it's acceptable to skip a
month's release. Ideally January releases should not be skipped, since the first release
in a new calendar year may make changes to the _stable_ style, as per our
[stability policy](labels/stability-policy). While the policy applies to the first
release (instead of only January releases), confining changes to the stable style to
January will keep things predictable (and nicer) for users.

Unless there is a serious regression or bug that requires immediate patching, **there
should not be more than one release per month**. While version numbers are cheap,
releases require a maintainer to commit not only to the actual cutting of a release, but
also to deal with the potential fallout post-release. Releasing more frequently than
monthly nets rapidly diminishing returns.

## Cutting a release

**You must have `write` permissions for the _Black_ repository to cut a release.**

The 10,000-foot view of the release process is that you trigger a workflow to create a
PR automating the release chores. Then, merge it, triggering
[release automation](#release-workflows) that builds all release artifacts and publishes
them to the various platforms we publish to.

To cut a release:

1. **Run [the "prepare release" workflow][prepare-release-workflow].** Make sure to
   leave the main branch selected. This will create a PR automating most of the needed
   changes.
   - For stable versions, the workflow will automatically determine the next version
     number. Leave the `Prerelease_Version` input empty.
     - _Black_ follows the [CalVer] versioning standard using the `YY.M.N` format.
     - Unless there already has been a release during the month, `N` should be `0`.
     - Example: the first release in January 2026 is `26.1.0`.
   - If you're releasing a prerelease, specify the version in the box provided. Use the
     format `YY.MMaN`, where the date is when it is expected to become stable.
     - The first alpha should start `N` at `1` (not `0`).
     - Example: the first alpha released in December 2025 and to be stabilized in
       January 2026 is `26.1a1`.

2. **Check the changelog diff in the PR description and copyedit `CHANGES.md`.** The CI
   will update it after each push, so double-check it again before you merge. Things to
   check include:
   - Make sure nothing was put into the wrong version or section, particularly things
     that you might want to move to "Highlights"
   - Rephrase unclear or unnecessarily detailed entries (a sentence or two is probably
     plenty for most changes)
   - Remove duplicates, fix typos, and reorder entries if needed

3. **If you're releasing a prerelease or major version, commit the changes unique to
   it** to the PR branch. If you make any changes that should have a changelog entry,
   remember to add one!

   If you're releasing a major version (or a prerelease for one), there are some
   specific additional changes to make at this point:
   - Bump `wcwidth` to the latest version and run `scripts/make_width_table.py`
   - Find any references to the old version and bump them (references to minor versions
     are auto-bumped, so you don't need to check when releasing minor versions)

4. **Wait for CI to pass on the PR, and fix any failures.**
   - If CI does not pass, **stop** and investigate the failure(s) as we'd generally want
     to fix failing CI before cutting a release.

5. **To cut a stable release, merge the PR once everything looks good.** If you're
   cutting a prerelease, **do not merge it**, and instead [run the "cut release"
   workflow][cut-release-workflow] manually. **Make sure to select the
   `ci/prepare-release` branch.**

6. **Make sure CI passes.** At this point, you're basically done, but it's good practice
   to [watch and verify that all the release workflows pass][black-actions], though
   GitHub may notify you anyway if something fails.
   - If something fails, don't panic. Please go read the respective workflow's logs and
     configuration file to reverse-engineer your way to a solution.
   - Additionally, the CI will create a new changelog PR (only after stable releases).
     Once everything passes, merge it.

Congratulations! You've successfully cut a new release of _Black_. Go and stand up and
take a break, you deserve it.

```{important}
Once the release artifacts are published, you may see new issues being filed indicating
regressions. While regressions are not great, they don't automatically mean a hotfix
release is warranted. Unless the regressions are serious and impact many users, a hotfix
release is probably unnecessary. In the end, use your best judgment and ask other
maintainers for their thoughts.
```

## Release workflows

All of _Black_'s release automation uses [GitHub Actions]. All workflows are therefore
configured using YAML files in the `.github/workflows` directory of the _Black_
repository. They are triggered at various points in the release process detailed above.

### prepare release

This workflow is manually run as the first step in the release process. It handles many
of the initial chores before releasing.

#### prepare

This job runs `scripts/release.py` to clean up CHANGES.md and bump most references to
old _Black_ versions, then creates a PR with the changes for your review. It also
creates a draft release for the next job to upload the binaries to. The PR creation is
authenticated in order to trigger test CI.

```{note}
_Currently this workflow uses a GitHub API Token associated with @TODO's account._
```

#### build binaries (…)

This workflow builds native executables for multiple platforms using [PyInstaller]. This
allows people to download the executable for their platform and run _Black_ without a
[Python runtime][python-runtimes] installed.

The created binaries are stored on the associated GitHub Release for download. Note that
we use [GitHub's immutable releases][immutable-releases], preventing assets or tags from
being modified after the release as a security measure.

This is the only step in the "prepare release" workflow that runs a build. The other
build steps are routinely tested on PRs and pushes to `main`, so they don't need to be
included here.

### cut release

This workflow runs when the changelog PR is merged (or when manually triggered, in the
case of prereleases). It marks the release as published, triggering other workflows, and
also completes final post-release chores.

#### release

Updates the release with the cleaned changelog and publishes it. This is authenticated
in order to trigger the other release automation.

```{note}
_Currently this workflow uses a GitHub API Token associated with @TODO's account._
```

#### update-stable

Updates the `stable` branch by force pushing it to the most recent tag. This saves us
from remembering to update the branch sometime after cutting the release.

#### new-changelog

Opens a new PR to add the "Unreleased" section back to the changelog. The PR is
intentionally not auto-merged, in case there's an issue and the release needs to be
re-cut.

### build and publish

This is our main workflow, triggered when the release is published. It builds an [sdist]
and [wheels] to upload to PyPI where the vast majority of users will download _Black_
from.

It also runs as a test dry run on each PR and push to `main` (without publishing
anything to PyPI).

#### sdist + pure wheel

This single job builds the sdist and pure Python wheel (i.e., a wheel that only contains
Python code) using [Hatch]. These artifacts are general-purpose and can be used on
basically any platform supported by Python.

#### generate wheels matrix / mypyc wheels (…)

We use [mypyc] to compile _Black_ into a CPython C extension for significantly improved
performance. Wheels built with mypyc are platform and Python version specific.
[Supported platforms are documented in the FAQ](labels/mypyc-support).

These matrix jobs use [cibuildwheel] which handles the complicated task of building C
extensions for many environments for us. Since building these wheels is slow, there are
multiple mypyc wheels jobs (hence the term "matrix") that build for a specific platform
(as noted in the job name in parentheses).

#### publish-hatch / publish-mypyc

These jobs upload the built sdist and all wheels to PyPI using [Trusted
Publishing][trusted-publishing].

### docker

This workflow uses Docker Buildx to build and push `arm64` and `amd64`/`x86_64` builds
of the official _Black_ Docker image to Docker Hub.

This also runs on each push to `main`.

```{note}
_Currently this workflow uses a Docker API Token associated with @cooperlees's account._
```

[black-actions]: https://github.com/psf/black/actions
[calver]: https://calver.org
[cibuildwheel]: https://cibuildwheel.readthedocs.io/
[cut-release-workflow]: https://github.com/psf/black/actions/workflows/cut_release.yml
[github actions]: https://github.com/features/actions
[hatch]: https://hatch.pypa.io/latest/
[immutable-releases]:
  https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases
[mypyc]: https://mypyc.readthedocs.io/
[prepare-release-workflow]:
  https://github.com/psf/black/actions/workflows/prepare_release.yml
[pyinstaller]: https://www.pyinstaller.org/
[python-runtimes]: https://wiki.python.org/moin/pythonimplementations
[sdist]:
  https://packaging.python.org/en/latest/glossary/#term-source-distribution-or-sdist
[trusted-publishing]: https://docs.pypi.org/trusted-publishers/
[wheels]: https://packaging.python.org/en/latest/glossary/#term-wheel
