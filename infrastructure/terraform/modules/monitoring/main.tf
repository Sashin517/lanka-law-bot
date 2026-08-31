resource "google_monitoring_uptime_check_config" "backend" {
  project      = var.project_id
  display_name = "LankaLawBot backend health"
  timeout      = "10s"
  period       = "300s"

  http_check {
    path         = "/healthz"
    port         = 443
    use_ssl      = true
    validate_ssl = true
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = var.backend_host
    }
  }
}

resource "google_monitoring_uptime_check_config" "frontend" {
  project      = var.project_id
  display_name = "LankaLawBot frontend health"
  timeout      = "10s"
  period       = "300s"

  http_check {
    path         = "/"
    port         = 443
    use_ssl      = true
    validate_ssl = true
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = var.frontend_host
    }
  }
}

resource "google_monitoring_notification_channel" "email" {
  project      = var.project_id
  display_name = "LankaLawBot operations email"
  type         = "email"
  labels       = { email_address = var.alert_email }
}

resource "google_monitoring_alert_policy" "availability" {
  project      = var.project_id
  display_name = "LankaLawBot service unavailable"
  combiner     = "OR"

  dynamic "conditions" {
    for_each = {
      backend  = google_monitoring_uptime_check_config.backend.uptime_check_id
      frontend = google_monitoring_uptime_check_config.frontend.uptime_check_id
    }
    content {
      display_name = "${title(conditions.key)} uptime failure"
      condition_threshold {
        filter = join(" AND ", [
          "metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\"",
          "resource.type=\"uptime_url\"",
          "metric.label.check_id=\"${conditions.value}\"",
        ])
        comparison      = "COMPARISON_GT"
        threshold_value = 0
        duration        = "300s"
        aggregations {
          alignment_period     = "300s"
          per_series_aligner   = "ALIGN_NEXT_OLDER"
          cross_series_reducer = "REDUCE_COUNT_FALSE"
          group_by_fields      = ["resource.label.host"]
        }
        trigger { count = 1 }
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.name]
  alert_strategy { auto_close = "1800s" }
}

resource "google_logging_metric" "backend_5xx" {
  project = var.project_id
  name    = "lankalawbot/backend_5xx_errors"
  filter  = <<-EOT
    resource.type="cloud_run_revision"
    resource.labels.service_name="lankalawbot-backend"
    httpRequest.status>=500
  EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

resource "google_monitoring_alert_policy" "backend_5xx" {
  project      = var.project_id
  display_name = "LankaLawBot backend 5xx errors"
  combiner     = "OR"

  conditions {
    display_name = "Backend returned a 5xx response"
    condition_threshold {
      filter = join(" AND ", [
        "metric.type=\"logging.googleapis.com/user/${google_logging_metric.backend_5xx.name}\"",
        "resource.type=\"cloud_run_revision\"",
      ])
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_DELTA"
        cross_series_reducer = "REDUCE_SUM"
      }
      trigger { count = 1 }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.name]
  alert_strategy { auto_close = "1800s" }
}

resource "google_monitoring_dashboard" "service" {
  project = var.project_id
  dashboard_json = jsonencode({
    displayName = "LankaLawBot Production"
    mosaicLayout = {
      columns = 12
      tiles = [
        {
          width = 6, height = 4
          widget = {
            title = "Cloud Run request latency"
            xyChart = {
              dataSets = [{
                plotType   = "LINE"
                targetAxis = "Y1"
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "metric.type=\"run.googleapis.com/request_latencies\" resource.type=\"cloud_run_revision\""
                    aggregation = {
                      alignmentPeriod  = "300s"
                      perSeriesAligner = "ALIGN_PERCENTILE_95"
                    }
                  }
                }
              }]
              yAxis = { label = "p95 latency", scale = "LINEAR" }
            }
          }
        },
        {
          width = 6, height = 4
          xPos  = 6
          widget = {
            title = "Cloud Run container instances"
            xyChart = {
              dataSets = [{
                plotType   = "LINE"
                targetAxis = "Y1"
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "metric.type=\"run.googleapis.com/container/instance_count\" resource.type=\"cloud_run_revision\""
                    aggregation = {
                      alignmentPeriod  = "300s"
                      perSeriesAligner = "ALIGN_MEAN"
                    }
                  }
                }
              }]
              yAxis = { label = "instances", scale = "LINEAR" }
            }
          }
        }
      ]
    }
  })
}
