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

### Yarn installation

```
curl -sS https://dl.yarnpkg.com/debian/pubkey.gpg | sudo apt-key add -
echo "deb https://dl.yarnpkg.com/debian/ stable main" | sudo tee /etc/apt/sources.list.d/yarn.list
sudo apt update
sudo apt install yarn
yarn --version
```

### Frontend building

```
cd ...your temp path...
git clone https://github.com/tirinox/nodeop-settings
yarn install
yarn build

# move everything to /web/frontend
cp -r * ../../thorchainmonitorbot/web/frontend/
```
