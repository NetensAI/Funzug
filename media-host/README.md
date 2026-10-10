# Funzug media host

This small Docker service accepts authenticated image uploads and serves only immutable, randomly named public image files. Uploads use a bearer token stored as a Docker secret. Public image GETs require no token so Meta can fetch them. It does not accept arbitrary paths, overwrite files, or provide deletion through HTTP.

## Requirements

- A home server that runs Docker Compose and remains online.
- A DNS name pointing to the server, with inbound TCP ports 80 and 443 available. Caddy obtains and renews HTTPS certificates automatically.
- A router/firewall forwarding 80 and 443 to the server. If the ISP uses CGNAT, configure a trusted outbound tunnel with HTTPS instead of exposing ports directly.
- A long random upload token, kept only on the server and in GitHub Actions secrets. Never commit it.

## First-time setup on the server

Copy this `media-host` directory to a dedicated server folder. From that folder:

```sh
mkdir -p secrets
umask 077
openssl rand -hex 32 > secrets/upload_token
chmod 600 secrets/upload_token
```

Create `.env` with only the DNS name, for example `FUNZUG_MEDIA_DOMAIN=media.example.com`. Set GitHub Actions secrets `FUNZUG_MEDIA_BASE_URL` to `https://media.example.com` and `FUNZUG_MEDIA_UPLOAD_TOKEN` to the exact random token file value. Do not add the token to `.env`, compose environment, source control, terminal command arguments, or chat.

Then start the service:

```sh
docker compose up -d --build
docker compose ps
docker compose logs --tail=50 caddy media
```

Check `https://media.example.com/health` returns `ok`. Keep the named volumes `media_data`, `caddy_data`, and `caddy_config`; back up the media and Caddy data volumes. There is no HTTP delete route. To remove a public image, use controlled server-side administration after confirming the exact filename.

## Uploading a reviewed draft image

An upload makes that image public. Only run this after reviewing the image and deciding it is okay to publish publicly. The command below is deliberately explicit and prints a public URL; it does not approve or publish a social post.

```sh
python scripts/upload_media.py drafts/assets/IMAGE.png --confirm-public-upload FUNZUG
```

Set `FUNZUG_MEDIA_BASE_URL` and `FUNZUG_MEDIA_UPLOAD_TOKEN` in the local environment or CI secret store. Use the returned URL with `stage-draft`; staging leaves the item unapproved. A separate human approval is still required before Meta publishing.

The service limits uploads to 12 MiB and PNG, JPEG, or WebP with matching file signatures. It runs as a non-root user with a read-only container filesystem, dropped Linux capabilities, a read-only public surface, and no upload credential in logs or image URLs.
