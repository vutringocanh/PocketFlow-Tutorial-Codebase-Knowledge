from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
import subprocess
import os
import uuid
import asyncio
from typing import List, Optional, Dict, Any

app = FastAPI(
    title="My PocketFlow Tutorial Generator",
    description="Generate AI-powered tutorials from GitHub repositories",
    version="1.0.0"
)

class RepositoryRequest(BaseModel):
    repo_url: str
    language: str = "english"
    include_patterns: List[str] = ["*.py", "*.js"]
    exclude_patterns: List[str] = ["tests/*"]
    max_size: int = 100000

class TutorialResponse(BaseModel):
    task_id: str
    status: str
    message: str

class StatusResponse(BaseModel):
    task_id: str
    status: str
    result: Optional[Dict[str, Any]] = None  # FIX: Make result optional
    error: Optional[str] = None

# In-memory task storage (production should use Redis/Database)
tasks = {}

@app.get("/")
async def root():
    return {
        "message": "PocketFlow Tutorial Generator API",
        "version": "1.0.0",
        "endpoints": {
            "generate": "/generate-tutorial",
            "status": "/status/{task_id}",
            "health": "/health",
            "docs": "/docs"
        }
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy", 
        "service": "PocketFlow Tutorial Generator",
        "active_tasks": len([t for t in tasks.values() if t.get("status") == "processing"])
    }

@app.post("/generate-tutorial", response_model=TutorialResponse)
async def generate_tutorial(request: RepositoryRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    tasks[task_id] = {"status": "processing", "result": None, "error": None}
    
    # Run PocketFlow in background
    background_tasks.add_task(run_pocketflow, task_id, request)
    
    return TutorialResponse(
        task_id=task_id,
        status="processing",
        message="Tutorial generation started. Use /status/{task_id} to check progress."
    )

@app.get("/status/{task_id}", response_model=StatusResponse)
async def get_status(task_id: str):
    if task_id not in tasks:
        return StatusResponse(
            task_id=task_id,
            status="not_found",
            result=None,  # Explicitly set to None
            error="Task not found"
        )
    
    task_data = tasks[task_id]
    return StatusResponse(
        task_id=task_id,
        status=task_data.get("status", "unknown"),
        result=task_data.get("result"),  # This can be None
        error=task_data.get("error")
    )

@app.get("/tasks")
async def list_tasks():
    """List all tasks and their status"""
    return {
        "total_tasks": len(tasks),
        "tasks": [
            {
                "task_id": task_id,
                "status": task_data.get("status", "unknown"),
                "has_result": task_data.get("result") is not None
            }
            for task_id, task_data in tasks.items()
        ]
    }

def run_pocketflow(task_id: str, request: RepositoryRequest):
    try:
        output_dir = f"./output/{task_id}"
        
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
        
        # Build command
        cmd = [
            "python", "main.py",
            "--repo", request.repo_url,
            "--output", output_dir,
            "--language", request.language,
            "--max-size", str(request.max_size)
        ]
        
        # Add include patterns
        for pattern in request.include_patterns:
            cmd.extend(["--include", pattern])
            
        # Add exclude patterns  
        for pattern in request.exclude_patterns:
            cmd.extend(["--exclude", pattern])
        
        # Update task status
        if task_id in tasks:
            tasks[task_id]["status"] = "running"
        
        # Run the command
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)  # 5 min timeout
        
        if result.returncode == 0:
            tasks[task_id] = {
                "status": "completed",
                "result": {
                    "output_path": output_dir,
                    "message": "Tutorial generated successfully",
                    "stdout": result.stdout[-500:] if result.stdout else "",  # Last 500 chars
                    "repo_url": request.repo_url,
                    "language": request.language
                },
                "error": None
            }
        else:
            tasks[task_id] = {
                "status": "failed",
                "result": None,
                "error": f"Command failed with return code {result.returncode}: {result.stderr}"
            }
            
    except subprocess.TimeoutExpired:
        if task_id in tasks:
            tasks[task_id] = {
                "status": "failed",
                "result": None,
                "error": "Task timed out after 5 minutes"
            }
    except Exception as e:
        if task_id in tasks:
            tasks[task_id] = {
                "status": "failed",
                "result": None,
                "error": f"Unexpected error: {str(e)}"
            }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)