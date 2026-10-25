# The example dataset is committed to the repository

The gallery is backed by real mass-spectrometry data derived from FLASHApp's shipped
example files and from ProteomeXchange PXD044981. The derived dataset is committed
under `gallery/data/`, together with a `manifest.json` recording, per table, which
source it came from and what transformation produced it.

We originally decided to publish it as a versioned GitHub Release asset fetched by
SHA-256, to keep binary data out of a library repository's permanent history. Once
derivation was implemented the dataset turned out to be **4.4 MB** — distilled from
8.1 GB of source — which is small enough that the objection no longer holds. Committing
it removes fetch-and-verify plumbing from the Dockerfile, CI and the scheduled build,
lets the gallery run offline from a single clone, and means no release has to exist
before the gallery can build at all.

## Considered Options

A release asset fetched by checksum (data versioned independently of code, but a
release must exist before anything builds, and the fetch logic is duplicated in three
places); Git LFS (quota consumed on every CI clone); fetching from FLASHApp at a pinned
commit (couples us to another application's **internal** `cache/files/` layout, which
is not a published data contract).

## Consequences

Derivation stays a deliberate manual step, run by a maintainer via
`tools/derive_example_dataset.py` and committed as a normal change — appropriate, since
its inputs are published measurements that never change. The multi-gigabyte source
archives are never fetched by CI. The dataset is excluded from the wheel and sdist by
the existing hatch configuration, which whitelists only `openms_insight/**`, so PyPI
users do not download it.
