import aws_inventory


class _Paginator:
    def paginate(self, **_kwargs):
        return [{"Reservations": [{"Instances": [{
            "InstanceId": "i-0123456789abcdef0",
            "State": {"Name": "running"},
            "InstanceType": "t3.medium",
            "Platform": "windows",
            "PlatformDetails": "Windows",
            "Architecture": "x86_64",
            "ImageId": "ami-test",
            "Placement": {"AvailabilityZone": "us-east-1a"},
            "VpcId": "vpc-test",
            "SubnetId": "subnet-test",
            "PrivateIpAddress": "10.0.0.10",
            "PrivateDnsName": "ip-10-0-0-10.ec2.internal",
            "PublicIpAddress": "198.51.100.10",
            "PublicDnsName": "ec2-198-51-100-10.compute.amazonaws.com",
            "BlockDeviceMappings": [{
                "DeviceName": "/dev/sda1",
                "Ebs": {"VolumeId": "vol-test", "DeleteOnTermination": True},
            }],
            "Tags": [{"Key": "Name", "Value": "windows-test"}],
        }]}]}]


class _Ec2:
    def get_paginator(self, name):
        assert name == "describe_instances"
        return _Paginator()

    def describe_vpcs(self, **_kwargs):
        return {"Vpcs": [{"VpcId": "vpc-test", "CidrBlock": "10.0.0.0/16"}]}

    def describe_subnets(self, **_kwargs):
        return {"Subnets": [{"SubnetId": "subnet-test", "CidrBlock": "10.0.0.0/24"}]}

    def describe_volumes(self, **_kwargs):
        return {"Volumes": [{
            "VolumeId": "vol-test", "Size": 80, "VolumeType": "gp3",
            "Iops": 3000, "Throughput": 125, "Encrypted": True, "State": "in-use",
        }]}


def test_discovery_includes_dns_and_ebs_details():
    record = aws_inventory.discover_region("us-east-1", client=_Ec2())[0]
    assert record["private_dns"] == "ip-10-0-0-10.ec2.internal"
    assert record["public_dns"] == "ec2-198-51-100-10.compute.amazonaws.com"
    assert record["volume_details"] == [{
        "volume_id": "vol-test", "device": "/dev/sda1", "size_gib": 80,
        "volume_type": "gp3", "iops": 3000, "throughput_mibps": 125,
        "encrypted": True, "state": "in-use", "delete_on_termination": True,
    }]
