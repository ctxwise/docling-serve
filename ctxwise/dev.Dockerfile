# Fast local image for development: the official CPU release plus this fork's changes (no model downloads).
# The published image is built from ../Containerfile by .github/workflows/ctxwise-image.yml.
# Build from the repository root: docker build -f ctxwise/dev.Dockerfile -t docling-serve:dev .
ARG BASE=quay.io/docling-project/docling-serve-cpu:v1.35.0
FROM ${BASE}
USER 0
RUN dnf install -y --setopt=install_weak_deps=False libreoffice-writer libreoffice-calc libreoffice-impress \
 && dnf clean all && rm -rf /var/cache/dnf
USER 1001
COPY --chown=1001:0 docling_serve /opt/app-root/src/docling_serve
