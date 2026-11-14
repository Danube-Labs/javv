# Scans the running Docker images of this Nomad cluster with Grype and pushes them to JAVV.
# Steps and settings: README.md in this folder.

variable "javv_url" {
  type        = string
  description = "The address of JAVV, for example https://javv.example.com"
}

variable "cluster_id" {
  type        = string
  description = "The ID of this cluster in JAVV"
}

variable "image" {
  type    = string
  default = "ghcr.io/danube-labs/javv-scanner-grype:0.121.3"
}

job "javv-scan-grype" {
  type = "batch"

  # The scan jobs skip each job with this meta: themselves and each other.
  meta {
    javv_scan = "true"
  }

  # One scan cycle every 6 hours. Two runs never overlap.
  periodic {
    crons            = ["0 */6 * * *"]
    prohibit_overlap = true
  }

  group "scan" {
    # A failed run waits for the next run of the schedule.
    restart {
      attempts = 0
      mode     = "fail"
    }

    reschedule {
      attempts  = 0
      unlimited = false
    }

    # The vulnerability database stays here between runs.
    volume "cache" {
      type            = "host"
      source          = "javv-grype-cache"
      access_mode     = "single-node-writer"
      attachment_mode = "file-system"
    }

    task "push" {
      driver = "docker"

      config {
        image        = var.image
        entrypoint   = ["python3"]
        args         = ["/local/javv_nomad_push.py"]
        network_mode = "host" # reaches the local Nomad agent on 127.0.0.1
      }

      volume_mount {
        volume      = "cache"
        destination = "/var/cache/javv/grype"
      }

      # The Nomad token of this task, in NOMAD_TOKEN. The policy javv-scan gives it its access.
      identity {
        env = true
      }

      env {
        NOMAD_ADDR       = "http://127.0.0.1:4646"
        JAVV_BACKEND_URL = var.javv_url
        JAVV_CLUSTER_ID  = var.cluster_id
      }

      # The JAVV push token, from the Nomad variable nomad/jobs/javv-scan-grype.
      template {
        data        = <<EOT
JAVV_TOKEN={{ with nomadVar "nomad/jobs/javv-scan-grype" }}{{ .javv_token }}{{ end }}
EOT
        destination = "secrets/javv.env"
        env         = true
      }

      template {
        data            = file("javv_nomad_push.py")
        destination     = "local/javv_nomad_push.py"
        left_delimiter  = "[[[["
        right_delimiter = "]]]]"
      }

      resources {
        cpu    = 500
        memory = 1024
      }
    }
  }
}
