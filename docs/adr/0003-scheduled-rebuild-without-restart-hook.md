# The deployed gallery is refreshed by scheduled rebuild, with no restart hook

The OpenMS Kubernetes cluster has no GitOps controller: CI builds and pushes images to
GHCR, and a human applies manifests. We refresh the gallery by rebuilding and pushing
the image on a schedule, and deliberately add no mechanism to restart the deployment.
The cluster picks the new image up whenever the pod next restarts, because the overlay
pins a mutable tag with `imagePullPolicy: Always`.

## Considered Options

A Kubernetes `CronJob` in our own manifests performing a scheduled `rollout restart`
(self-contained, no credentials leaving the cluster, but new cluster-side machinery);
CI holding a cluster token and restarting on merge (fastest, but puts cluster
credentials in this repository's CI and contradicts the template's stated division that
tooling edits YAML while humans apply it).

## Consequences

GHCR always holds a current image, but the **live site can lag indefinitely** — update
latency is unbounded and depends on unrelated restarts. The scheduled job also builds
against fully pinned dependencies, so on its own it cannot detect that a new Streamlit
or polars release has broken the gallery. Dependabot covers that gap instead: version
bumps arrive as pull requests whose CI runs the full example suite, so external drift
surfaces as a red PR rather than as a silently broken deployment.
