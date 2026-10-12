"""Install a user-downloaded key using the already-authorized private GitHub App."""
import argparse
import os
from pathlib import Path

from scripts.renew_instagram_credential import installation_token, save_secret


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--key-file", required=True)
    args = parser.parse_args()
    try:
        key = Path(args.key_file).read_text()
        if "PRIVATE KEY-----" not in key or len(key) > 16384:
            raise RuntimeError("Invalid private key")
        os.environ["FUNZUG_GH_APP_ID"] = "5281589"
        os.environ["FUNZUG_GH_APP_PRIVATE_KEY"] = key
        auth = installation_token()
        save_secret("FUNZUG_GH_APP_ID", "5281589", auth)
        save_secret("FUNZUG_GH_APP_PRIVATE_KEY", key, auth)
        print("Funzug GitHub App credentials installed in the encrypted publishing environment")
        return 0
    except Exception:
        print("GitHub App credential installation failed; private details omitted")
        return 1
    finally:
        os.environ.pop("FUNZUG_GH_APP_PRIVATE_KEY", None)


if __name__ == "__main__":
    raise SystemExit(main())
