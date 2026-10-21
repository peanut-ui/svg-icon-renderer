import json
import os
import threading
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from os.path import join

import svg_compile

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))

OUT_DIR = join(SCRIPT_DIR, "out")
TEMP_DIR = join(SCRIPT_DIR, "temp")

ICONS_DIR = join(TEMP_DIR, "icons")

ICON_NAMES_CACHE = join(ICONS_DIR, "names.json")

DEFAULT_DIR = join(ICONS_DIR, "default")
FILLED_DIR = join(ICONS_DIR, "filled")

os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(DEFAULT_DIR, exist_ok=True)
os.makedirs(FILLED_DIR, exist_ok=True)

REPO = "google/material-design-icons"
BRANCH = "master"
STYLE = "materialsymbolsrounded"
BASE_URL = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/symbols/web"
METADATA_URL = (
    "https://fonts.google.com/metadata/icons"
    "?key=material_symbols&incomplete=true"
)

THREADS = 32

WANTED = [
    # Navigation
    "home",
    "menu",
    "search",
    "settings",
    "close",
    "arrow_back",
    "arrow_forward",
    "chevron_left",
    "chevron_right",
    "expand_more",
    "expand_less",
    "more_vert",

    # Actions
    "add",
    "remove",
    "edit",
    "delete",
    "save",
    "check",
    "content_copy",
    "share",
    "download",
    "upload",
    "send",
    "filter_list",
    "sort",
    "refresh",

    # Status
    "info",
    "warning",
    "error",
    "help",
    "check_circle",
    "cancel",
    "notifications",
    "star",
    "favorite",
    "visibility",
    "visibility_off",
    "lock",

    # People
    "person",
    "group",
    "account_circle",
    "chat",
    "mail",
    "call",

    # Media
    "play_arrow",
    "pause",
    "volume_up",
    "volume_off",
    "image",
    "videocam",

    # Files
    "folder",
    "description",
    "cloud",
    "cloud_upload",
    "cloud_download",
    "code",

    # Misc
    "dashboard",
    "grid_view",
    "list",
    "calendar_today",
    "schedule",
    "lightbulb",
]

icons: list[str] = []

print_lock = threading.Lock()


def log(message: str) -> None:
    with print_lock:
        print(message)


def icon_url(name: str, filled: bool) -> str:
    suffix = "_fill1_24px.svg" if filled else "_24px.svg"
    return f"{BASE_URL}/{name}/{STYLE}/{name}{suffix}"


def download(name: str, filled: bool) -> bool:
    dest_dir = FILLED_DIR if filled else DEFAULT_DIR
    dest = join(dest_dir, f"{name}.svg")

    name_str = "filled" if filled else "default"
    if os.path.exists(dest):
        return True

    url = icon_url(name, filled)
    try:
        with urllib.request.urlopen(url) as response:
            data = response.read()
    except Exception as error:
        log(f"  FAIL  {name} ({name_str}): {error}")
        return False

    with open(dest, "wb") as file:
        file.write(data)

    return True


def download_all() -> int:
    jobs = [(name, filled) for name in icons for filled in (False, True)]
    total = len(jobs)
    failures = 0
    done = 0
    missing = 0

    print(
        f"Downloading {len(icons)} icons x2 variants "
        f"into {ICONS_DIR} ({THREADS} threads)"
    )

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        futures = {
            pool.submit(download, name, filled): (name, filled)
            for name, filled in jobs
        }

        for future in as_completed(futures):
            name, filled = futures[future]
            done += 1
            variant = "filled" if filled else "default"

            try:
                ok = future.result()
            except urllib.error.HTTPError as error:
                if error.code == 404:
                    missing += 1
                    return True
                log(f"  FAIL  {name} ({variant}): {error}")
                return False
            except Exception as error:
                ok = False
                log(f"  FAIL  {name} ({variant}): {error}")

            if not ok:
                failures += 1

            if done % 100 == 0 or done == total:
                log(f"  {done}/{total} done, {failures} failed")

    print(f"Done. {total - failures}/{total} downloaded, " +
          f"{missing} missing, {failures} failed.")
    return failures


def fetch_all_icon_names() -> list[str]:
    if os.path.isfile(ICON_NAMES_CACHE):
        try:
            with open(ICON_NAMES_CACHE) as f:
                return json.load(f)
        except Exception as e:
            print(f"Couldn't load cached icon names due to: {e}")

    print("Fetching icon metadata...")
    request = urllib.request.Request(
        METADATA_URL,
        headers={"User-Agent": "icon-fetcher"}
    )
    with urllib.request.urlopen(request) as response:
        raw = response.read().decode("utf-8")

    if raw.startswith(")]}'"):
        raw = raw[4:]

    data = json.loads(raw)

    family = "Material Symbols Rounded"
    names = sorted({
        icon["name"]
        for icon in data["icons"]
        if family not in icon.get("unsupported_families", [])
    })

    with open(ICON_NAMES_CACHE, "w") as f:
        json.dump(names, f)

    print(f"Fetched {len(names)} icon names.")
    return names


def compile_icons() -> int:
    compiled: dict[str, list[list[int]]] = {}
    failures = 0

    for name in icons:
        for filled in (False, True):
            source = join(FILLED_DIR if filled else DEFAULT_DIR, f"{name}.svg")
            if not os.path.isfile(source):
                continue

            key = f"{name}_filled" if filled else name
            try:
                compiled[key] = svg_compile.compile_icon_file(source)
            except Exception as error:
                log(f"  COMPILE FAIL  {key}: {error}")
                failures += 1

    dest = svg_compile.default_out_path(SCRIPT_DIR)
    svg_compile.write_luau(compiled, dest)

    size = os.path.getsize(dest)
    print(
        f"Compiled {len(compiled)} icons into {dest} "
        f"({size / 1024:.1f} KiB), {failures} failed."
    )
    return failures


if __name__ == "__main__":
    icons = WANTED
    print(f"Building {len(icons)} icons.")

    download_failures = download_all()
    print(f"Downloaded icons, failures: {download_failures}.")

    compile_failures = compile_icons()
    print(f"Compiled icons, failures: {compile_failures}.")
