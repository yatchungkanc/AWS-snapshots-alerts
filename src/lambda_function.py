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
        self.account_id = boto3.client('sts').get_caller_identity()['Account']
               
        # Get environment variables
        self.s3_bucket = os.environ['S3_BUCKET_NAME']
        self.sns_topic_arn = os.environ['SNS_TOPIC_ARN']
        self.email_subject = os.environ.get('EMAIL_SUBJECT', 'AWS Snapshot Inventory Report')  # Default title if not set
        
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

    def get_unattached_volumes(self) -> List[Dict[str, Any]]:
        """Get all unattached EBS volumes and their idle time"""
        unattached_volumes = []
        
        try:
            paginator = self.ec2_client.get_paginator('describe_volumes')
            for page in paginator.paginate():
                for volume in page['Volumes']:
                    # Check if volume has no attachments
                    if not volume['Attachments']:
                        # Calculate days since last attachment using State.Transition time if available
                        idle_days = 0
                        if 'StateTransitionTime' in volume:
                            idle_days = self.get_snapshot_age(volume['StateTransitionTime'])
                        
                        unattached_volumes.append({
                            'VolumeId': volume['VolumeId'],
                            'Size': volume['Size'],
                            'State': volume['State'],
                            'IdleDays': idle_days,
                            'VolumeType': volume['VolumeType'],
                            'CreateTime': volume['CreateTime'].isoformat()
                        })
        except Exception as e:
            print(f"Error getting unattached volumes: {str(e)}")
        
        # Sort by idle days in descending order
        unattached_volumes.sort(key=lambda x: x['IdleDays'], reverse=True)
        return unattached_volumes

    def generate_summary(self, snapshots: List[Dict[str, Any]]) -> str:
        # Get unattached volumes
        unattached_volumes = self.get_unattached_volumes()
        
        # Calculate summary statistics
        summary = {
            'total_count': len(snapshots),
            'by_region': {},
            'by_type': {},
            'by_age_group': {}
        }
        
        # Calculate breakdown by region and type
        # Sort snapshots by age in descending order
        snapshots.sort(key=lambda x: x['Age'], reverse=True)
        for snapshot in snapshots:
            region = snapshot.get('Region', 'unknown')
            stype = snapshot['Type']
            
            # Initialize region if not exists
            if region not in summary['by_region']:
                summary['by_region'][region] = {
                    'count': 0,
                    'size': 0,
                    'by_type': {}
                }
            
            # Update region totals
            summary['by_region'][region]['count'] += 1
            summary['by_region'][region]['size'] += snapshot['Size']
            
            # Update region type breakdown
            if stype not in summary['by_region'][region]['by_type']:
                summary['by_region'][region]['by_type'][stype] = {
                    'count': 0, 'size': 0
                }
            summary['by_region'][region]['by_type'][stype]['count'] += 1
            summary['by_region'][region]['by_type'][stype]['size'] += snapshot['Size']
            
            # Update global type totals
            if stype not in summary['by_type']:
                summary['by_type'][stype] = {'count': 0, 'size': 0}
            summary['by_type'][stype]['count'] += 1
            summary['by_type'][stype]['size'] += snapshot['Size']
            
            # Update age group totals
            age_group = snapshot['AgeGroup']
            if age_group not in summary['by_age_group']:
                summary['by_age_group'][age_group] = {'count': 0, 'size': 0}
            summary['by_age_group'][age_group]['count'] += 1
            summary['by_age_group'][age_group]['size'] += snapshot['Size']

        # Generate email content
        email_content = f"""Snapshot Inventory Summary for Account {self.account_id}
    Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

    Total Snapshots: {summary['total_count']}

    Regional Breakdown:
    {'-' * 40}"""

        # Add regional breakdown
        for region, data in summary['by_region'].items():
            email_content += f"\n\nRegion: {region}"
            email_content += f"\nTotal: {data['count']} snapshots, {data['size']:.2f} GB"
            email_content += "\nBy Type:"
            for stype, type_data in data['by_type'].items():
                email_content += f"\n  - {stype}: {type_data['count']} snapshots, {type_data['size']:.2f} GB"

        email_content += f"\n\nGlobal Breakdown by Type:\n{'-' * 40}"
        for stype, data in summary['by_type'].items():
            email_content += f"\n{stype}: {data['count']} snapshots, {data['size']:.2f} GB"

        email_content += f"\n\nBreakdown by Age:\n{'-' * 40}"
        for age_group, data in summary['by_age_group'].items():
            email_content += f"\n{age_group}: {data['count']} snapshots, {data['size']:.2f} GB"

        # Add unattached volumes section with regional breakdown
        email_content += f"\n\nUnattached EBS Volumes Summary:\n{'-' * 40}"
        email_content += f"\nTotal Unattached Volumes: {len(unattached_volumes)}"
        
        if unattached_volumes:
            # Group volumes by region
            volumes_by_region = {}
            for vol in unattached_volumes:
                region = vol.get('Region', 'unknown')
                if region not in volumes_by_region:
                    volumes_by_region[region] = []
                volumes_by_region[region].append(vol)

            # Display volumes by region
            for region, volumes in volumes_by_region.items():
                total_size = sum(vol['Size'] for vol in volumes)
                email_content += f"\n\nRegion: {region}"
                email_content += f"\nVolumes: {len(volumes)}, Total Size: {total_size} GB"
                email_content += "\nTop Idle Volumes (by days unattached):"
                
                # List top 5 longest idle volumes per region
                for vol in sorted(volumes, key=lambda x: x['IdleDays'], reverse=True)[:5]:
                    email_content += (f"\nVolume ID: {vol['VolumeId']}\n"
                                    f"  - Idle Days: {vol['IdleDays']}\n"
                                    f"  - Size: {vol['Size']} GB\n"
                                    f"  - Type: {vol['VolumeType']}\n"
                                    f"  - State: {vol['State']}")
        else:
            email_content += "\nNo unattached volumes found."

        return email_content


    def get_all_regions(self) -> List[str]:
        """Get list of all AWS regions"""
        try:
            regions = [region['RegionName'] 
                      for region in self.ec2_client.describe_regions()['Regions']]
            return regions
        except Exception as e:
            print(f"Error getting regions: {str(e)}")
            return []

    def get_snapshots_for_region(self, region: str) -> List[Dict[str, Any]]:
        """Get snapshots from a specific region"""
        snapshots = []
        
        # Create regional clients
        ec2_regional = boto3.client('ec2', region_name=region)
        rds_regional = boto3.client('rds', region_name=region)
        backup_regional = boto3.client('backup', region_name=region)
        
        # Get EBS snapshots
        try:
            paginator = ec2_regional.get_paginator('describe_snapshots')
            for page in paginator.paginate(OwnerIds=[self.account_id]):
                for snapshot in page['Snapshots']:
                    age = self.get_snapshot_age(snapshot['StartTime'])
                    snapshots.append({
                        'Id': snapshot['SnapshotId'],
                        'Type': 'EBS',
                        'Region': region,
                        'StartTime': snapshot['StartTime'].isoformat(),
                        'Size': snapshot['VolumeSize'],
                        'Age': age,
                        'AgeGroup': self.get_age_group(age)
                    })
        except Exception as e:
            print(f"Error getting EBS snapshots in {region}: {str(e)}")

        # Get RDS snapshots
        try:
            paginator = rds_regional.get_paginator('describe_db_snapshots')
            for page in paginator.paginate():
                for snapshot in page['DBSnapshots']:
                    age = self.get_snapshot_age(snapshot['SnapshotCreateTime'])
                    snapshots.append({
                        'Id': snapshot['DBSnapshotIdentifier'],
                        'Type': 'RDS',
                        'Region': region,
                        'StartTime': snapshot['SnapshotCreateTime'].isoformat(),
                        'Size': snapshot['AllocatedStorage'],
                        'Age': age,
                        'AgeGroup': self.get_age_group(age)
                    })
        except Exception as e:
            print(f"Error getting RDS snapshots in {region}: {str(e)}")

        # Get EFS backups using AWS Backup
        try:
            paginator = backup_regional.get_paginator('list_backup_jobs')
            for page in paginator.paginate(ByResourceType='EFS'):
                for backup in page['BackupJobs']:
                    if backup['State'] == 'COMPLETED':
                        age = self.get_snapshot_age(backup['CreationDate'])
                        size_gb = backup.get('BackupSizeInBytes', 0) / (1024 * 1024 * 1024)
                        snapshots.append({
                            'Id': backup['BackupJobId'],
                            'Type': 'EFS',
                            'Region': region,
                            'StartTime': backup['CreationDate'].isoformat(),
                            'Size': round(size_gb, 2),
                            'Age': age,
                            'AgeGroup': self.get_age_group(age)
                        })
        except Exception as e:
            print(f"Error getting EFS backups in {region}: {str(e)}")

        return snapshots

    def get_all_regions_snapshots(self) -> List[Dict[str, Any]]:
        """Get snapshots from all regions"""
        all_snapshots = []
        regions = self.get_all_regions()
        
        for region in regions:
            print(f"Processing region: {region}")
            region_snapshots = self.get_snapshots_for_region(region)
            all_snapshots.extend(region_snapshots)
            
        return all_snapshots

    def get_unattached_volumes_for_region(self, region: str) -> List[Dict[str, Any]]:
        """Get unattached volumes for a specific region"""
        unattached_volumes = []
        
        try:
            ec2_regional = boto3.client('ec2', region_name=region)
            paginator = ec2_regional.get_paginator('describe_volumes')
            for page in paginator.paginate():
                for volume in page['Volumes']:
                    if not volume['Attachments']:
                        idle_days = 0
                        if 'StateTransitionTime' in volume:
                            idle_days = self.get_snapshot_age(volume['StateTransitionTime'])
                        
                        unattached_volumes.append({
                            'VolumeId': volume['VolumeId'],
                            'Region': region,
                            'Size': volume['Size'],
                            'State': volume['State'],
                            'IdleDays': idle_days,
                            'VolumeType': volume['VolumeType'],
                            'CreateTime': volume['CreateTime'].isoformat()
                        })
        except Exception as e:
            print(f"Error getting unattached volumes in {region}: {str(e)}")
            
        return unattached_volumes

    def get_all_regions_unattached_volumes(self) -> List[Dict[str, Any]]:
        """Get unattached volumes from all regions"""
        all_unattached_volumes = []
        regions = self.get_all_regions()
        
        for region in regions:
            print(f"Processing unattached volumes in region: {region}")
            region_volumes = self.get_unattached_volumes_for_region(region)
            all_unattached_volumes.extend(region_volumes)
            
        all_unattached_volumes.sort(key=lambda x: x['IdleDays'], reverse=True)
        return all_unattached_volumes

def lambda_handler(event, context):
    inventory = SnapshotInventory()
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Create email subject with account ID and timestamp
    email_subject = f"{inventory.email_subject} - Account {inventory.account_id} - {timestamp}"
    
    # Get snapshots from all regions
    snapshots = inventory.get_all_regions_snapshots()
    
    # Get unattached volumes from all regions
    unattached_volumes = inventory.get_all_regions_unattached_volumes()

    # Generate CSV file
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    csv_filename = f'snapshot_inventory_{inventory.account_id}_{timestamp}.csv'
    
    # Create CSV in memory
    csv_buffer = io.StringIO()
    writer = csv.DictWriter(csv_buffer, 
                          fieldnames=['Id', 'Type', 'Region', 'StartTime', 
                                    'Size', 'Age', 'AgeGroup'])
    writer.writeheader()
    writer.writerows(snapshots)
    
    # Upload CSV to S3
    inventory.s3_client.put_object(
        Bucket=inventory.s3_bucket,
        Key=csv_filename,
        Body=csv_buffer.getvalue()
    )
    
    # Unattached volumes CSV
    volumes_csv_filename = f'unattached_volumes_{inventory.account_id}_{timestamp}.csv'
    volumes_csv_buffer = io.StringIO()
    volumes_writer = csv.DictWriter(volumes_csv_buffer,
                                  fieldnames=['VolumeId', 'Region', 'Size', 'State', 
                                            'IdleDays', 'VolumeType', 'CreateTime'])
    volumes_writer.writeheader()
    volumes_writer.writerows(unattached_volumes)
    
    # Upload volumes CSV to S3
    inventory.s3_client.put_object(
        Bucket=inventory.s3_bucket,
        Key=volumes_csv_filename,
        Body=volumes_csv_buffer.getvalue()
    )

    # Generate summary and send email
    summary = inventory.generate_summary(snapshots)
    
    # Create SNS message with S3 links
    message = {
        'default': summary,
        'email': summary + f"\n\nDetailed reports available in S3:\n" +
                f"Snapshots: s3://{inventory.s3_bucket}/{csv_filename}\n" +
                f"Unattached Volumes: s3://{inventory.s3_bucket}/{volumes_csv_filename}"
    }

    # Publish to SNS
    inventory.sns_client.publish(
        TopicArn=inventory.sns_topic_arn,
        Message=json.dumps(message),
        MessageStructure='json',
        Subject=email_subject
    )
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Snapshot inventory processed successfully',
            'csv_file': csv_filename
        })
    }
