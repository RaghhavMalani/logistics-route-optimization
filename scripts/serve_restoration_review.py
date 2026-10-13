"""Local restoration review with verified accounts and an isolated state root.

Reads the existing exported public-data cache. Does not seed/replace forecasts,
alter evidence, run collectors, or provision accounts in the operational store.
"""
from pathlib import Path
import os
import tempfile


def main():
    root = Path(__file__).resolve().parents[1]
    review = root / "work" / "restoration-e906f6a"
    review.mkdir(parents=True, exist_ok=True)
    state = Path(tempfile.mkdtemp(prefix="review-state-", dir=review))
    os.environ["PORTWATCH_STATE_DIR"] = str(state)
    os.environ["PORTWATCH_AUTH_DB"] = str(state / "identity.sqlite3")
    os.environ["PORTWATCH_IDENTITY_MODE"] = "verified"
    os.environ["PORTWATCH_LICENCE_MODE"] = "DEMO"
    os.environ["PORTWATCH_FRESHNESS_SCHEDULER"] = "0"
    os.environ.pop("AISSTREAM_API_KEY", None)
    os.environ.pop("PORTWATCH_FLEET_PROVIDER", None)
    from backend.app.auth_store import AuthStore
    from src.portwatch_os.fleet.company import DEMO_COMPANY_ID
    import uvicorn

    accounts = AuthStore(state / "identity.sqlite3")
    password = "restore-local-review"
    for name, role, ports, vessels in (
        ("admin", "NATIONAL_ADMIN", (), ()),
        ("company", "SHIPPING_COMPANY", (), ()),
        ("vessel", "VESSEL_OPERATOR", (), ("PWD-001",)),
        ("port", "PORT_AUTHORITY", ("INMAA",), ()),
    ):
        accounts.provision(
            f"{name}@restore.local", password, role=role,
            display_name=f"Restoration review · {name}", ports=ports,
            organisation=DEMO_COMPANY_ID if name in ("company", "vessel") else "",
            vessel_ids=vessels,
        )
    (review / "active-state.txt").write_text(str(state), encoding="utf-8")
    print(f"Local review state: {state}; existing exported sources retain their original timestamps", flush=True)
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=9297)


if __name__ == "__main__":
    main()
