Interactive visualization components for mass spectrometry data in Streamlit, plus a
small set of helpers for differential expression analysis, and the gallery that
demonstrates the components. This file fixes the vocabulary; it is a glossary, not a
design document. The component and state vocabulary is defined in `CONTRIBUTING.md`.

## Language

### Data

**Quantification matrix**:
A wide table holding one row per feature and one column per sample, carrying the
measured abundance of each feature in each sample.
_Avoid_: expression matrix, intensity table, wide data

**Feature**:
The row identity of a quantification matrix — the analyte being quantified across
samples, such as a protein, peptide or proteoform. Distinct from an OpenMS
featureXML feature, which is a 2D isotopic peak cluster in a single run; when both
senses appear together, name the file format explicitly.
_Avoid_: analyte, entity, row

**Sample**:
One measured run, identified by a sample id that appears both as a column of the
quantification matrix and as a row of the sample metadata.
_Avoid_: replicate, run, experiment

**Sample metadata**:
A table mapping each sample id to the biological group it belongs to.
_Avoid_: design table, annotation, phenotype data

**Group**:
The biological condition a sample belongs to, and the unit that differential
expression compares.
_Avoid_: condition, class, cohort, label

**Working column**:
A column an analysis helper materializes part-way through a computation and removes
before returning. Named with a leading underscore, and never part of a helper's
output.
_Avoid_: temp column, intermediate, scratch column

### Code surfaces

**Core component**:
A visualization the library offers on its public surface, pairing a Python class
with a Vue view and sharing selection state with its siblings. A plain install of
the package must be enough to use one.
_Avoid_: widget, plot, chart, view

**Analysis helper**:
A transformation over a quantification matrix — filtering, imputation,
normalization, statistical testing, enrichment. It has no Vue counterpart, holds no
selection state, and is not part of the component architecture.
_Avoid_: utility, processor, pipeline step

### Gallery

**Gallery**:
The deployed Streamlit application that presents every example on one site.
_Avoid_: showcase, demo app, docs site, catalog

**Example**:
One Streamlit page demonstrating a single component or a single linking pattern
against real mass-spectrometry data.
_Avoid_: demo, sample, snippet, showcase

**Linking pattern**:
An example whose subject is the interaction between two or more components rather
than any one component. Cross-component selection is the package's distinguishing
capability, so these are a first-class category, not a variation on an example.
_Avoid_: integration example, combined example

**Coverage**:
The property that every component in the registry is demonstrated by at least one
example. Coverage is enforced by tests rather than maintained by hand, so a component
added without an example is a build failure.
_Avoid_: completeness, parity

### Example data

**Example dataset**:
The curated, versioned collection of real mass-spectrometry data that backs the
examples, published as a release asset and fetched by checksum. It is a deliverable in
its own right, versioned independently of the code.
_Avoid_: demo data, test data, fixtures, sample data

**Source dataset**:
Real data as originally published, before any transformation — a ProteomeXchange
accession, or another OpenMS application's shipped files.
_Avoid_: raw data, upstream data

**Provenance manifest**:
The record shipped with the example dataset stating, for each file, which source
dataset it derives from, which tools and versions produced it, and what transformation
was applied. It exists so a reader can trace any pixel in the gallery back to a
published measurement.
_Avoid_: data README, changelog, attribution file

**Derivation**:
The one-time, offline transformation from source dataset to example dataset. It is
deliberately not part of the build or of CI, because it is expensive and its inputs
never change.
_Avoid_: preprocessing, ETL, data pipeline

> Note: **preprocessing** already means something specific in this codebase — the
> component's own conversion of input data into its Parquet cache, which happens once
> per (data, config) pair and is reused on later constructions. Do not use it for
> derivation.
