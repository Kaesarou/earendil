# Continuous deployment to OVHcloud

Goblin production releases are created only by a push to `main`. In normal use,
branch protection makes that push the result of an explicitly authorized pull
request merge.

The `Deploy production` workflow:

1. runs the complete Python suite and validates the deployment files;
2. publishes `ghcr.io/kaesarou/goblin:<git-sha>` and the convenience tag `main`;
3. uploads a seven-day GitHub artifact containing the immutable deployment manifest;
4. copies the release files to the VPS;
5. deploys the SHA tag and waits for the container to become healthy;
6. restores the previous image when startup fails.

The VPS never checks out the repository. Its `.env` and `data/` directory remain
local and are mounted into every successive image.

## One-time VPS preparation

Install Docker Engine with the Compose plugin on the OVHcloud VPS. Create one
dedicated deployment user and directory. The deployment user must be able to run
Docker without `sudo`; membership in the `docker` group is effectively root access,
so the account and its SSH key must be dedicated to this workflow.

```bash
sudo useradd --create-home --shell /bin/bash goblin-deploy
sudo usermod --append --groups docker goblin-deploy
sudo install --directory --owner goblin-deploy --group goblin-deploy /opt/goblin
sudo install --directory --owner goblin-deploy --group goblin-deploy /opt/goblin/data
sudo -u goblin-deploy install --directory --mode 700 /home/goblin-deploy/.ssh
sudo -u goblin-deploy touch /home/goblin-deploy/.ssh/authorized_keys
sudo chmod 600 /home/goblin-deploy/.ssh/authorized_keys
```

Add the public half of the dedicated deployment key to `authorized_keys`. Copy the
runtime configuration once and restrict it to the deployment user:

```bash
sudo -u goblin-deploy nano /opt/goblin/.env
sudo chmod 600 /opt/goblin/.env
```

Keep eToro credentials exclusively in that VPS file. They must never be GitHub
Actions secrets or part of an image.

## GitHub production configuration

Create a GitHub environment named `production` and add these environment secrets:

| Secret | Value |
|---|---|
| `OVH_HOST` | VPS public IP or DNS name |
| `OVH_USER` | `goblin-deploy` |
| `OVH_SSH_PRIVATE_KEY` | private half of the dedicated deployment key |
| `OVH_SSH_KNOWN_HOSTS` | pinned VPS host-key line from `ssh-keyscan`, verified against the VPS console |

Protect `main` against direct pushes and require the `Tests / Python tests` check.
Do not configure an automatic merge. Optionally require manual approval on the
`production` environment if a second deployment confirmation is desired.

## Runtime files and rollback

The current deployed SHA is recorded in `/opt/goblin/deployment.json`. Application
state and complete run logs remain below `/opt/goblin/data`. Docker console logs are
rotated at 20 MiB with three files.

Compose sends `SIGTERM` and allows up to two minutes for Goblin to finalize the run
before replacing the container. The deploy script always uses the immutable SHA
tag. If the new container does not become healthy within 90 seconds, it restores
the preceding Compose file and image reference.
