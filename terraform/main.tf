terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.25.0"
    }
  }
  backend "gcs" {
    bucket = "openetruscan-terraform-state"
    prefix = "terraform/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

# 1. Cloud Storage Buckets
resource "google_storage_bucket" "tf_state" {
  name          = "openetruscan-terraform-state"
  location      = "EU"
  force_destroy = false
  versioning {
    enabled = true
  }
}

# ─── DEFERRED: IIIF tile bucket + Cantaloupe Cloud Run ──────────────────────
# The IIIF image-tile pipeline (bucket + public-read IAM + Cantaloupe Cloud
# Run service further down) was planned in this main.tf but never actually
# deployed. The bucket doesn't exist, the IAM binding has no target, and
# the Cantaloupe service config still carries a `placeholder-replace-me`
# secret. Applying these as-is would either fail or create insecure
# placeholders in prod.
#
# Re-enable when the IIIF pipeline actually goes live. At that point set
# a real CANTALOUPE_ENDPOINT_API_SECRET, decide on bucket location +
# retention, and verify the Cantaloupe image URI.
#
# resource "google_storage_bucket" "iiif_images" {
#   name          = "openetruscan-iiif-images"
#   location      = var.region
#   force_destroy = false
#   uniform_bucket_level_access = true
# }
#
# resource "google_storage_bucket_iam_member" "iiif_public" {
#   bucket = google_storage_bucket.iiif_images.name
#   role   = "roles/storage.objectViewer"
#   member = "allUsers"
# }

# 2. Cloud SQL Database (Imported from existing)
#
# The values below mirror the *actual* prod state captured at import time
# (2026-05-11) so the next `tofu plan` is a no-op. The historical .tf had
# drifted from prod \xe2\x80\x94 disk_size/disk_type and several tuning flags were
# adjusted by hand after the original config was written, and applying the
# old .tf as-is would have forced a database replacement.
#
# `lifecycle.ignore_changes` covers attributes that drift naturally
# (start_time + database_flags get tuned by ops). The terraform stays
# accurate as documentation but doesn't fight prod on every plan.
resource "google_sql_database_instance" "main" {
  name             = "openetruscan"
  database_version = "POSTGRES_15"
  region           = "europe-west1" # Moving to europe-west4 is a future manual operation

  settings {
    tier = "db-custom-2-7680"

    disk_type                   = "PD_HDD"
    disk_size                   = 15
    disk_autoresize             = true
    # Settings-level deletion guard (distinct from the resource-level
    # `deletion_protection` below): prevents deletion via the Cloud SQL
    # admin API even if terraform's resource-level guard is removed.
    deletion_protection_enabled = true

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      transaction_log_retention_days = 7
      start_time                     = "02:00"
      backup_retention_settings {
        retained_backups = 30
        retention_unit   = "COUNT"
      }
    }

    ip_configuration {
      ipv4_enabled    = false
      private_network = "projects/${var.project_id}/global/networks/default"
      require_ssl     = false
      ssl_mode        = "ENCRYPTED_ONLY"
    }

    location_preference {
      zone = "europe-west1-b"
    }

    database_flags {
      name  = "log_lock_waits"
      value = "on"
    }
    database_flags {
      name  = "log_min_duration_statement"
      value = "250"
    }
    database_flags {
      name  = "log_temp_files"
      value = "0"
    }
    database_flags {
      name  = "track_io_timing"
      value = "on"
    }
  }

  deletion_protection = true

  lifecycle {
    # database_flags are tuned by ops outside terraform; backup window
    # may be adjusted seasonally. Refuse to plan-clobber those.
    ignore_changes = [
      settings[0].database_flags,
      settings[0].backup_configuration[0].start_time,
    ]
  }
}

# 3. Artifact Registry (Imported from existing)
resource "google_artifact_registry_repository" "docker_repo" {
  location      = var.region
  repository_id = "openetruscan"
  description   = "OpenEtruscan API container images"
  format        = "DOCKER"
}

# 4. API Virtual Machine (Imported from existing)
#
# The VM was created/tuned by hand and has drifted far from what this .tf
# describes (boot disk type, SSH keys metadata, http/https firewall tags,
# logging+monitoring metadata flags). Terraform tracks its existence so
# accidental destroys are blocked, but `ignore_changes = all` keeps it
# from trying to "reconcile" attributes that ops actually owns. To make
# changes to this VM, edit it in console / gcloud, then re-import.
resource "google_compute_instance" "api" {
  name         = "openetruscan-eu"
  machine_type = "e2-small"
  zone         = var.zone

  boot_disk {
    initialize_params {
      image = "cos-cloud/cos-stable"
      size  = 100
      type  = "pd-balanced"
    }
  }

  network_interface {
    network = "default"
    access_config {
      // Ephemeral IP or static depending on configuration
    }
  }

  service_account {
    email  = "compute-sa@${var.project_id}.iam.gserviceaccount.com"
    scopes = ["cloud-platform"]
  }

  allow_stopping_for_update = true

  lifecycle {
    ignore_changes = all
  }
}

# 5. Secret Manager Secrets
resource "google_secret_manager_secret" "database_url" {
  secret_id = "oe-database-url"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "hf_token" {
  secret_id = "oe-hf-token"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "gemini_key" {
  secret_id = "oe-gemini-api-key"
  replication {
    auto {}
  }
}

# 6. Cloud Monitoring Policies
resource "google_monitoring_alert_policy" "slow_sql" {
  display_name = "Slow SQL Queries Alert"
  combiner     = "OR"

  conditions {
    display_name = "High Slow Query Count"
    condition_threshold {
      filter          = "metric.type=\"cloudsql.googleapis.com/database/postgresql/transaction_count\" AND resource.type=\"cloudsql_database\" AND metric.labels.transaction_type=\"slow_query\""
      duration        = "60s"
      comparison      = "COMPARISON_GT"
      threshold_value = 10

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
      trigger {
        count = 1
      }
    }
  }

  lifecycle {
    # Imported live; ops may tune thresholds without re-running terraform.
    ignore_changes = all
  }
}

# 7. Cloud Run: byt5 restorer (imported from existing)
#
# Currently running the `gcr.io/cloudrun/hello` placeholder image \xe2\x80\x94 the
# `byt5-restorer` image referenced below has not been built into Artifact
# Registry yet. Terraform tracks the service so the URL stays stable;
# `ignore_changes` keeps it from trying to replace the running placeholder
# with a not-yet-built image and breaking the URL until the image lands.
#
# When the real image is built and pushed, remove the ignore_changes block
# and re-apply to roll out the actual restorer.
resource "google_cloud_run_v2_service" "byt5" {
  name     = "openetruscan-byt5"
  location = var.region

  template {
    scaling {
      min_instance_count = 0
      max_instance_count = 10
    }
    containers {
      image = "europe-west4-docker.pkg.dev/${var.project_id}/openetruscan/byt5-restorer:latest"
      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }
    }
  }

  lifecycle {
    ignore_changes = all
  }
}

# ─── DEFERRED: minilm reranker Cloud Run ────────────────────────────────────
# Service was planned but never deployed; the
# `minilm-reranker:latest` image isn't in Artifact Registry yet. Re-enable
# when the reranker actually ships.
#
# resource "google_cloud_run_v2_service" "minilm" {
#   name     = "openetruscan-rerank"
#   location = var.region
#
#   template {
#     scaling {
#       min_instance_count = 0
#       max_instance_count = 10
#     }
#     containers {
#       image = "europe-west4-docker.pkg.dev/${var.project_id}/openetruscan/minilm-reranker:latest"
#       resources {
#         limits = {
#           cpu    = "1"
#           memory = "1Gi"
#         }
#       }
#     }
#   }
# }

# ─── DEFERRED: Cantaloupe IIIF server ───────────────────────────────────────
# Tied to the iiif_images bucket above; same reason. Note the
# `placeholder-replace-me` secret \xe2\x80\x94 do not enable until that's set to
# a real value pulled from Secret Manager.
#
# resource "google_cloud_run_v2_service" "iiif_server" {
#   name     = "openetruscan-iiif"
#   location = var.region
#
#   template {
#     scaling {
#       min_instance_count = 0
#       max_instance_count = 10
#     }
#     containers {
#       image = "krux/cantaloupe:latest"
#       env {
#         name  = "CANTALOUPE_ENDPOINT_API_SECRET"
#         value = "placeholder-replace-me"
#       }
#       env {
#         name  = "CANTALOUPE_SOURCE_STATIC"
#         value = "HttpSource"
#       }
#       env {
#         name  = "CANTALOUPE_HTTPSOURCE_BASICLOOKUPSTRATEGY_URL_PREFIX"
#         value = "https://storage.googleapis.com/${google_storage_bucket.iiif_images.name}/"
#       }
#       resources {
#         limits = {
#           cpu    = "1"
#           memory = "1Gi"
#         }
#       }
#     }
#   }
# }
