resource "google_logging_metric" "admin_token_missing" {
  name = "admin_token_missing"
  # Created via `gcloud logging metrics create` during the dashboard
  # rollout (PR #59 deploy notes). Imported here so terraform tracks
  # existence; description matches gcloud's create string so plan stays
  # clean.
  filter      = "resource.type=\"gce_instance\" AND textPayload:\"admin_token_configured=false\""
  description = "Count of logs indicating ADMIN_TOKEN is not configured at startup"
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

resource "google_monitoring_alert_policy" "admin_token_alert" {
  display_name = "Admin Token Not Configured Alert"
  combiner     = "OR"
  conditions {
    display_name = "Admin Token Missing"
    condition_threshold {
      # GCP rejects monitoring filters that don't constrain `resource.type`.
      # The metric itself is keyed by gce_instance, so we anchor here too.
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.admin_token_missing.name}\" resource.type=\"gce_instance\""
      duration        = "60s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0
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
