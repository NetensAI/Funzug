# Funzug media host

This small Docker service accepts authenticated image uploads, validates the exact 1080x1350 canvas, converts PNG or JPEG input to JPEG, and serves only immutable, randomly named public image files. JPEG output is required by Instagram's content publishing API. Uploads use a bearer token stored as a Docker secret. Public image GETs require no token so Meta can fetch them. It does not accept arbitrary paths, overwrite files, or provide deletion through HTTP.

## Requirements

- A home server that runs Docker Compose and remains online.
- Either a Cloudflare Tunnel with a published hostname, or a DNS name pointing to the server with inbound TCP ports 80 and 443 available.
- A long random upload token, kept only on the server and in GitHub Actions secrets. Never commit it.
- For Cloudflare Tunnel, a tunnel token kept only on the server.

## First-time setup on the server

Copy this `media-host` directory to a dedicated server folder. The Cloudflare remotely managed tunnel `funzug-media` and Published application route for `media.funzug.com` are already configured, targeting `http://media:8080`. Do not create another tunnel. Cloudflare terminates public HTTPS; no home-router ports need to be opened. The published hostname is public, as required for Meta to fetch the image. The connector is not yet running; install its token on the Linux server as described below.

From the `media-host` folder:

```sh
mkdir -p secrets
umask 077
openssl rand -hex 32 > secrets/upload_token
chmod 600 secrets/upload_token
```

Store the Cloudflare tunnel token in `secrets/tunnel_token` with restrictive permissions using a text editor, not a shell command. Create `.env` with only `FUNZUG_MEDIA_DOMAIN=media.funzug.com`. Set GitHub Actions secrets `FUNZUG_MEDIA_BASE_URL` to `https://media.funzug.com` and `FUNZUG_MEDIA_UPLOAD_TOKEN` to the exact random upload-token file value. Do not add either token to `.env`, compose environment, source control, terminal command arguments, or chat. The tunnel token stays on the server and is not needed by GitHub Actions.

For Cloudflare Tunnel, start the service:

```sh
docker compose --profile tunnel up -d --build media cloudflared
docker compose ps
docker compose logs --tail=50 cloudflared media
```

Check `https://media.funzug.com/health` returns `ok` and verify the tunnel is healthy in Cloudflare. For direct inbound hosting instead, set up DNS and forward 80/443, then run `docker compose --profile direct up -d --build media caddy`. Keep the named `media_data` volume and back it up. Direct mode also uses `caddy_data` and `caddy_config`. There is no HTTP delete route. To remove a public image, use controlled server-side administration after confirming the exact filename.

## Uploading a reviewed draft image

An upload makes that image public. Only run this after reviewing the image and deciding it is okay to publish publicly. The command below is deliberately explicit and prints a public URL; it does not approve or publish a social post.

Run this from the repository root, not from the server folder:

```sh
python scripts/upload_media.py drafts/assets/IMAGE.png --confirm-public-upload FUNZUG
```

Set `FUNZUG_MEDIA_BASE_URL` and `FUNZUG_MEDIA_UPLOAD_TOKEN` in the local environment or CI secret store. Use the returned URL with `stage-draft`; staging leaves the item unapproved. A separate human approval is still required before Meta publishing.

The uploader requires exact 1080x1350 dimensions and limits uploads to 12 MiB. The host decodes PNG or JPEG input, validates its dimensions and signature, composites transparency onto white, and publishes a normalized JPEG without changing the canvas dimensions. It runs as a non-root user with a read-only container filesystem, dropped Linux capabilities, a read-only public surface, and no upload credential in logs or image URLs.
