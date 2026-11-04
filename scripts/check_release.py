"""Reject release tags that do not describe the package being built."""

import argparse
import ast
import re
import tomllib
from pathlib import Path


def check_release(root, tag):
    root = Path(root)
    if not re.fullmatch(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", tag):
        raise ValueError("Release tags must be stable versions such as v0.4.0; prereleases need a separate publishing policy")
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    tree = ast.parse((root / "codex_harness" / "__init__.py").read_text())
    versions = [ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets)]
    if versions != [project["version"]] or tag != "v" + project["version"]:
        raise ValueError("Tag, pyproject.toml version and codex_harness.__version__ must match exactly")
    return project["version"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        print(check_release(args.root, args.tag))
    except (OSError, KeyError, ValueError, SyntaxError) as error:
        parser.exit(2, f"Release validation failed: {error}\n")


if __name__ == "__main__":
    main()
