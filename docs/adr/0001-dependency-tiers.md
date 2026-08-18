# Dependency tiers follow reachability from the package root

A dependency is a core dependency when it is reachable from
`openms_insight/__init__.py`, and an optional extra otherwise. Everything the
package exports must work after a plain `pip install openms-insight`, so
`scikit-learn` (PCAPlot) and `scipy` (ClusteredHeatmap) are core even though both
are imported lazily inside `_preprocess` — that laziness buys import time, not
optionality. `mygene` and `plotly` are reachable only from
`openms_insight.analysis.enrichment`, which nothing imports, so they live in the
`analysis` extra; `mygene` in particular pulls a client for the MyGene.info web
service that no component needs.

## Considered options

Making `scikit-learn` optional too was considered and rejected: `PCAPlot` is
exported alongside `Table` and `Heatmap`, and a first-class component whose default
install cannot run it is a worse trade than the download size. Reimplementing PCA on
`numpy.linalg.svd` to drop the dependency entirely was also rejected — two numerical
paths would produce differently signed components in different environments, and
preprocessed results are cached to disk under a `cache_id` that would not
distinguish them.

## Consequences

Version floors on core dependencies are bounded by the oldest supported Python, not
by the newest release. `scikit-learn>=1.8.0` required Python 3.11 and broke the 3.9
and 3.10 CI jobs at install time; the floor is now the oldest release carrying the
APIs actually used. Adding a dependency for an analysis helper means adding it to
the extra and guarding its import with an install hint, not adding it to the core
list.
