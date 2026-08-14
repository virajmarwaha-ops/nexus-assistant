# NEXUS Autonomous AI Desktop Assistant

NEXUS is a modular, stateful AI desktop assistant supporting natural language
voice pipelines, multi-agent orchestration, computer vision, file management,
and OS automation.

## Quickstart

1. Run the backend:

   ```bash
   python -m venv venv
   source venv/bin/activate  # Or venv\Scripts\activate on Windows
   pip install -r backend/requirements.txt
   uvicorn backend.app.main:app --reload --port 8000
   ```

2. Run the frontend:

   ```bash
   cd frontend
   npm install
   npm start
   ```
