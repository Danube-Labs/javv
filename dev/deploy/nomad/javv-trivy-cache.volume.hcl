# The cache of the Trivy database for the job javv-scan-trivy: nomad volume create javv-trivy-cache.volume.hcl
name      = "javv-trivy-cache"
type      = "host"
plugin_id = "mkdir"

capability {
  access_mode     = "single-node-writer"
  attachment_mode = "file-system"
}

# The JAVV scanner images run as the user 65532.
parameters {
  mode = "0700"
  uid  = 65532
  gid  = 65532
}
