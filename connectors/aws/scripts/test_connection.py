"""Validate an OpsAgent AWS role connection without exposing credentials."""
import json
import os
import sys

import boto3


def main():
    region = os.getenv("AWS_REGION", "us-east-1")
    role_arn = os.environ["AWS_ROLE_ARN"]
    external_id = os.environ["AWS_EXTERNAL_ID"]
    base = boto3.Session(profile_name=os.getenv("AWS_PROFILE") or None)
    response = base.client("sts", region_name=region).assume_role(
        RoleArn=role_arn,
        ExternalId=external_id,
        RoleSessionName="opsagent-connector-test",
    )
    value = response["Credentials"]
    connected = boto3.Session(
        aws_access_key_id=value["AccessKeyId"],
        aws_secret_access_key=value["SecretAccessKey"],
        aws_session_token=value["SessionToken"],
        region_name=region,
    )
    identity = connected.client("sts").get_caller_identity()
    page = connected.client("ec2").describe_instances(MaxResults=5)
    count = sum(len(item.get("Instances", [])) for item in page.get("Reservations", []))
    print(json.dumps({
        "connected": True,
        "account_id": identity["Account"],
        "principal_arn": identity["Arn"],
        "region": region,
        "instances_in_test_page": count,
    }, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Connection failed: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1)
