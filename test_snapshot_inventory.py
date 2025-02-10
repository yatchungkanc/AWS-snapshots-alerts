import unittest
import boto3
from botocore.exceptions import ClientError
import os
from unittest.mock import Mock, patch

class TestDeployment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Initialize AWS clients
        cls.lambda_client = boto3.client('lambda')
        cls.s3_client = boto3.client('s3')
        cls.sns_client = boto3.client('sns')
        
        # Get configuration from environment variables
        cls.function_name = os.getenv('LAMBDA_FUNCTION_NAME', 'snapshot-inventory-nonprod')
        cls.bucket_name = os.getenv('S3_BUCKET_NAME')
        cls.sns_topic_name = os.getenv('SNS_TOPIC_NAME')

    def test_lambda_function_configuration(self):
        """Test if Lambda function exists and has correct configuration"""
        try:
            response = self.lambda_client.get_function(
                FunctionName=self.function_name
            )
            
            # Verify function configuration
            config = response['Configuration']
            self.assertEqual(config['Runtime'], 'python3.9')
            self.assertEqual(config['Handler'], 'lambda_function.lambda_handler')
            self.assertGreaterEqual(config['Timeout'], 300)
            self.assertGreaterEqual(config['MemorySize'], 256)
            
            # Verify environment variables
            env_vars = config['Environment']['Variables']
            self.assertIn('SNS_TOPIC_ARN', env_vars)
            self.assertIn('S3_BUCKET_NAME', env_vars)
            self.assertIn('ENVIRONMENT', env_vars)
            
        except ClientError as e:
            self.fail(f"Lambda function not found: {str(e)}")

    def test_s3_bucket_configuration(self):
        """Test if S3 bucket exists and has correct configuration"""
        try:
            # Check bucket exists
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            
            # Check bucket encryption
            encryption = self.s3_client.get_bucket_encryption(
                Bucket=self.bucket_name
            )
            self.assertIn('ServerSideEncryptionConfiguration', encryption)
            
            # Check bucket versioning
            versioning = self.s3_client.get_bucket_versioning(
                Bucket=self.bucket_name
            )
            self.assertEqual(versioning.get('Status', 'Disabled'), 'Enabled')
            
        except ClientError as e:
            self.fail(f"S3 bucket test failed: {str(e)}")

    def test_lambda_iam_role(self):
        """Test if Lambda function has required IAM permissions"""
        try:
            response = self.lambda_client.get_function(
                FunctionName=self.function_name
            )
            role_arn = response['Configuration']['Role']
            
            iam_client = boto3.client('iam')
            role_name = role_arn.split('/')[-1]
            
            # Get attached policies
            policies = iam_client.list_attached_role_policies(
                RoleName=role_name
            )
            
            # Verify required policies are attached
            policy_names = [p['PolicyName'] for p in policies['AttachedPolicies']]
            required_permissions = [
                'AWSLambdaBasicExecutionRole',
                'AmazonS3FullAccess',
                'AmazonSNSFullAccess'
            ]
            
            for perm in required_permissions:
                self.assertTrue(
                    any(perm in name for name in policy_names),
                    f"Missing required permission: {perm}"
                )
                
        except ClientError as e:
            self.fail(f"IAM role test failed: {str(e)}")

    def test_sns_topic_configuration(self):
        """Test if SNS topic exists and has correct configuration"""
        try:
            # Get topic attributes
            response = self.sns_client.get_topic_attributes(
                TopicArn=self.sns_topic_name
            )
            
            attributes = response['Attributes']
            self.assertIn('DisplayName', attributes)
            self.assertIn('Policy', attributes)
            
        except ClientError as e:
            self.fail(f"SNS topic test failed: {str(e)}")

    @patch('boto3.client')
    def test_lambda_function_invocation(self, mock_boto3_client):
        """Test if Lambda function can be invoked successfully"""
        mock_lambda = Mock()
        mock_boto3_client.return_value = mock_lambda
        
        # Mock successful response
        mock_lambda.invoke.return_value = {
            'StatusCode': 200,
            'Payload': 'Success'
        }
        
        try:
            response = self.lambda_client.invoke(
                FunctionName=self.function_name,
                InvocationType='RequestResponse'
            )
            
            self.assertEqual(response['StatusCode'], 200)
            
        except ClientError as e:
            self.fail(f"Lambda invocation test failed: {str(e)}")

    def test_deployment_rollback_capability(self):
        """Test if deployment rollback is possible"""
        try:
            versions = self.lambda_client.list_versions_by_function(
                FunctionName=self.function_name
            )
            # Should have at least 2 versions ($LATEST and one published)
            self.assertGreater(
                len(versions['Versions']), 
                1, 
                "Insufficient versions for rollback capability"
            )
        except ClientError as e:
            self.fail(f"Rollback capability test failed: {str(e)}")

def run_tests():
    """Run all deployment tests"""
    suite = unittest.TestLoader().loadTestsFromTestCase(TestDeployment)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return result.wasSuccessful()

if __name__ == '__main__':
    import sys
    sys.exit(0 if run_tests() else 1)
