#!/usr/bin/env python3

"""
Tool to help automate changes needed in commits during and after releases
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from subprocess import run

LOG = logging.getLogger(__name__)
NEW_VERSION_CHANGELOG_TEMPLATE = """\
## Unreleased

<!-- PR authors:
     Please include the PR number in the changelog entry, not the issue number -->

### Highlights

<!-- Include any especially major or disruptive changes here -->

### Stable style

<!-- Changes that affect Black's stable style -->

### Preview style

<!-- Changes that affect Black's preview style -->

### Configuration

<!-- Changes to how Black can be configured -->

### Packaging

<!-- Changes to how Black is packaged, such as dependency requirements -->

### Parser

<!-- Changes to the parser or to version autodetection -->

### Performance

<!-- Changes that improve Black's performance. -->

### Output

<!-- Changes to Black's terminal output and error messages -->

### _Blackd_

<!-- Changes to Blackd -->

### Integrations

<!-- For example, Docker, GitHub Actions, pre-commit, editors -->

### Documentation

<!-- Major changes to documentation and policies. Small docs changes
     don't need a changelog entry. -->
"""


class NoGitTagsError(Exception): ...


def get_git_tags() -> list[str]:
    """List all stable version tags"""
    cp = run(["git", "tag"], capture_output=True, check=True, encoding="utf8")
    if not cp.stdout:
        LOG.error(f"Returned no git tags; stderr: {cp.stderr}")
        raise NoGitTagsError
    git_tags = cp.stdout.splitlines()
    return [t for t in git_tags if t[0].isdigit() and len(t.split(".")) == 3]


def tuple_calver(calver: str) -> tuple[int, ...]:  # mypy can't notice maxsplit below
    """Convert a calver string into a tuple of ints for sorting"""
    return tuple(map(int, calver.split(".", maxsplit=2)))


class SourceFiles:
    def __init__(self, black_repo_dir: Path, next_version: str | None):
        # Use pathlib for all file path fun to be platform agnostic
        self.black_repo_path = black_repo_dir
        self.changes_path = self.black_repo_path / "CHANGES.md"
        self.docs_path = self.black_repo_path / "docs"
        self.version_doc_paths = (
            self.docs_path / "integrations" / "source_version_control.md",
            self.docs_path / "usage_and_configuration" / "the_basics.md",
            self.docs_path / "guides" / "using_black_with_jupyter_notebooks.md",
        )

        self.force_next_version = next_version

        LOG.debug(self)

    def __str__(self) -> str:
        return f"""\
> SourceFiles ENV:
  Repo path: {self.black_repo_path}
  CHANGES.md path: {self.changes_path}
  Docs path: {self.docs_path}
  Current version: {self.get_current_version()}
  Next version: {self.get_next_version()}
  Is prerelease: {bool(self.force_next_version)}
"""

    def get_current_version(self) -> str | None:
        """Get the latest git (version) tag as latest version"""
        versions = sorted(get_git_tags(), key=lambda k: tuple_calver(k))
        if versions:
            return versions[-1]
        return None

    def get_next_version(self) -> str:
        """Determine the year and month + version number to bump to"""
        if self.force_next_version:
            return self.force_next_version

        base_calver = datetime.today().strftime("%y.%m")
        calver_parts = base_calver.split(".")
        base_calver = f"{calver_parts[0]}.{int(calver_parts[1])}"  # Remove leading 0

        current_version = self.get_current_version()
        if not current_version or not current_version.startswith(base_calver):
            return f"{base_calver}.0"

        same_month_version = current_version.split(".", 2)[-1]
        return f"{base_calver}.{int(same_month_version) + 1}"

    def add_template_to_changes(self) -> int:
        """Add the template to CHANGES.md if it does not exist"""
        LOG.info(f"Adding template to {self.changes_path}")

        with self.changes_path.open("r", encoding="utf-8") as cfp:
            changes_string = cfp.read()

        if "## Unreleased" in changes_string:
            LOG.error(f"{self.changes_path} already has unreleased template")
            return 1

        templated_changes_string = changes_string.replace(
            "# Change Log\n",
            f"# Change Log\n\n{NEW_VERSION_CHANGELOG_TEMPLATE}",
        )

        with self.changes_path.open("w", encoding="utf-8") as cfp:
            cfp.write(templated_changes_string)

        LOG.info(f"Added template to {self.changes_path}")
        return 0

    def update_repo_for_release(self) -> int:
        """Update CHANGES.md + doc files ready for release"""
        self.cleanup_changes_template_for_release()
        if not bool(self.force_next_version):
            self.update_version_in_docs()
        return 0  # return 0 if no exceptions hit

    def cleanup_changes_template_for_release(self) -> None:
        LOG.info(f"Cleaning up {self.changes_path}")

        with self.changes_path.open("r", encoding="utf-8") as cfp:
            changes_string = cfp.read()

        next_version = self.get_next_version()
        if next_version:
            # Change Unreleased to next version
            changes_string = changes_string.replace(
                "## Unreleased", f"## Version {next_version}"
            )

        # Remove all comments
        changes_string = re.sub(r"(?m)^<!--(?>(?:.|\n)*?-->)\n+", "", changes_string)

        # Remove empty subheadings
        changes_string = re.sub(r"(?m)^###.+\n+(?=#)", "", changes_string)

        with self.changes_path.open("w", encoding="utf-8") as cfp:
            cfp.write(changes_string)

        LOG.debug(f"Finished cleaning up {self.changes_path}")

    def update_version_in_docs(self) -> None:
        current_version = self.get_current_version()
        if not current_version:
            return
        next_version = self.get_next_version()

        for doc_path in self.version_doc_paths:
            LOG.info(f"Updating Black version to {next_version} in {doc_path}")

            with doc_path.open("r", encoding="utf-8") as dfp:
                doc_string = dfp.read()

            next_version_doc = doc_string.replace(current_version, next_version)

            with doc_path.open("w", encoding="utf-8") as dfp:
                dfp.write(next_version_doc)

            LOG.debug(
                f"Finished updating Black version to {next_version} in {doc_path}"
            )

    def get_changelog(self) -> str:
        with self.changes_path.open("r", encoding="utf-8") as cfp:
            changes_string = cfp.read()

        current_version = self.get_current_version()
        if not current_version:
            before_current = changes_string
        else:
            before_current = changes_string.split(f"## Version {current_version}")[0]

        next_version = self.get_next_version()
        return before_current.split(f"## Version {next_version}")[1].strip()


def _handle_debug(debug: bool) -> None:
    """Turn on debugging if asked, otherwise default to INFO"""
    log_level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        format="[%(asctime)s] %(levelname)s: %(message)s (%(filename)s:%(lineno)d)",
        level=log_level,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-a",
        "--add-changes-template",
        action="store_true",
        help="Add the Unreleased template to CHANGES.md",
    )
    parser.add_argument(
        "-v",
        "--version",
        help="Overrides the next version (for prereleases)",
    )
    parser.add_argument(
        "-V",
        "--get-version",
        action="store_true",
        help="Echoes the next version number and disables all other logging",
    )
    parser.add_argument(
        "-C",
        "--get-changelog",
        action="store_true",
        help="Echoes the version's changelog and disables all other logging",
    )
    parser.add_argument(
        "-d", "--debug", action="store_true", help="Verbose debug output"
    )
    args = parser.parse_args()
    _handle_debug(args.debug)
    return args


def main() -> int:
    args = parse_args()
    if (args.get_version or args.get_changelog) and not args.debug:
        logging.disable()

    # Need parent.parent cause script is in scripts/ directory
    sf = SourceFiles(Path(__file__).parent.parent, args.version)

    if args.add_changes_template:
        return sf.add_template_to_changes()

    next_version = sf.get_next_version()
    LOG.info(f"Current version detected to be {sf.get_current_version()}")
    LOG.info(f"Next version will be {next_version}")

    exit_code = sf.update_repo_for_release()
    if exit_code != 0:
        return exit_code

    if args.get_version:
        print(next_version)
    if args.get_changelog:
        print(sf.get_changelog())

    return exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
