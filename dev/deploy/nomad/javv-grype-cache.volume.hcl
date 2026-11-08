# The cache of the Grype database for the job javv-scan-grype: nomad volume create javv-grype-cache.volume.hcl
name      = "javv-grype-cache"
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
