#!/bin/bash
set -e

cd /home/edpan/openEtruscan

# 0. Create Network
echo 'Creating network...'
docker network create openetruscan-net || true

# 1. Build API
echo 'Building API...'
docker build -t openetruscan-api .

# 2. Stop and Remove existing containers
echo 'Stopping existing containers...'
docker stop openetruscan-web-1 openetruscan-api-1 openetruscan-fuseki-1 || true
docker rm openetruscan-web-1 openetruscan-api-1 openetruscan-fuseki-1 || true

# 3. Run Fuseki
echo 'Starting Fuseki...'
docker run -d \
  --name openetruscan-fuseki-1 \
  --network openetruscan-net \
  --network-alias fuseki \
  --restart unless-stopped \
  -v fuseki_data:/fuseki \
  -v /home/edpan/openEtruscan/data/rdf:/staging:ro \
  stain/jena-fuseki:latest \
  /bin/bash -c 'mkdir -p /fuseki/databases/openetruscan; if [ ! -f /fuseki/databases/openetruscan/.loaded ]; then /jena-fuseki/tdbloader --loc /fuseki/databases/openetruscan /staging/corpus.ttl; touch /fuseki/databases/openetruscan/.loaded; fi; exec /jena-fuseki/fuseki-server --loc /fuseki/databases/openetruscan /openetruscan'

# 4. Run API
echo 'Starting API...'
docker run -d \
  --name openetruscan-api-1 \
  --network openetruscan-net \
  --network-alias api \
  --restart unless-stopped \
  --memory 1600m \
  --env-file .env \
  -p 8000:8000 \
  openetruscan-api

# 5. Run Nginx
echo 'Starting Nginx...'
docker run -d \
  --name openetruscan-web-1 \
  --network openetruscan-net \
  --restart unless-stopped \
  -p 80:80 -p 443:443 \
  -v /home/edpan/openEtruscan/nginx.conf:/etc/nginx/conf.d/default.conf:ro \
  -v /home/edoardo.panichi/certs:/certs:ro \
  nginx:alpine

echo 'DEPLOYMENT COMPLETE'
docker ps
