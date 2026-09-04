"""Guards the committed wire-contract snapshot for the diagnosis preview.

`DiagnosisPreview` is the shape butter_mind sends downstream; devbutter_backend
relays it verbatim and no longer re-declares it (ADR-0005). If this test fails,
the contract changed -- regenerate and commit the snapshot:

    poetry run python scripts/export_conversation_schema.py
"""

from scripts.export_conversation_schema import CONTRACT_PATH, render


def test_committed_conversation_state_schema_is_current() -> None:
    committed = CONTRACT_PATH.read_text(encoding="utf-8")
    assert committed == render(), (
        "contracts/conversation_state.schema.json is stale -- run "
        "`poetry run python scripts/export_conversation_schema.py` and commit."
    )
