# Guepard AI - Strategic Synthesis Platform

Deployment structure for Guepard AI.

## Architecture
- **Backend**: FastAPI (Python 3.12)
- **Frontend**: Angular (Nginx)
- **Persistence**: Local Docker Volumes for Brand DNA and Knowledge Banks.

## Deployment Steps

1. **Configure Environment**:
   Copy `.env.example` to `.env` and fill in your API keys.
   ```bash
   cp .env.example .env
   ```

2. **Build and Run**:
   ```bash
   docker-compose up --build -d
   ```

3. **Access**:
   - Frontend: `http://localhost`
   - Backend API: `http://localhost:8000`

## Directory Mapping
- `/backend/uploads`: Stores corporate manuals and brand documents.
- `/backend/data`: Stores vectorized knowledge and brand profiles.
