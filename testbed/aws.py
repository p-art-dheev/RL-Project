"""Create / inspect / destroy the PACE AWS testbed (works on the AWS Free plan).

  python -m testbed.aws check     # credentials, permissions, instance types: launches nothing
  python -m testbed.aws up        # 2 workers in ap-south-1 (fog) + 2 in eu-north-1 (cloud)
  python -m testbed.aws status    # list instances, health-check workers
  python -m testbed.aws down      # terminate everything tagged project=pace, delete security groups
  python -m testbed.aws stop | start   # pause between sessions (start rewrites the new IPs)
  python -m testbed.aws allow     # your laptop's public IP changed (new Wi-Fi)? re-authorise it
  python -m testbed.aws allow --wide   # campus network with several rotating public IPs: allow their /24s

Credentials come from the standard AWS chain (aws configure / env vars). Workers are
installed by cloud-init user-data (no SSH needed). The worker port is only opened to
your laptop's public IP and to the other workers. All requests need the shared token.
Instance types are Free-plan eligible: c7i-flex.large (x86) with t3.small fallback, t4g.small (ARM).
"""
from __future__ import annotations

import argparse
import base64
import gzip
import ipaddress
import json
import secrets
import time
import urllib.request
from pathlib import Path

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

ROOT = Path(__file__).resolve().parent
TAG = {"Key": "project", "Value": "pace"}
PORT = 80  # plain HTTP on 80 passes most campus / office firewalls
SITES = [  # (region, tier, loc, zone, prefix)
    ("ap-south-1", 1, "BOM", "IN-WE", "bom"),
    ("eu-north-1", 2, "ARN", "SE-SE3", "arn"),
]
TYPES = {"x86": ["c7i-flex.large", "t3.small"], "arm": ["t4g.small"]}
POWER = {"x86": (0.74, 3.5), "arm": (0.47, 1.69)}  # W per vCPU (Cloud Carbon Footprint)
AMI = {"x86": "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64",
       "arm": "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"}


IP_SERVICES = ("https://checkip.amazonaws.com", "https://api.ipify.org", "https://icanhazip.com")


def my_ips(rounds: int = 3) -> list[str]:
    """All public IPs this laptop shows up as. Campus networks often balance new connections
    over several ISP links, so a single lookup can miss the IP a worker connection will use."""
    seen = set()
    for _ in range(rounds):
        for url in IP_SERVICES:
            try:
                ip = urllib.request.urlopen(url, timeout=5).read().decode().strip()
                ipaddress.ip_address(ip)
                seen.add(ip)
            except Exception:  # noqa: BLE001
                pass
    if not seen:
        raise SystemExit("could not determine the laptop's public IP (no internet?)")
    return sorted(seen)


def laptop_cidrs(wide: bool = False) -> list[str]:
    ips = my_ips()
    if len(ips) > 1:
        print(f"note: this network uses {len(ips)} public IPs ({', '.join(ips)}), e.g. campus load balancing; "
              "all are allowed")
    return [str(ipaddress.ip_network(f"{ip}/{24 if wide else 32}", strict=False)) for ip in ips]


def user_data(name: str, token: str) -> str:
    # EC2 user-data is limited to 16 KB, so ship the worker gzip-compressed
    worker = base64.b64encode(gzip.compress((ROOT / "worker.py").read_bytes())).decode()
    return f"""#!/bin/bash
set -e
dnf install -y python3-pip
pip3 install numpy aiohttp "opencv-python-headless<5"
mkdir -p /opt/pace && echo '{worker}' | base64 -d | gunzip > /opt/pace/worker.py
cat > /etc/systemd/system/pace-worker.service <<EOF
[Unit]
Description=PACE worker
After=network-online.target
[Service]
Environment=PACE_TOKEN={token}
Environment=PACE_NAME={name}
Environment=PACE_CORES=2
ExecStart=/usr/bin/python3 /opt/pace/worker.py --port {PORT}
Restart=always
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload && systemctl enable --now pace-worker
"""


def ensure_sg(ec2, cidrs: list[str]) -> str:
    vpc = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])["Vpcs"][0]["VpcId"]
    sgs = ec2.describe_security_groups(Filters=[{"Name": "group-name", "Values": ["pace-sg"]},
                                                {"Name": "vpc-id", "Values": [vpc]}])["SecurityGroups"]
    if sgs:
        sg = sgs[0]["GroupId"]
    else:
        sg = ec2.create_security_group(GroupName="pace-sg", Description="PACE testbed workers", VpcId=vpc,
                                       TagSpecifications=[{"ResourceType": "security-group", "Tags": [TAG]}])["GroupId"]
    for c in cidrs:
        try:
            ec2.authorize_security_group_ingress(GroupId=sg, IpPermissions=[{
                "IpProtocol": "tcp", "FromPort": PORT, "ToPort": PORT, "IpRanges": [{"CidrIp": c}]}])
        except ClientError as e:
            if "Duplicate" not in str(e):
                raise
    return sg


def launch(region: str, arch: str, name: str, sg: str, token: str) -> dict:
    ec2 = boto3.client("ec2", region_name=region)
    ami = boto3.client("ssm", region_name=region).get_parameter(Name=AMI[arch])["Parameter"]["Value"]
    last = None
    for itype in TYPES[arch]:
        try:
            r = ec2.run_instances(ImageId=ami, InstanceType=itype, MinCount=1, MaxCount=1, SecurityGroupIds=[sg],
                                  UserData=user_data(name, token),
                                  MetadataOptions={"HttpTokens": "required"},
                                  BlockDeviceMappings=[{"DeviceName": "/dev/xvda",
                                                        "Ebs": {"VolumeSize": 8, "VolumeType": "gp3"}}],
                                  TagSpecifications=[{"ResourceType": "instance",
                                                      "Tags": [TAG, {"Key": "Name", "Value": f"pace-{name}"}]}])
            iid = r["Instances"][0]["InstanceId"]
            print(f"  launched {name} {itype} {iid} in {region}")
            return dict(id=iid, region=region, type=itype, arch=arch, name=name)
        except ClientError as e:
            last = e
            print(f"  {itype} not available in {region} ({e.response['Error']['Code']}), trying next")
    raise last


def up(a) -> None:
    suffix_pool = "" if a.pool == "a" else f"-{a.pool}"
    token = secrets.token_hex(16)
    cidrs = laptop_cidrs(a.wide)
    print("laptop public IP:", ", ".join(cidrs))
    launched = []
    for region, tier, loc, zone, prefix in SITES:
        ec2 = boto3.client("ec2", region_name=region)
        sg = ensure_sg(ec2, cidrs)
        for arch, suffix in (("x86", "x86"), ("arm", "arm")):
            name = f"{prefix}-{suffix}{suffix_pool}"
            launched.append({**launch(region, arch, name, sg, token), "tier": tier, "loc": loc, "zone": zone, "sg": sg})
    print("waiting for public IPs ...")
    for inst in launched:
        ec2 = boto3.client("ec2", region_name=inst["region"])
        ec2.get_waiter("instance_running").wait(InstanceIds=[inst["id"]])
        d = ec2.describe_instances(InstanceIds=[inst["id"]])["Reservations"][0]["Instances"][0]
        inst["ip"] = d["PublicIpAddress"]
    worker_cidrs = [f"{i['ip']}/32" for i in launched]
    for region, *_r in SITES:
        ensure_sg(boto3.client("ec2", region_name=region), worker_cidrs)  # worker <-> worker data transfer
    write_nodes(launched, token, a.edges, a.pool)
    print("cloud-init installs the workers in ~2-3 min. Then run:  python -m testbed.aws status")


def write_nodes(launched: list[dict], token: str, n_edges: int, pool: str = "a") -> None:
    nodes = []
    base = 8100 if pool == "a" else 8110
    for e in range(n_edges):
        nodes.append(dict(name=f"edge{e}", tier=0, loc="CBE", zone="IN-SO", cores=1, arch="x86",
                          url=f"http://127.0.0.1:{base + e}", speed={"generic": 0.3, "vision": 0.3},
                          idle_w=2.0, max_w=6.0, pue=1.0, mem_gb=2.0))
    for i in launched:
        lo, hi = POWER[i["arch"]]
        nodes.append(dict(name=i["name"], tier=i["tier"], loc=i["loc"], zone=i["zone"], cores=2, arch=i["arch"],
                          url=f"http://{i['ip']}:{PORT}", instance=i["id"], region=i["region"], type=i["type"],
                          speed={"generic": 1.0, "vision": 1.0} if i["arch"] == "x86" else {"generic": 0.85, "vision": 0.6},
                          idle_w=lo * 2, max_w=hi * 2, pue=1.135, mem_gb=2.0 if "small" in i["type"] else 4.0))
    cfg = dict(token=token, nodes=nodes,
               net={"CBE-BOM": [0.035, 20.0], "CBE-ARN": [0.16, 15.0], "BOM-ARN": [0.12, 200.0]},
               country={"CBE": "IN", "BOM": "IN", "ARN": "SE"})
    path = ROOT / ("nodes.json" if pool == "a" else f"nodes_{pool}.json")
    path.write_text(json.dumps(cfg, indent=1))
    print("wrote", path)


def status(_a) -> None:
    for region, *_r in SITES:
        ec2 = boto3.client("ec2", region_name=region)
        res = ec2.describe_instances(Filters=[{"Name": "tag:project", "Values": ["pace"]},
                                              {"Name": "instance-state-name", "Values": ["pending", "running", "stopped"]}])
        for r in res["Reservations"]:
            for i in r["Instances"]:
                name = next((t["Value"] for t in i.get("Tags", []) if t["Key"] == "Name"), "?")
                print(f"{region:12s} {name:14s} {i['InstanceType']:15s} {i['State']['Name']:8s} {i.get('PublicIpAddress', '-')}")
    for p in sorted(ROOT.glob("nodes*.json")):
        if p.name == "nodes.local.json":
            continue
        cfg = json.loads(p.read_text())
        print(p.name)
        hints = set()
        for n in cfg["nodes"]:
            try:
                req = urllib.request.Request(n["url"] + "/status", headers={"X-Token": cfg["token"]})
                print(f"  {n['name']:10s} OK  {urllib.request.urlopen(req, timeout=5).read().decode()[:90]}")
            except Exception as e:  # noqa: BLE001
                print(f"  {n['name']:10s} --  {str(e)[:70]}")
                msg, local = str(e).lower(), "127.0.0.1" in n["url"]
                if local:
                    hints.add("edge workers not running: start  python -m testbed.local --edges 2  in a second terminal")
                elif "timed out" in msg:
                    hints.add("timed out = AWS is dropping this laptop's current public IP: run  "
                              "python -m testbed.aws allow  (still timing out? use  allow --wide)")
                elif "refused" in msg:
                    hints.add("connection refused = instance is up but the worker is still installing: wait 1-2 min")
                elif "401" in msg:
                    hints.add("401 = token mismatch: restart  python -m testbed.local  after  aws up")
        for h in sorted(hints):
            print("  hint:", h)


def down(_a) -> None:
    for region, *_r in SITES:
        ec2 = boto3.client("ec2", region_name=region)
        res = ec2.describe_instances(Filters=[{"Name": "tag:project", "Values": ["pace"]},
                                              {"Name": "instance-state-name", "Values": ["pending", "running", "stopped", "stopping"]}])
        ids = [i["InstanceId"] for r in res["Reservations"] for i in r["Instances"]]
        if ids:
            ec2.terminate_instances(InstanceIds=ids)
            print(f"terminating {ids} in {region}")
            ec2.get_waiter("instance_terminated").wait(InstanceIds=ids)
        for sg in ec2.describe_security_groups(Filters=[{"Name": "group-name", "Values": ["pace-sg"]}])["SecurityGroups"]:
            for _ in range(10):
                try:
                    ec2.delete_security_group(GroupId=sg["GroupId"])
                    print("deleted", sg["GroupId"], "in", region)
                    break
                except ClientError:
                    time.sleep(5)
    print("all PACE resources removed")


def stop(_a) -> None:
    """Stop (not terminate) instances between sessions: no compute charge, IPs change on start."""
    for region, *_r in SITES:
        ec2 = boto3.client("ec2", region_name=region)
        res = ec2.describe_instances(Filters=[{"Name": "tag:project", "Values": ["pace"]},
                                              {"Name": "instance-state-name", "Values": ["running"]}])
        ids = [i["InstanceId"] for r in res["Reservations"] for i in r["Instances"]]
        if ids:
            ec2.stop_instances(InstanceIds=ids)
            print("stopped", ids)


def check(_a) -> None:
    """Verify credentials, permissions and Free-plan instance types without launching anything."""
    try:
        ident = boto3.client("sts").get_caller_identity()
    except (ClientError, NoCredentialsError) as e:
        raise SystemExit(f"AWS credentials not working ({e.__class__.__name__}: {e}).\n"
                         "Check C:\\Users\\<you>\\.aws\\credentials (no .txt ending, [default] header, "
                         "no spaces inside the keys) - see docs/RUNBOOK.md section 1.")
    print("credentials OK:", ident["Arn"])
    print("laptop public IP:", ", ".join(my_ips()))
    ok = True
    for region, *_r in SITES:
        ec2 = boto3.client("ec2", region_name=region)
        vpcs = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])["Vpcs"]
        print(f"{region}: default VPC {'OK' if vpcs else 'MISSING'}")
        ok &= bool(vpcs)
        for arch, types in TYPES.items():
            offered = {o["InstanceType"] for o in ec2.describe_instance_type_offerings(
                Filters=[{"Name": "instance-type", "Values": types}])["InstanceTypeOfferings"]}
            usable = [t for t in types if t in offered]
            print(f"  {arch}: {', '.join(usable) or 'none of ' + ', '.join(types)}")
            ok &= bool(usable)
        boto3.client("ssm", region_name=region).get_parameter(Name=AMI["x86"])
        print("  AMI lookup OK")
    print("\nAll checks passed. Next: python -m testbed.aws up" if ok else "\nSome checks failed; see above.")


def allow(a) -> None:
    """Re-authorise this laptop after its public IP changed (e.g. home -> college Wi-Fi)."""
    cidrs = laptop_cidrs(a.wide)
    for region, *_r in SITES:
        ensure_sg(boto3.client("ec2", region_name=region), cidrs)
    print("allowed", ", ".join(cidrs), "on port", PORT)


def start(a) -> None:
    """Start stopped instances and rewrite node URLs with their new public IPs."""
    cidrs = laptop_cidrs(a.wide)
    for p in sorted(ROOT.glob("nodes*.json")):
        if p.name == "nodes.local.json":
            continue
        cfg = json.loads(p.read_text())
        for region, *_r in SITES:
            ids = [n["instance"] for n in cfg["nodes"] if n.get("region") == region]
            if not ids:
                continue
            ec2 = boto3.client("ec2", region_name=region)
            ec2.start_instances(InstanceIds=ids)
            ec2.get_waiter("instance_running").wait(InstanceIds=ids)
            desc = {i["InstanceId"]: i for r in ec2.describe_instances(InstanceIds=ids)["Reservations"] for i in r["Instances"]}
            for n in cfg["nodes"]:
                if n.get("instance") in desc:
                    n["url"] = f"http://{desc[n['instance']]['PublicIpAddress']}:{PORT}"
            ensure_sg(ec2, [f"{d['PublicIpAddress']}/32" for d in desc.values()] + cidrs)
        p.write_text(json.dumps(cfg, indent=1))
        print("updated", p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["check", "up", "status", "down", "stop", "start", "allow"])
    ap.add_argument("--edges", type=int, default=2, help="edge workers on the laptop")
    ap.add_argument("--pool", default="a", help="second pool 'b' for a live side-by-side (A/B) demo")
    ap.add_argument("--wide", action="store_true",
                    help="allow the /24 of each laptop IP (networks that rotate public IPs; workers still need the token)")
    a = ap.parse_args()
    {"check": check, "up": up, "status": status, "down": down, "stop": stop, "start": start,
     "allow": allow}[a.cmd](a)


if __name__ == "__main__":
    main()
