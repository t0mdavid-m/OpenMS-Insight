# The gallery lives in the library repository, not in its own webapp repository

Every other OpenMS web application is its own repository forked from
`OpenMS/streamlit-template`. The gallery deliberately breaks that pattern: its
examples, Streamlit app, Dockerfile and Kubernetes overlay all live inside
OpenMS-Insight, excluded from the wheel and sdist by the existing hatch configuration.

The gallery is documentation for a library rather than a scientific workflow
application, and its central guarantee — that every registered component is
demonstrated by at least one example — is only enforceable when the examples sit beside
the components they document and are tested in the same run.

## Consequences

The gallery does not inherit the template's Kubernetes stack, legal pages, Matomo
analytics or Claude skills, so any of those we want must be added deliberately. In
exchange, adding a component without an example is a build failure rather than a thing
somebody notices months later in a different repository.
