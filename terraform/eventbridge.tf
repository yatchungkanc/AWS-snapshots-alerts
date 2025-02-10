# eventbridge.tf
resource "aws_cloudwatch_event_rule" "daily_trigger" {
  name                = "trigger-snapshot-inventory-${var.environment}"
  description         = "Triggers snapshot inventory Lambda function daily"
  schedule_expression = "rate(1 day)"
  tags               = var.tags
}

resource "aws_cloudwatch_event_target" "lambda_target" {
  rule      = aws_cloudwatch_event_rule.daily_trigger.name
  target_id = "SendToLambda"
  arn       = aws_lambda_function.snapshot_inventory.arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.snapshot_inventory.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_trigger.arn
}

