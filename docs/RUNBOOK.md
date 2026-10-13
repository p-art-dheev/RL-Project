# PACE runbook: laptop setup, AWS testbed, experiments, live demo

Commands are for **Windows 11 PowerShell** on the HP Victus. Linux and macOS are the same except for `.venv\Scripts\Activate.ps1`.
Budget: the whole plan uses **< $10** of the $100 Free-plan credit.

---

## 0. One-time laptop setup (10 min)

1. Install **Python 3.11 or 3.12** from python.org and tick "Add python.exe to PATH". Also install **Git**.
2. Clone the repository and install the dependencies:
   ```powershell
   git clone https://github.com/p-art-dheev/RL-Project.git
   cd RL-Project
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
   pip install -r requirements.txt
   ```
   The policy is about 60K parameters, so the CPU build of PyTorch is enough. The RTX 3050 is optional.
3. Sanity check (≈30 s, no AWS needed), from the `RL-Project` folder with the venv active:
   ```powershell
   python -m experiments.smoke
   ```
   It lists the installed packages, then simulates 10 minutes with CA-EFT, MERSEM and PACE + shield. It should end with `Setup OK`.

## 1. AWS access (≈15 min, once)

**a) Create a user for the scripts** (never use the root account's keys):
1. Sign in at https://console.aws.amazon.com with your account email. Open **IAM** (search bar → "IAM"); IAM is global, so the region doesn't matter.
2. **Users → Create user** → name `pace-cli` → leave "Provide user access to the AWS Management Console" **unticked** → Next.
3. **Attach policies directly** → search and tick **AmazonEC2FullAccess** and **AmazonSSMReadOnlyAccess** → Next → **Create user**.
4. Open `pace-cli` → **Security credentials** tab → **Create access key** → use case **Command Line Interface (CLI)** → tick the confirmation → Next → **Create access key**.
5. Copy the **Access key ID** and **Secret access key**, or click **Download .csv file**. The secret is shown only once. Never paste it into chat or commit it.

**b) Store the key on the laptop** (PowerShell, replace the two values):
```powershell
mkdir $HOME\.aws -Force
@"
[default]
aws_access_key_id = AKIA_REPLACE_ME
aws_secret_access_key = REPLACE_ME
"@ | Set-Content -Path $HOME\.aws\credentials -Encoding ascii
@"
[default]
region = ap-south-1
"@ | Set-Content -Path $HOME\.aws\config -Encoding ascii
```
The files must be named exactly `credentials` and `config`, with no `.txt` ending; this command takes care of that.

**c) Check it** (launches nothing, costs nothing):
```powershell
python -m testbed.aws check
```
It should show `credentials OK: arn:aws:iam::...:user/pace-cli`, a default VPC and usable instance types in **ap-south-1** and **eu-north-1**, and end with `All checks passed`.

**d) Budget alert** (2 min): console search bar → **Billing and Cost Management** → **Budgets** → **Create budget** → *Use a template* → **Monthly cost budget** → amount **$20** → your email → Create. Your remaining credit is under **Billing → Credits**. On the Free plan, running out of credit **closes the account**, so the alert protects the testbed. This project should use under $10.

## 2. Bring up the testbed (≈5 min)

```powershell
python -m testbed.aws up            # 2 workers in Mumbai (fog) + 2 in Stockholm (cloud): x86 + ARM each
# wait ~3 min for cloud-init to install the workers, then:
python -m testbed.aws status        # every node must say OK
```
In a **second terminal** (keep it open), start the two edge workers that emulate camera boxes:
```powershell
.\.venv\Scripts\Activate.ps1
python -m testbed.local --edges 2   # allow the Windows firewall prompt for private networks
```
Back in the first terminal, measure the real system (CPU speed per node, RTT and bandwidth Coimbatore↔Mumbai↔Stockholm):
```powershell
python -m testbed.calibrate         # writes the measurements into testbed/nodes.json
```
- **Changed Wi-Fi (e.g. home → college)?** Run `python -m testbed.aws allow` to re-authorise your new public IP.
- **Some AWS nodes say `timed out`, others `OK`?** Your network sends connections out through several public IPs (common on campus networks with two ISP links), and AWS drops the ones it doesn't know. Run `python -m testbed.aws allow`, which detects and authorises all of them. If nodes still time out, run `python -m testbed.aws allow --wide` to authorise each IP's /24 range. The workers still require the token.
- **`connection refused` on an AWS node** means its worker is still installing; wait 1–2 min. **On edge0/edge1** it means `testbed.local` isn't running.
- **College firewall trouble?** The AWS workers listen on port 80. If it still fails, use your phone's hotspot and run `allow` again.

## 3. Smoke test with the dashboard (3 min)

```powershell
python -m testbed.orchestrator --scheduler ca-eft --minutes 2
```
Open http://localhost:8080. You should see jobs completing, all nodes green, and the decisions table filling up.

## 4. Real-testbed experiment E8 (≈1.5 h unattended)

```powershell
python -m experiments.run_testbed --methods pace-shield,pace,mersem,ca-eft,eft --minutes 6 --seeds 3
```
- Runs are interleaved (A B C D E, A B C D E, …) on the same job and carbon trace per seed.
- Results go to `results/testbed/e8_*.json`, with a table in `results/testbed/E8_SUMMARY.md`.
- Keep the laptop plugged in and stop it from sleeping: Settings → Power → Screen and sleep → Never.
- Commit and push `results/testbed/` afterwards so it ends up in the report.

## 5. Live demo for the professor (≈10 min)

Open 3 terminals, each with `.\.venv\Scripts\Activate.ps1`:

```powershell
# T1: edge workers (camera boxes)
python -m testbed.local --edges 2
# T2: PACE (+ safety shield) with an SLA target of 5%, camera-driven alerts, dashboard on :8080
python -m testbed.orchestrator --scheduler pace-shield --target 0.05 --camera --minutes 15 --linger
# T3: laptop webcam as camera edge0
python -m testbed.camera --source 0 --camera edge0 --fps 2
```
To use the phone as a second camera, install an "IP Webcam" app and start the server, then run:
`python -m testbed.camera --source http://PHONE_IP:8080/video --camera edge1 --private`
The `--private` flag marks the feed as data-residency restricted, so it never leaves India.

**Optional side-by-side:** run a second pool with MERSEM in parallel.
```powershell
python -m testbed.aws up --pool b ; python -m testbed.local --edges 2 --pool b
python -m testbed.orchestrator --nodes testbed/nodes_b.json --scheduler mersem --camera --port 8081 --minutes 15 --linger
```
Then open `http://localhost:8080/?peer=http://localhost:8081`. Both schedulers appear in the KPI rows and charts.

**Demo script** (the buttons are on the dashboard):
1. **Topology.** Coimbatore edge, Mumbai fog (dirty grid, ~30 ms) and Stockholm cloud (clean grid, ~150 ms). Point at the g/kWh on every node card.
2. **Normal operation.** Alerts stay within 1 s. Batch and analytics work goes north to Stockholm. Private feeds stay in India (greyed candidates in the decisions table).
3. **Carbon spike ×4 on IN-WE (Mumbai).** Work shifts away from Mumbai within seconds.
4. **Rush hour ×3.** Watch the SLA chart: PACE protects alerts and defers batch work.
5. **Crash bom-x86.** The node turns red, its tasks are re-queued and re-placed, and the SLA dips briefly, then recovers.
6. **SLA target 0.05 → 0.01.** The w(SLA) badge rises and PACE spends more carbon to meet the tighter SLA, with no retraining.
7. Close with the plots in `results/plots/`: the Pareto front vs MERSEM, E1 bars with confidence intervals, and the E8 real-testbed table.

**Backup if the network fails:** run the whole testbed locally (no AWS) with
`python -m testbed.local --edges 2 --servers 4` and
`python -m testbed.orchestrator --nodes testbed/nodes.local.json --scheduler pace-shield`.
Network delays are not real in this mode, so say that if you use it.

## 6. Tear down (always!)

```powershell
python -m testbed.aws stop     # between sessions: no compute charge (small EBS charge remains)
python -m testbed.aws start    # next day: restarts the instances and rewrites the new IPs
python -m testbed.aws down     # when finished: terminates everything and deletes the security groups
```

## 7. Reproduce the simulation results (no AWS)

```powershell
python -m pace.rl.train --minutes 45 --workers 6        # optional: re-train (≈45 min on the i5)
python -m experiments.run_sim --exp all --seeds 10 --procs 6
python -m experiments.plots                             # results/plots/*.png and results/RESULTS.md
```
With real carbon data (Electricity Maps CSVs in `data/carbon/`), add `--carbon data/carbon@2024` to `run_sim`.
