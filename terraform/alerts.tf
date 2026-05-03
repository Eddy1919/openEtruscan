resource "google_logging_metric" "admin_token_missing" {
  name        = "admin_token_missing"
  filter      = "resource.type=\"gce_instance\" AND textPayload:\"admin_token_configured=false\""
  description = "Count of logs indicating ADMIN_TOKEN is not configured"
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
      filter     = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.admin_token_missing.name}\""
      duration   = "60s"
      comparison = "COMPARISON_GT"
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
