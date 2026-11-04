#!/usr/bin/env python3
"""
fix_pr1_issues.py — automated fixes for PR #1 issues in
XDiaoXuanX/Black-Android-M.

Idempotent: safe to run multiple times.

Usage (from repo root):
    python3 scripts/fix_pr1_issues.py              # apply
    python3 scripts/fix_pr1_issues.py --dry-run    # preview only
    python3 scripts/fix_pr1_issues.py --verify     # exit 1 if fixes needed

The script targets these specific issues reported for PR #1:

  1. native/game_files.cpp :: RemovableFolders
        - duplicate `out` / `ec` declarations
        - duplicate `if (name == "emulated" ...)` guard
  2. native/dynamic_resolution.cpp
        - std::chrono::duration(el).count() — invalid, needs duration_cast
  3. native/update.cpp :: CheckForUpdates
        - function defined twice (redefinition error)
  4. native/update.cpp :: WithActivity
        - `jmethodID m` declared twice in same scope
  5. native/game_files.cpp :: AskOtherRelease
        - duplicate SDL_MessageBoxData `box` declaration
  6. native/game_files.cpp :: ActivityCardFolders
        - DeleteLocalRef(activity) called on non-owned reference
  7. native/input.cpp :: OnEvent
        - duplicated gyro/touch guard
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHANGES: list[str] = []
DRY_RUN = False
VERIFY = False


# ----------------------------------------------------------------------------- helpers

def read(path: str) -> str | None:
    p = ROOT / path
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8", errors="replace")


def write(path: str, new_content: str, label: str) -> bool:
    p = ROOT / path
    old = p.read_text(encoding="utf-8", errors="replace")
    if old == new_content:
        return False
    if DRY_RUN:
        CHANGES.append(f"  [dry-run] {path} — {label}")
        return True
    p.write_text(new_content, encoding="utf-8")
    CHANGES.append(f"  \u2713 {path} — {label}")
    return True


def skip(path: str, reason: str) -> None:
    CHANGES.append(f"  \u00b7 {path} — skipped ({reason})")


# ----------------------------------------------------------------------------- fixes

def fix_removable_folders() -> None:
    path = "native/game_files.cpp"
    src = read(path)
    if src is None:
        return skip(path, "file not found")

    new = src

    # 1a) collapse duplicate `out` / `ec` declaration block
    new = re.sub(
        r"std::vector<std::string> out;[^\S\r\n]*\r?\n"
        r"[^\S\r\n]*std::error_code ec;[^\S\r\n]*\r?\n"
        r"([^\S\r\n]*)std::vector<std::string> out = ActivityCardFolders\(\);[^\S\r\n]*\r?\n"
        r"[^\S\r\n]*std::error_code ec, dir_ec;",
        r"\1std::vector<std::string> out = ActivityCardFolders();\n"
        r"\1std::error_code ec;",
        new,
    )

    # 1b) drop the duplicated `if (...)` guard (uses `dir_ec`)
    new = re.sub(
        r"([^\S\r\n]*)if \(name == \"emulated\" \|\| name == \"self\" "
        r"\|\| !e\.is_directory\(ec\)\) continue;[^\S\r\n]*\r?\n"
        r"[^\S\r\n]*if \(name == \"emulated\" \|\| name == \"self\" "
        r"\|\| !e\.is_directory\(dir_ec\)\) continue;",
        r"\1if (name == \"emulated\" || name == \"self\" "
        r"|| !e.is_directory(ec)) continue;",
        new,
    )

    if not write(path, new, "RemovableFolders: dedupe decls + duplicate guard"):
        skip(path, "RemovableFolders — already clean")


def fix_chrono_duration() -> None:
    path = "native/dynamic_resolution.cpp"
    src = read(path)
    if src is None:
        return skip(path, "file not found")

    new = re.sub(
        r"std::chrono::duration\(el\)\.count\(\)",
        "std::chrono::duration_cast<std::chrono::duration<float>>(el).count()",
        src,
    )
    if not write(path, new, "chrono: duration_cast<duration<float>>"):
        skip(path, "chrono — already clean")


def fix_update_cpp() -> None:
    path = "native/update.cpp"
    src = read(path)
    if src is None:
        return skip(path, "file not found")

    new = src

    # 4) remove the extra `jmethodID m` that uses "()V" sig
    new = re.sub(
        r"[^\S\r\n]*jmethodID m = env->GetMethodID\(cls, name, \"\(\)V\"\);[^\S\r\n]*\r?\n"
        r"[^\S\r\n]*if \(m\) env->CallVoidMethod\(activity, m\);[^\S\r\n]*\r?\n"
        r"([^\S\r\n]*)jmethodID m = env->GetMethodID\(cls, name, sig\);",
        r"\1jmethodID m = env->GetMethodID(cls, name, sig);",
        new,
    )

    # 3) remove the simpler duplicate `CheckForUpdates` definition
    new = re.sub(
        r"void CheckForUpdates\(\)[^\S\r\n]*\{[^\S\r\n]*\r?\n"
        r"[^\S\r\n]*CallActivity\(\"checkForUpdates\"\);[^\S\r\n]*\r?\n"
        r"[^\S\r\n]*\}[^\S\r\n]*\r?\n"
        r"(\s*\r?\n)?",
        "",
        new,
    )

    if not write(path, new, "update.cpp: dedupe jmethodID m + CheckForUpdates"):
        skip(path, "update.cpp — already clean")


def fix_ask_other_release() -> None:
    path = "native/game_files.cpp"
    src = read(path)
    if src is None:
        return skip(path, "file not found")

    # 5) drop the earlier `box` declared with `2, buttons`
    new = re.sub(
        r"SDL_MessageBoxData box\{SDL_MESSAGEBOX_WARNING, nullptr, "
        r"title\.c_str\(\),[^\S\r\n]*\r?\n"
        r"[^\S\r\n]*text\.c_str\(\), 2, buttons, nullptr\};[^\S\r\n]*\r?\n",
        "",
        src,
    )
    if not write(path, new, "AskOtherRelease: remove duplicate SDL_MessageBoxData"):
        skip(path, "AskOtherRelease — already clean")


def fix_activity_card_folders() -> None:
    path = "native/game_files.cpp"
    src = read(path)
    if src is None:
        return skip(path, "file not found")

    # 6) remove the invalid DeleteLocalRef(activity)
    new = re.sub(
        r"\n[^\S\r\n]*env->DeleteLocalRef\(activity\);[^\n]*\n",
        "\n",
        src,
    )
    if not write(path, new, "ActivityCardFolders: remove DeleteLocalRef(activity)"):
        skip(path, "ActivityCardFolders — already clean")


def fix_input_sensor() -> None:
    path = "native/input.cpp"
    src = read(path)
    if src is None:
        return skip(path, "file not found")

    # 7) collapse duplicate gyro/touch guard
    new = re.sub(
        r"if \(e\.gsensor\.sensor != SDL_SENSOR_GYRO\) return;[^\S\r\n]*\r?\n"
        r"[^\S\r\n]*if \(((?:\w+::)?)TouchActive\(\)\) return;[^\S\r\n]*\r?\n"
        r"[^\S\r\n]*if \(e\.gsensor\.sensor != SDL_SENSOR_GYRO\) return;",
        r"if (e.gsensor.sensor != SDL_SENSOR_GYRO || \1TouchActive()) return;",
        src,
    )
    if not write(path, new, "input.cpp: collapse duplicated gyro guard"):
        skip(path, "input.cpp — already clean")


# ----------------------------------------------------------------------------- main

def main() -> int:
    global DRY_RUN, VERIFY

    parser = argparse.ArgumentParser(description="Fix PR #1 issues")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview only; do not modify files")
    parser.add_argument("--verify",  action="store_true",
                        help="Exit non-zero if any fix would be applied")
    args = parser.parse_args()

    VERIFY = args.verify
    DRY_RUN = args.dry_run or VERIFY

    print(f"Black-Android-M :: fix_pr1_issues.py")
    print(f"  repo root  : {ROOT}")
    print(f"  dry-run    : {DRY_RUN}")
    print(f"  verify     : {VERIFY}")
    print()

    fix_removable_folders()
    fix_chrono_duration()
    fix_update_cpp()
    fix_ask_other_release()
    fix_activity_card_folders()
    fix_input_sensor()

    if CHANGES:
        print("Results:")
        print("\n".join(CHANGES))
    else:
        print("Nothing to do — all patterns already clean or not present.")

    if VERIFY and CHANGES:
        print("\n[verify] repository still needs fixes \u2192 exit 1")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
