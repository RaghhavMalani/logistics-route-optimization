"""Run on the API host: python -m scripts.provision_identity --help."""
import argparse
from getpass import getpass

from backend.app.auth_store import get_auth_store
from src.portwatch_os.roles import WORKSPACE_ROLES


def main():
    parser = argparse.ArgumentParser(description="Provision or update a verified operator; updating revokes all their sessions")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--role", required=True, choices=WORKSPACE_ROLES)
    parser.add_argument("--port", action="append", default=[], help="Registered port code; repeat for memberships")
    parser.add_argument("--organisation", default="")
    parser.add_argument("--vessel", action="append", default=[])
    args = parser.parse_args()
    password = getpass("New password (12–256 characters): ")
    if password != getpass("Confirm password: "):
        parser.error("passwords differ")
    try:
        profile = get_auth_store().provision(args.email, password, role=args.role, display_name=args.name,
                                            ports=tuple(args.port), organisation=args.organisation, vessel_ids=tuple(args.vessel))
    except ValueError as exc:
        parser.error(str(exc))
    print(f"Provisioned {profile['email']} as {profile['role']}; ports: {', '.join(profile['portCodes']) or 'none'}")


if __name__ == "__main__":
    main()
