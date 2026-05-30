# To-Do App

A Flask + SQLAlchemy task management app with priorities, due dates, tags, search, and sort. Built for easy migration to AWS RDS and S3.

---

## Table of Contents

- [Features](#features)
- [Project Structure](#project-structure)
- [Local Setup](#local-setup)
- [Environment Variables](#environment-variables)
- [Docker](#docker)
- [CI/CD Pipeline](#cicd-pipeline)
- [AWS Infrastructure](#aws-infrastructure)
- [Database Migration (SQLite → RDS)](#database-migration-sqlite--rds)
- [S3 File Attachments (Phase 3)](#s3-file-attachments-phase-3)
- [Secrets Reference](#secrets-reference)

---

## Features

- Add tasks with **priority** (High / Medium / Low)
- **Due dates** with automatic overdue detection
- **Color-coded tags** — create, filter, and manage
- **Search** tasks by keyword
- **Sort** by newest, priority, due date, or A→Z
- **Edit** any existing task
- **Filter** by All / Active / Done
- Live stats bar showing active count and overdue alerts
- SQLite locally, RDS-ready via a single env var swap

---

## Project Structure

```
todo-app/
├── app.py                  # Flask app — routes, models, DB config
├── requirements.txt        # Python dependencies
├── Dockerfile              # Multi-stage Docker build
├── .dockerignore           # Files excluded from Docker image
├── .github/
│   └── workflows/
│       └── deploy.yml      # CI/CD: test → build → push ECR → deploy EC2
└── templates/
    ├── index.html          # Main task list (Jinja2)
    └── edit.html           # Edit task form
```

---

## Local Setup

### Prerequisites

- Python 3.11+
- pip

### Steps

```bash
# 1. Clone the repo
git clone https://github.com/highfelabs/to-do_app_Deployment.git
cd todo-app

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the app
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

SQLite database is created automatically at `instance/todos.db` on first run.

---

## Environment Variables

| Variable       | Default                    | Description                              |
|----------------|----------------------------|------------------------------------------|
| `DATABASE_URL` | `sqlite:////app/data/todos.db` | Database connection string           |
| `SECRET_KEY`   | `dev-secret-key`           | Flask session secret — **change in prod** |

Set variables in a `.env` file (never commit this):

```bash
# .env
SECRET_KEY=your-secure-random-string
DATABASE_URL=sqlite:////app/data/todos.db
```

Load it with `python-dotenv` (uncomment in `requirements.txt`) or export manually:

```bash
export SECRET_KEY=your-secure-random-string
export DATABASE_URL=sqlite:////app/data/todos.db
```

---

## Docker

### Build and run locally

```bash
# Build
docker build -t todo-app .

# Run (mounts a volume so SQLite data persists)
docker run -d \
  --name todo-app \
  -p 5000:5000 \
  -v todo-app-data:/app/data \
  -e SECRET_KEY=your-secret \
  todo-app
```

Open [http://localhost:5000](http://localhost:5000).

### Dockerfile highlights

The Dockerfile uses a **multi-stage build** to keep the final image lean:

```
Stage 1 (builder)  →  installs all pip packages into /install
Stage 2 (runtime)  →  copies only the installed packages + app code
```

Additional hardening:
- Runs as a non-root `appuser`
- Persistent data written to `/app/data` (mount a volume here)
- Health check pings `/` every 10 seconds via `curl`

---

## CI/CD Pipeline

The GitHub Actions workflow (`.github/workflows/deploy.yml`) runs on every push to `main` with three sequential jobs:

```
push to main
    │
    ▼
┌─────────┐     ┌────────────────────────┐     ┌──────────────────────┐
│  test   │────▶│        docker          │────▶│        deploy        │
│         │     │                        │     │                      │
│ Install │     │ Build image            │     │ SSH into EC2 via SSM │
│ deps    │     │ Tag with ${{ github.sha }}            │     │ Pull image from ECR  │
│ (pytest)│     │ Push to ECR            │     │ Stop old container   │
└─────────┘     └────────────────────────┘     │ Start new container  │
                                               └──────────────────────┘
```

### Job breakdown

**`test`**
- Checks out code
- Sets up Python 3.11
- Installs `requirements.txt`
- *(pytest step is commented out — uncomment once tests are written)*

**`docker`**
- Authenticates to AWS ECR using GitHub secrets
- Builds the Docker image
- Tags it as `704225640883.dkr.ecr.us-east-1.amazonaws.com/to-do_app:${{ github.sha }}`
- Pushes to ECR

**`deploy`**
- Uses AWS SSM `send-command` to run shell commands on EC2 — **no SSH key required**
- On the EC2 instance:
  1. Logs into ECR
  2. Pulls the new image
  3. Stops and removes the old container
  4. Starts a fresh container with a persistent data volume

### Enabling dynamic image tags

The workflow currently hardcodes `IMAGE_TAG: ${{ github.sha }}`. To tag by Git SHA for traceability:

```yaml
env:
  IMAGE_TAG: ${{ github.sha }}
```

Update the deploy job's pull/run commands to match:

```bash
docker pull $ECR_REGISTRY/$ECR_REPOSITORY:${{ github.sha }}
docker run -d --name myapp -p 5000:5000 \
  -v myapp-data:/app/data \
  $ECR_REGISTRY/$ECR_REPOSITORY:${{ github.sha }}
```

---

## AWS Infrastructure

```
Internet
    │
    ▼
EC2 Instance (port 5000)
    │
    ├── Docker container: todo-app
    │       └── /app/data  ←──── Docker volume: myapp-data (SQLite)
    │
    ├── ECR: 704225640883.dkr.ecr.us-east-1.amazonaws.com/to-do_app
    │
    └── SSM Agent (used by CI/CD for deployments — no bastion needed)
```

### EC2 requirements

- Instance ID: `i-07b8b37802d0680e6`
- IAM role must allow:
  - `ssm:SendCommand` (for CI/CD deployments)
  - `ecr:GetAuthorizationToken`, `ecr:BatchGetImage`, `ecr:GetDownloadUrlForLayer` (to pull images)
- Docker installed on the instance
- SSM Agent running (`sudo systemctl status amazon-ssm-agent`)

### ECR repository

The container registry is:
```
704225640883.dkr.ecr.us-east-1.amazonaws.com/to-do_app
```

Images are tagged with `${{ github.sha }}` (or Git SHA if you adopt dynamic tagging).

---

## Database Migration (SQLite → RDS)

When you're ready to scale beyond a single container, swap in RDS PostgreSQL. SQLAlchemy abstracts the difference — only the connection string changes.

### Step 1 — Provision RDS

In the AWS Console or via Terraform, create a PostgreSQL RDS instance. Note the endpoint, port, username, password, and database name.

### Step 2 — Update requirements

Uncomment in `requirements.txt`:

```
psycopg2-binary>=2.9
```

### Step 3 — Set the env var

In GitHub Secrets and on your EC2 instance:

```bash
DATABASE_URL=postgresql://username:password@your-rds-endpoint.rds.amazonaws.com:5432/todos
```

### Step 4 — Update the Docker run command

Pass the env var at runtime:

```bash
docker run -d --name myapp -p 5000:5000 \
  -e DATABASE_URL="postgresql://..." \
  -e SECRET_KEY="your-secret" \
  $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG
```

No code changes required — SQLAlchemy creates all tables automatically on first boot via `db.create_all()`.

### Updated architecture with RDS

```
EC2 Instance
    └── Docker container: todo-app
            │
            └── RDS PostgreSQL  ←── task data (persistent, multi-AZ capable)
```

---

## S3 File Attachments (Phase 3)

To allow file attachments on tasks, add S3 storage.

### Step 1 — Install boto3

```
boto3>=1.34
```

### Step 2 — Add attachment model

```python
class Attachment(db.Model):
    id       = db.Column(db.Integer, primary_key=True)
    task_id  = db.Column(db.Integer, db.ForeignKey("task.id"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    s3_key   = db.Column(db.String(500), nullable=False)
```

### Step 3 — Upload and retrieve

```python
import boto3

s3 = boto3.client("s3")
BUCKET = os.environ.get("S3_BUCKET_NAME")

# Upload
s3.upload_fileobj(file_obj, BUCKET, f"attachments/{task_id}/{filename}")

# Pre-signed download URL (expires in 1 hour)
url = s3.generate_presigned_url(
    "get_object",
    Params={"Bucket": BUCKET, "Key": s3_key},
    ExpiresIn=3600
)
```

### Environment variables to add

| Variable        | Description                    |
|-----------------|--------------------------------|
| `S3_BUCKET_NAME`| Name of your S3 bucket         |
| `AWS_ACCESS_KEY_ID` | AWS credentials (or use IAM role on EC2) |
| `AWS_SECRET_ACCESS_KEY` | AWS credentials          |

### Updated architecture with RDS + S3

```
EC2 Instance
    └── Docker container: todo-app
            ├── RDS PostgreSQL  ←── task data
            └── S3 Bucket       ←── file attachments
```

---

## Secrets Reference

Add these in **GitHub → Settings → Secrets and Variables → Actions**:

| Secret                  | Description                                      |
|-------------------------|--------------------------------------------------|
| `AWS_ACCESS_KEY_ID`     | IAM user access key for ECR push + SSM deploy    |
| `AWS_SECRET_ACCESS_KEY` | IAM user secret key                              |
| `AWS_REGION`            | e.g. `us-east-1`                                 |
| `SECRET_KEY`            | Flask secret key for sessions                    |
| `DATABASE_URL`          | RDS connection string (when migrating from SQLite)|
| `S3_BUCKET_NAME`        | S3 bucket name (Phase 3)                         |

> **Never commit secrets to the repository.** Use GitHub Secrets for CI/CD and pass them as environment variables to the Docker container at runtime.