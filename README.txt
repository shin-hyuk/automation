[Steps After Git Pull]

Ensure the following files are added manually:

    .env

    credentials.json

Confirm the files are placed in the correct locations:

    both should be in the root directory

Docker container in container (backup):

    python3 -m venv venv
    source /home/node/venv/bin/activate
    python3 /home/jason/dailybot/src/main.py

    docker cp n8n:/home/node/.n8n ./n8n_backup
    ls -l ./n8n_backup

    docker stop n8n
    docker remove n8n

    docker volume create n8n_data
    docker run -dit \
        --name n8n \
        -v n8n_data:/home/node/.n8n \
        -v /home/jason:/home/jason \
        -v /home/ken:/home/ken \
        -v /var/run/docker.sock:/var/run/docker.sock \
        -v /usr/bin/docker:/usr/bin/docker \
        -e N8N_SSL_CERT=/home/node/.n8n/n8n.ungr.app.crt \
        -e N8N_SSL_KEY=/home/node/.n8n/n8n.ungr.app.key \
        -e N8N_PROTOCOL=https \
        -e WEBHOOK_URL=https://n8n.ungr.app \
        -e NODE_VERSION=20.18.0 \
        -e YARN_VERSION=1.22.22 \
        -e NODE_ENV=production \
        -e N8N_VERSION=1.69.2 \
        -e N8N_RELEASE_TYPE=stable \
        -p 5678:5678 \
        --entrypoint "tini" \
        n8n-with-python -- /docker-entrypoint.sh


    docker cp n8n:/home/node/.n8n ./n8n_backup

    cat /etc/group | grep docker
    docker exec -it -u root n8n sh
    addgroup -g 110 docker
    addgroup node docker
    docker restart n8n

    docker network create selenium-net
    docker run -dit \
        --name selenium-chromium \
        --network selenium-net \
        -v /path/to/your/config:/config \
        -p 4444:4444 \
        selenium/standalone-chromium
    docker network connect selenium-net selenium-chromium
    docker network connect selenium-net n8n
