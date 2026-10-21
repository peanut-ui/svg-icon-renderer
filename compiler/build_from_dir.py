import os
import sys
from os.path import join

import svg_compile

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))


def find_svgs(root: str) -> list[str]:
    paths: list[str] = []

    for dirpath, _, filenames in os.walk(root):
        for filename in filenames:
            if filename.lower().endswith(".svg"):
                paths.append(join(dirpath, filename))

    paths.sort()
    return paths


def compile_dir(root: str) -> tuple[dict[str, list[list[int]]], int]:
    compiled: dict[str, list[list[int]]] = {}
    failures = 0

    for path in find_svgs(root):
        name = os.path.splitext(os.path.basename(path))[0]

        if name in compiled:
            print(f"  SKIP  {name}: duplicate name ({path})")
            continue

        try:
            compiled[name] = svg_compile.compile_icon_file(path)
        except Exception as error:
            print(f"  FAIL  {name}: {error}")
            failures += 1

    return compiled, failures


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    root = sys.argv[1]
    if not os.path.isdir(root):
        print(f"Not a directory: {root}")
        return 1

    if len(sys.argv) > 2:
        dest = sys.argv[2]
    else:
        dest = svg_compile.default_out_path(SCRIPT_DIR)

    print(f"Compiling SVGs from {root}")
    compiled, failures = compile_dir(root)

    if not compiled:
        print("No icons compiled.")
        return 1

    svg_compile.write_luau(compiled, dest)

    size = os.path.getsize(dest)
    print(
        f"Compiled {len(compiled)} icons into {dest} "
        f"({size / 1024:.1f} KiB), {failures} failed."
    )
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    main()
