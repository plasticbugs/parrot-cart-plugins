"""record_fixture -- run the validator against the real GitHub (read-only)
and save every response as a test scenario.

    python3 tools/record_fixture.py OWNER/REPO [--tag TAG] OUT_DIR

tools/validate.py --fixtures OUT_DIR replays it. Downloaded .CVP files and
screenshots are saved too (NN.bin), so don't commit a recording of a plugin
whose files you can't share: the tests' own scenarios are synthetic
(tests/scenarios.py). Needs the network;
GITHUB_TOKEN is used if set (and never written to the scenario).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ghapi  # noqa: E402
import validate  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("out")
    ap.add_argument("--tag", default=None)
    a = ap.parse_args()
    gh = ghapi.GitHub(transport=ghapi.RecordingTransport(a.out))
    res = validate.validate(gh, a.repo, a.tag, "recorded")
    print(validate.report(res))
    print(f"saved {len(gh.t.index)} responses in {a.out}")


if __name__ == "__main__":
    main()
