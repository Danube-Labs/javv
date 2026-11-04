"""The users of the video stack: rotates the bootstrap admin, then adds `lead` with the security
lead role and `viewer` with the viewer role. The passwords come from the 600 files that start.sh
writes; nothing prints them."""

import os
import sys
from pathlib import Path

import httpx

SECRETS = Path(os.environ["SECRETS"])
BASE = f"http://127.0.0.1:{os.environ['BACKEND_PORT']}"


def login(client: httpx.Client, user: str, password: str) -> dict:
    r = client.post("/auth/login", json={"username": user, "password": password})
    r.raise_for_status()
    client.cookies.set("javv_session", r.cookies["javv_session"])
    return r.json()["user"]


def rotate(client: httpx.Client, current: str, new: str) -> None:
    r = client.post(
        "/auth/password", json={"current_password": current, "new_password": new}
    )
    r.raise_for_status()
    client.cookies.set("javv_session", r.cookies["javv_session"])


def main() -> int:
    boot = (SECRETS / "admin_boot_pass").read_text()
    admin = (SECRETS / "admin_pass").read_text()
    users = {"lead": "security_lead", "viewer": "viewer"}
    # a temporary password the next sign-in must change, as for any new user
    temp = "Temp-" + boot[:20]
    with httpx.Client(base_url=BASE) as client:
        if login(client, "admin", boot).get("must_change"):
            rotate(client, boot, admin)
        for user, role in users.items():
            r = client.post(
                "/api/v1/admin/users",
                json={"username": user, "temp_password": temp, "role": role},
            )
            r.raise_for_status()
    for user in users:
        with httpx.Client(base_url=BASE) as client:
            login(client, user, temp)
            rotate(client, temp, (SECRETS / f"{user}_pass").read_text())
    print("users ready: admin, " + ", ".join(users))
    return 0


if __name__ == "__main__":
    sys.exit(main())
