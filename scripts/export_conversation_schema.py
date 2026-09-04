"""Regenerate contracts/conversation_state.schema.json from DiagnosisPreview.

The diagnosis preview (a.k.a. conversation state) is the shape butter_mind sends
to devbutter_backend, which relays it verbatim to the browser -- see ADR-0005.
This file is the single reviewable snapshot of that contract: a diff here is the
signal that the wire shape changed. devbutter_backend no longer re-declares it.

Run after changing DiagnosisPreview (or anything it nests):

    poetry run python scripts/export_conversation_schema.py

test_conversation_state_contract.py fails if the committed file is stale.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.diagnosis.schemas import DiagnosisPreview

CONTRACT_PATH = Path(__file__).resolve().parent.parent / "contracts" / "conversation_state.schema.json"


def render() -> str:
    schema = DiagnosisPreview.model_json_schema()
    return json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> None:
    CONTRACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONTRACT_PATH.write_text(render(), encoding="utf-8")
    print(f"wrote {CONTRACT_PATH.relative_to(CONTRACT_PATH.parent.parent)}")


if __name__ == "__main__":
    main()
