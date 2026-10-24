"""Create an RSA key pair for a Snowflake service user (run once per user).

    .venv/Scripts/python loader/make_keypair.py                  # ECOM_LOADER (Python loader)
    .venv/Scripts/python loader/make_keypair.py --name ecom_bi   # ECOM_BI_SVC (Fabric / Power BI)

The PRIVATE key is saved under ~/.snowflake/ (outside the repo, never committed).
The PUBLIC key is printed as a ready-to-run ALTER USER statement for Snowflake.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="ecom_loader", help="key file prefix (default: ecom_loader)")
    KEY_PATH = Path.home() / ".snowflake" / f"{ap.parse_args().name}_key.p8"

    if KEY_PATH.exists():
        print(f"Key already exists at {KEY_PATH}, so nothing was created. Delete it first to make a new one.")
        private_key = serialization.load_pem_private_key(KEY_PATH.read_bytes(), password=None)
    else:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
        KEY_PATH.write_bytes(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ))
        print(f"Private key saved to {KEY_PATH}")

    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    # Snowflake wants the key body only, without the BEGIN/END lines
    body = "".join(line for line in public_pem.splitlines() if "-----" not in line)
    print("\nPaste this line into the SQL script where it says <PUBLIC_KEY>:\n")
    print(body)


if __name__ == "__main__":
    main()
