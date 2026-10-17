# Build the compatible, pinned scanner images from one Dockerfile per scanner (M0b / D41).
# One Dockerfile, built across a matrix of versions → N pinned image tags. The version lists
# default to the current pins here but are overridden in CI from versions.yaml (single source, D42).
# Run from the scanner/ dir (context = ".." — the repo root: the image needs libs/javv-common):
#   docker buildx bake -f docker-bake.hcl --print
#   docker buildx bake -f docker-bake.hcl --set '*.platform=linux/amd64'
variable "REGISTRY" {
  default = "ghcr.io/danube-labs"
}
variable "TRIVY_VERSIONS" {
  default = "0.76.0,0.70.0"
}
variable "GRYPE_VERSIONS" {
  default = "0.120.1,0.114.0"
}
# JAVV git commit that builds the image (the entrypoint is JAVV code). CI passes the short sha;
# "dev" for local builds. Each image gets a moving :<ver> tag + an immutable :<ver>-<GIT_SHA> tag.
variable "GIT_SHA" {
  default = "dev"
}

SOURCE = "https://github.com/Danube-Labs/javv-poc"

group "default" {
  targets = ["trivy", "grype"]
}

target "trivy" {
  name       = "trivy-${replace(ver, ".", "-")}"
  matrix     = { ver = split(",", TRIVY_VERSIONS) }
  context    = ".."
  dockerfile = "scanner/Dockerfile.trivy"
  args       = { TRIVY_VERSION = ver }
  tags = [
    "${REGISTRY}/javv-scanner-trivy:${ver}",            # moving: latest build of this scanner version
    "${REGISTRY}/javv-scanner-trivy:${ver}-${GIT_SHA}", # immutable: this exact JAVV build
  ]
  labels = {
    "org.opencontainers.image.version"  = ver
    "org.opencontainers.image.revision" = GIT_SHA
    "org.opencontainers.image.source"   = SOURCE
    "javv.scanner"                       = "trivy"
  }
}

target "grype" {
  name       = "grype-${replace(ver, ".", "-")}"
  matrix     = { ver = split(",", GRYPE_VERSIONS) }
  context    = ".."
  dockerfile = "scanner/Dockerfile.grype"
  args       = { GRYPE_VERSION = ver }
  tags = [
    "${REGISTRY}/javv-scanner-grype:${ver}",
    "${REGISTRY}/javv-scanner-grype:${ver}-${GIT_SHA}",
  ]
  labels = {
    "org.opencontainers.image.version"  = ver
    "org.opencontainers.image.revision" = GIT_SHA
    "org.opencontainers.image.source"   = SOURCE
    "javv.scanner"                       = "grype"
  }
}
