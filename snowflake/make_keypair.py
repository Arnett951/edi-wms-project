"""Generates the RSA key pair the Snowflake copy script authenticates with.

    python snowflake/make_keypair.py

Writes ~/.snowflake/wmslab_rsa_key.p8 (private, PKCS#8, unencrypted; lab only)
and prints the ALTER USER statement to run in Snowsight with the public key.
Refuses to overwrite an existing key, since that would lock out the script
until the new public key is registered.
"""
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

KEY_PATH = Path(os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH", Path.home() / ".snowflake" / "wmslab_rsa_key.p8"))
USER = os.environ.get("SNOWFLAKE_USER", "CARNETT909")


def main():
    if KEY_PATH.exists():
        sys.exit(f"{KEY_PATH} already exists; delete it first if you really want a new key.")
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    KEY_PATH.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    pub = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    body = "".join(line for line in pub.splitlines() if "-----" not in line)

    print(f"Private key written to {KEY_PATH}\n")
    print("Run this in a Snowsight worksheet (as ACCOUNTADMIN):\n")
    print(f"ALTER USER {USER} SET RSA_PUBLIC_KEY = '{body}';")


if __name__ == "__main__":
    main()
