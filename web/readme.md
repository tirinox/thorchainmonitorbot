# Web interface

This guide will help you to setup the web interface for the bot.

## SSL certificate

Certificates live in `web/letsencrypt/conf` and are renewed by the `certbot` service in `docker-compose.yml`
(every 12 hours, HTTP-01 challenge served by nginx from `web/letsencrypt/www`). nginx reloads itself every 6 hours
to pick up a renewed certificate. Nothing needs to be installed on the host.

The domain is `DOMAIN` from `.env`; `web/nginx.conf` expects the certificate of `settings.thornode.org`.

Issue the first certificate (stops nginx for a moment, because nginx cannot start without a certificate):

```
make certbot
```

Check that renewal works through nginx:

```
make certbot-test
```

## Frontend

The node-operator settings page is a separate Vue 3 + Vite app: https://github.com/tirinox/nodeop-settings.
It is built into `web/frontend`, which nginx serves as static files (`/`), while `/api/*` goes to the `api` container.

Build and deploy it (only Docker is needed on the host; the Node version comes from the app's `.nvmrc`):

```
make frontend-build
```

This clones or pulls the app into `temp/nodeop-settings`, runs `npm ci && npm run build` in a `node:<version>-alpine`
container and replaces the contents of `web/frontend`. nginx picks it up right away, no restart is needed.
If the build fails, the deployed frontend is left untouched.

The previous version is kept in `temp/frontend-prev`; to bring it back:

```
make frontend-rollback
```

The page loads the node list from `/api/nodes`, so deploy the matching `api` container as well.
