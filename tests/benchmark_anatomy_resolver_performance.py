"""Repeatable pure-Python benchmark for large-rig anatomy detection."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests import test_creature_anatomy_profiles as fixture


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--bones", type=int, default=1_000)
    parser.add_argument("--samples", type=int, default=7)
    return parser.parse_args()


def main():
    args = arguments()
    bones = list(fixture.synthetic_quadruped().bones)
    for index in range(max(0, args.bones - len(bones))):
        bones.append(fixture.Bone(
            name=f"custom_helper_bone_{index:04d}",
            parent="",
            head=(0.0, 0.0, 0.0),
            tail=(0.0, 0.0, 1.0),
            length=1.0,
        ))
    snapshot = fixture.Snapshot.from_bones(
        bones,
        armature_name="DAF_Large_Rig_Benchmark",
    )

    def detect():
        return fixture.detection.detect_profile(snapshot)

    detect()
    durations = []
    result = None
    for _index in range(args.samples):
        started = time.perf_counter()
        result = detect()
        durations.append((time.perf_counter() - started) * 1000.0)
    report = {
        "fixture": {"bones": len(snapshot.bones)},
        "detection": {
            "durationsMs": [round(value, 6) for value in durations],
            "medianMs": round(statistics.median(durations), 6),
            "minimumMs": round(min(durations), 6),
            "maximumMs": round(max(durations), 6),
            "profileId": result.get("profileId"),
            "mappingDigest": result.get("mappingDigest"),
        },
    }
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("DAF_ANATOMY_RESOLVER_PERFORMANCE=" + json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
