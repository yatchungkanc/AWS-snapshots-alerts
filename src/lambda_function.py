# Description: Lambda function to generate a snapshot inventory and send a summary via SNS

import boto3
import csv
import io
import json
from datetime import datetime, timezone
import os
from typing import Dict, List, Any

class SnapshotInventory:
    def __init__(self):
        self.ec2_client = boto3.client('ec2')
        self.rds_client = boto3.client('rds')
        self.efs_client = boto3.client('efs')
        self.backup_client = boto3.client('backup')  # Add AWS Backup client
        self.s3_client = boto3.client('s3')
        self.sns_client = boto3.client('sns')
        
        # Get environment variables
        self.s3_bucket = os.environ['S3_BUCKET_NAME']
        self.sns_topic_arn = os.environ['SNS_TOPIC_ARN']
        self.account_id = boto3.client('sts').get_caller_identity()['Account']
        
    def get_snapshot_age(self, start_time) -> int:
        """Calculate snapshot age in days"""
        now = datetime.now(timezone.utc)
        age = now - start_time
        return age.days

    def get_age_group(self, age: int) -> str:
        """Determine age group for snapshot"""
        if age <= 7: return "7 days"
        elif age <= 15: return "15 days"
        elif age <= 30: return "30 days"
        elif age <= 90: return "90 days"
        elif age <= 180: return "180 days"
        elif age <= 365: return "365 days"
        elif age <= 730: return "730 days"
        else: return "> 730 days"

    def get_all_snapshots(self) -> List[Dict[str, Any]]:
        snapshots = []
        
        # Get EBS snapshots
        try:
            paginator = self.ec2_client.get_paginator('describe_snapshots')
            for page in paginator.paginate(OwnerIds=[self.account_id]):
                for snapshot in page['Snapshots']:
                    age = self.get_snapshot_age(snapshot['StartTime'])
                    snapshots.append({
                        'Id': snapshot['SnapshotId'],
                        'Type': 'EBS',
                        'StartTime': snapshot['StartTime'].isoformat(),
                        'Size': snapshot['VolumeSize'],
                        'Age': age,
                        'AgeGroup': self.get_age_group(age)
                    })
        except Exception as e:
            print(f"Error getting EBS snapshots: {str(e)}")

        # Get RDS snapshots
        try:
            paginator = self.rds_client.get_paginator('describe_db_snapshots')
            for page in paginator.paginate():
                for snapshot in page['DBSnapshots']:
                    age = self.get_snapshot_age(snapshot['SnapshotCreateTime'])
                    snapshots.append({
                        'Id': snapshot['DBSnapshotIdentifier'],
                        'Type': 'RDS',
                        'StartTime': snapshot['SnapshotCreateTime'].isoformat(),
                        'Size': snapshot['AllocatedStorage'],
                        'Age': age,
                        'AgeGroup': self.get_age_group(age)
                    })
        except Exception as e:
            print(f"Error getting RDS snapshots: {str(e)}")

        # Get EFS backups using AWS Backup
        try:
            paginator = self.backup_client.get_paginator('list_backup_jobs')
            for page in paginator.paginate(ByResourceType='EFS'):
                for backup in page['BackupJobs']:
                    if backup['State'] == 'COMPLETED':
                        age = self.get_snapshot_age(backup['CreationDate'])
                        # Convert bytes to GB, handle cases where BackupSizeInBytes might not exist
                        size_gb = backup.get('BackupSizeInBytes', 0) / (1024 * 1024 * 1024)
                        snapshots.append({
                            'Id': backup['BackupJobId'],
                            'Type': 'EFS',
                            'StartTime': backup['CreationDate'].isoformat(),
                            'Size': round(size_gb, 2),
                            'Age': age,
                            'AgeGroup': self.get_age_group(age)
                        })
        except Exception as e:
            print(f"Error getting EFS backups: {str(e)}")

        return snapshots

    def generate_summary(self, snapshots: List[Dict[str, Any]]) -> str:
        # Sort snapshots by age in descending order
        snapshots.sort(key=lambda x: x['Age'], reverse=True)

        summary = {
            'total_count': len(snapshots),
            'by_type': {},
            'by_age_group': {}
        }

        for snapshot in snapshots:
            # Count by type
            if snapshot['Type'] not in summary['by_type']:
                summary['by_type'][snapshot['Type']] = {'count': 0, 'size': 0}
            summary['by_type'][snapshot['Type']]['count'] += 1
            summary['by_type'][snapshot['Type']]['size'] += snapshot['Size']

            # Count by age group
            if snapshot['AgeGroup'] not in summary['by_age_group']:
                summary['by_age_group'][snapshot['AgeGroup']] = {'count': 0, 'size': 0}
            summary['by_age_group'][snapshot['AgeGroup']]['count'] += 1
            summary['by_age_group'][snapshot['AgeGroup']]['size'] += snapshot['Size']

        # Format summary as email content
        email_content = f"""Snapshot Inventory Summary for Account {self.account_id}
Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Total Snapshots: {summary['total_count']}

Breakdown by Type:
{'-' * 40}"""

        for stype, data in summary['by_type'].items():
            email_content += f"\n{stype}: {data['count']} snapshots, {data['size']:.2f} GB"

        email_content += f"""

Breakdown by Age:
{'-' * 40}"""

        for age_group, data in summary['by_age_group'].items():
            email_content += f"\n{age_group}: {data['count']} snapshots, {data['size']:.2f} GB"

        return email_content

def lambda_handler(event, context):
    inventory = SnapshotInventory()
    
    # Get all snapshots
    snapshots = inventory.get_all_snapshots()
    
    # Generate CSV file
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    csv_filename = f'snapshot_inventory_{inventory.account_id}_{timestamp}.csv'
    
    # Create CSV in memory
    csv_buffer = io.StringIO()
    writer = csv.DictWriter(csv_buffer, 
                          fieldnames=['Id', 'Type', 'StartTime', 'Size', 'Age', 'AgeGroup'])
    writer.writeheader()
    writer.writerows(snapshots)
    
    # Upload CSV to S3
    inventory.s3_client.put_object(
        Bucket=inventory.s3_bucket,
        Key=csv_filename,
        Body=csv_buffer.getvalue()
    )
    
    # Generate summary and send email
    summary = inventory.generate_summary(snapshots)
    
    # Create SNS message with S3 link
    message = {
        'default': summary,
        'email': summary + f"\n\nDetailed report available in S3: s3://{inventory.s3_bucket}/{csv_filename}"
    }
    
    # Publish to SNS
    inventory.sns_client.publish(
        TopicArn=inventory.sns_topic_arn,
        Message=json.dumps(message),
        MessageStructure='json'
    )
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Snapshot inventory processed successfully',
            'csv_file': csv_filename
        })
    }
