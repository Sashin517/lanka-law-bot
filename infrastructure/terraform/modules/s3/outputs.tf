output "pipeline_bucket_id" {
  value = aws_s3_bucket.pipeline_artifacts.id
}

output "pipeline_bucket_arn" {
  value = aws_s3_bucket.pipeline_artifacts.arn
}
