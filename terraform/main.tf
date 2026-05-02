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

resource "google_storage_bucket" "iiif_images" {
  name          = "openetruscan-iiif-images"
  location      = var.region
  force_destroy = false
  
  # Allow public read for IIIF image tiles
  uniform_bucket_level_access = true
}

resource "google_storage_bucket_iam_member" "iiif_public" {
  bucket = google_storage_bucket.iiif_images.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

# 2. Cloud SQL Database (Imported from existing)
resource "google_sql_database_instance" "main" {
  name             = "openetruscan"
  database_version = "POSTGRES_15"
  region           = "europe-west1" # Moving to europe-west4 is a future manual operation

  settings {
    tier = "db-custom-2-7680"
    
    disk_type = "PD_SSD"
    disk_size = 10
    disk_autoresize = true
    
    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      transaction_log_retention_days = 7
      retained_backups               = 30
    }
    
    ip_configuration {
      ipv4_enabled = false
      private_network = "projects/${var.project_id}/global/networks/default"
      require_ssl = true
    }
  }
  
  deletion_protection = true
}

# 3. Artifact Registry (Imported from existing)
resource "google_artifact_registry_repository" "docker_repo" {
  location      = var.region
  repository_id = "openetruscan"
  description   = "OpenEtruscan Docker Repository"
  format        = "DOCKER"
}

# 4. API Virtual Machine (Imported from existing)
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
      filter     = "metric.type=\"cloudsql.googleapis.com/database/postgresql/transaction_count\" AND resource.type=\"cloudsql_database\" AND metric.labels.transaction_type=\"slow_query\""
      duration   = "60s"
      comparison = "COMPARISON_GT"
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
}

# 7. Cloud Run Services (ByT5 & MiniLM)
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
}

resource "google_cloud_run_v2_service" "minilm" {
  name     = "openetruscan-rerank"
  location = var.region

  template {
    scaling {
      min_instance_count = 0
      max_instance_count = 10
    }
    containers {
      image = "europe-west4-docker.pkg.dev/${var.project_id}/openetruscan/minilm-reranker:latest"
      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }
    }
  }
}

resource "google_cloud_run_v2_service" "iiif_server" {
  name     = "openetruscan-iiif"
  location = var.region

  template {
    scaling {
      min_instance_count = 0
      max_instance_count = 10
    }
    containers {
      image = "krux/cantaloupe:latest"
      env {
        name  = "CANTALOUPE_ENDPOINT_API_SECRET"
        value = "placeholder-replace-me"
      }
      env {
        name  = "CANTALOUPE_SOURCE_STATIC"
        value = "FilesystemSource"
      }
      # A better approach for Cloud Run is HttpSource pointing to the GCS bucket or S3Source
      env {
        name  = "CANTALOUPE_SOURCE_STATIC"
        value = "HttpSource"
      }
      env {
        name  = "CANTALOUPE_HTTPSOURCE_BASICLOOKUPSTRATEGY_URL_PREFIX"
        value = "https://storage.googleapis.com/${google_storage_bucket.iiif_images.name}/"
      }
      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }
    }
  }
}
