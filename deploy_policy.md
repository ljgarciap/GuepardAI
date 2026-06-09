# Deploy Policy: AWS EC2 (t3.small) Deployment Guide

This document defines the requirements, optimizations, and step-by-step procedures to deploy the GuepardAI backend and frontend stacks to a cost-effective AWS EC2 `t3.small` instance.

---

## 1. Instance Sizing & Rationale

| Parameter | Specification | Rationale |
| :--- | :--- | :--- |
| **Instance Type** | `t3.small` | 2 vCPUs and 2.0 GiB RAM. Maximizes cost savings during staging/testing phases. |
| **Storage (EBS)** | 20 GB GP3 SSD | Space for OS, Docker images, and temporary PDF output storage. GP3 provides stable IOPS. |
| **Virtual Memory** | 4.0 GiB Swap Space | **Mandatory**. Prevents Out-Of-Memory (OOM) failures when Chromium instances run. |
| **Concurrency** | Autodetected (Default) | Defaults to 2 concurrent tasks (matching the 2 vCPUs of the t3.small). |

---

## 2. Ports & Firewall (AWS Security Group)

Ensure the EC2 Security Group permits the following inbound traffic:

- **SSH (Port `22`)**: Restricted to authorized Developer IPs.
- **HTTP (Port `80` / `4200`)**: Open to public/client traffic for the Angular Frontend.
- **API (Port `8000`)**: Optional (can be proxied via Nginx or exposed directly for API testing).

---

## 3. Step-by-Step Deployment Procedure

### Step 3.1: Provision the EC2 Instance
1. Launch an EC2 instance in the AWS Console.
2. Select **Ubuntu Server 22.04 LTS (HVM)**.
3. Choose the **t3.small** instance type.
4. Configure 20 GB of GP3 storage.
5. Apply the Security Group rules defined in Section 2.

### Step 3.2: Configure Swap Memory (4GB virtual RAM)
Once logged into the server via SSH:
```bash
# Create a 4GB swap space file
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Make swap persistent across reboots
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Verify memory allocation
free -h
```

### Step 3.3: Install System Dependencies
Install Docker Engine and Git:
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker ubuntu

# Apply user group changes without logging out
newgrp docker
```

### Step 3.4: Clone & Configure Env Files
1. Clone the repository to the EC2 target folder:
   ```bash
   git clone https://github.com/ljgarciap/GuepardAI.git
   cd GuepardAI
   ```
2. Set up the production variables in `.env`:
   ```bash
   cp .env.example .env
   nano .env
   ```
   *(Ensure API keys for OpenAI, Anthropic, Google, and Database configs are populated).*

### Step 3.5: Run the Services
Run the docker compose stack:
```bash
# Build and run containers in detached mode
docker compose up --build -d
```

### Step 3.6: Verify Services & Monitoring
Check logs to make sure databases initialized and celery worker connected:
```bash
# Check service status
docker compose ps

# Follow container logs
docker compose logs -f celery_worker
```

---

## 4. Monitoring & Justifying Server Upgrades

Since we are running with default concurrency on a 2GB RAM instance, parallel PDF generation tasks will trigger heavy Swap memory usage. Use the following metrics to demonstrate resource bottlenecks to stakeholders when requesting an upgrade to a `t3.medium` or `t3.large` instance:

### 4.1. Monitor Memory & Swap Usage
Run the following tool in a separate terminal during generation:
```bash
htop
# Or alternatively
watch -n 1 free -m
```
* **What to observe**: You will see physical memory hit 100% (~2000MB) and Swap usage climb to 1.5GB - 3GB when two PDF renders run simultaneously.
* **Bottleneck evidence**: Disk I/O (seen as %wa in `top` or high execution latency in Celery logs) will jump, indicating the SSD is acting as memory backup.

### 4.2. Latency Penalty Comparison
* **Single Task Duration**: ~10–15 seconds (primarily RAM-bound).
* **Two Concurrent Tasks (with default concurrency and Swap)**: ~35–50 seconds (due to SSD swap thrashing).
* **The Argument**: An upgrade to a `t3.medium` (4GB RAM) or `t3.large` (8GB RAM) will eliminate Swap dependency, improving parallel processing times by up to **300%** and ensuring the server never slows down under load.
