import os
import httpx
import shutil
import uvicorn
from datetime import datetime
from typing import Dict
from pathlib import Path
from uuid import uuid4
from fastapi import FastAPI, BackgroundTasks, HTTPException, File, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
# Import your custom modules
from models import FormData, TaskStatus# Assuming this contains FormData, TaskStatus models
from autofiller import FormAutofiller, logger
from utils import process_passport_mrz

# Configure logging


# Initialize FastAPI app
app = FastAPI(
    title="Form Autofiller & File Upload Service", 
    version="1.0.0",
    description="Combined service for form processing and file uploads"
)

# Global variables to track tasks
task_storage: Dict[str, TaskStatus] = {}

# Form processing configuration
FORM_URL = os.getenv("FORM_URL", "https://adventurescare.com/agent/orders-management")
LOGIN_URL = os.getenv("LOGIN_URL", "https://adventurescare.com/agent/login")

# File upload configuration
BASE_DIR = Path("static")
PHOTO_DIR = BASE_DIR / "photos"
PASSPORT_DIR = BASE_DIR / "passports"
PDF_DIR = BASE_DIR / "pdfs"

# Create directories
for directory in [PHOTO_DIR, PASSPORT_DIR, PDF_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Mount static folders
app.mount("/static", StaticFiles(directory="static"), name="static")


# === FORM PROCESSING ENDPOINTS ===

async def call_callback_api(callback_url: str, task_id: str, success: bool):
    """Call the callback API to update the processed status."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                callback_url,
                json={
                    "is_active": True,
                },
                timeout=30.0
            )
            response.raise_for_status()
            logger.info(f"Callback API called successfully for task {task_id}")
    except Exception as e:
        logger.error(f"Failed to call callback API for task {task_id}: {e}")


async def process_form_task(form_data: FormData):
    """Background task to process form submission."""
    task_id = form_data.id
    
    try:
        # Update task status to processing
        task_storage[task_id].status = "processing"
        task_storage[task_id].message = "Processing form submission..."
        
        # Initialize autofiller and process form
        autofiller = FormAutofiller(form_url=FORM_URL, login_url=LOGIN_URL)
        success = await autofiller.process_form(form_data)
        
        # Update task status
        if success:
            task_storage[task_id].status = "completed"
            task_storage[task_id].message = "Form processed successfully"
        else:
            task_storage[task_id].status = "failed"
            task_storage[task_id].message = "Form processing failed"
            
        task_storage[task_id].completed_at = datetime.now()
        
        # Call callback API if provided
        if form_data.callback_api_url:
            await call_callback_api(form_data.callback_api_url, task_id, success)
            
    except Exception as e:
        logger.error(f"Task {task_id} failed: {e}")
        task_storage[task_id].status = "failed"
        task_storage[task_id].message = f"Task failed: {str(e)}"
        task_storage[task_id].completed_at = datetime.now()
        
        # Call callback API even on failure
        if form_data.callback_api_url:
            await call_callback_api(form_data.callback_api_url, task_id, False)


@app.post("/submit-form", response_model=Dict[str, str])
async def submit_form(form_data: FormData, background_tasks: BackgroundTasks):
    """
    Submit a form for processing in the background.
    
    Returns a task ID that can be used to check the status.
    """
    task_id = form_data.id
    
    # Check if task already exists
    if task_id in task_storage:
        raise HTTPException(status_code=400, detail=f"Task with ID {task_id} already exists")
    
    # Create task status entry
    task_storage[task_id] = TaskStatus(
        task_id=task_id,
        status="queued",
        message="Task queued for processing",
        created_at=datetime.now()
    )
    
    # Add background task
    background_tasks.add_task(process_form_task, form_data)
    
    logger.info(f"Form submission queued with task ID: {task_id}")
    
    return {
        "task_id": task_id,
        "status": "queued",
        "message": "Form submission has been queued for processing"
    }


@app.get("/task-status/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """Get the status of a specific task."""
    if task_id not in task_storage:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    return task_storage[task_id]


@app.get("/tasks", response_model=Dict[str, TaskStatus])
async def get_all_tasks():
    """Get the status of all tasks."""
    return task_storage


@app.delete("/task/{task_id}")
async def delete_task(task_id: str):
    """Delete a completed or failed task from storage."""
    if task_id not in task_storage:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    task = task_storage[task_id]
    if task.status == "processing":
        raise HTTPException(status_code=400, detail="Cannot delete a task that is currently processing")
    
    del task_storage[task_id]
    return {"message": f"Task {task_id} deleted successfully"}


# === FILE UPLOAD ENDPOINTS ===

def save_upload_file(file: UploadFile, save_path: Path):
    """Helper function to save uploaded file."""
    with save_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)


@app.post("/upload-images/")
async def upload_images(
    profile_image: UploadFile = File(...),
    passport_image: UploadFile = File(...)
):
    """Upload profile and passport images, process passport MRZ data."""
    allowed_image_exts = {"png", "jpg", "jpeg", "gif", "bmp"}
    
    # Validate file extensions
    profile_ext = profile_image.filename.split(".")[-1].lower()
    passport_ext = passport_image.filename.split(".")[-1].lower()
    
    if profile_ext not in allowed_image_exts:
        raise HTTPException(status_code=400, detail=f"Unsupported profile image type: .{profile_ext}")
    if passport_ext not in allowed_image_exts:
        raise HTTPException(status_code=400, detail=f"Unsupported passport image type: .{passport_ext}")
    
    # Generate unique names using uuid4
    profile_unique_name = f"profile_{uuid4().hex}.{profile_ext}"
    passport_unique_name = f"passport_{uuid4().hex}.{passport_ext}"
    
    # Save profile image
    profile_path = PHOTO_DIR / profile_unique_name
    save_upload_file(profile_image, profile_path)
    profile_url = f"/static/photos/{profile_unique_name}"
    
    # Save passport image
    passport_path = PASSPORT_DIR / passport_unique_name
    save_upload_file(passport_image, passport_path)
    passport_url = f"/static/passports/{passport_unique_name}"
    
    # Verify passport file was saved
    if not passport_path.exists():
        raise HTTPException(status_code=500, detail="Passport image file was not saved.")
    
    # Process passport MRZ
    try:
        mrz = process_passport_mrz(str(passport_path))
        if "error" in mrz:
            raise HTTPException(status_code=400, detail=mrz["error"])
    except Exception as e:
        logger.error(f"Failed to process passport MRZ: {e}")
        raise HTTPException(status_code=500, detail="Failed to process passport MRZ data")
    
    return JSONResponse(content={
        "message": "Images uploaded successfully",
        "profile_image_url": profile_url,
        "passport_image_url": passport_url,
        "passport_data": mrz
    })


@app.post("/upload-pdf/")
async def upload_pdf(document: UploadFile = File(...)):
    """Upload PDF document."""
    if not document.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")
    
    # Generate unique name using uuid4
    pdf_unique_name = f"document_{uuid4().hex}.pdf"
    pdf_path = PDF_DIR / pdf_unique_name
    
    # Save PDF file
    save_upload_file(document, pdf_path)
    pdf_url = f"/static/pdfs/{pdf_unique_name}"
    
    return JSONResponse(content={
        "message": "PDF uploaded successfully",
        "document_url": pdf_url
    })


# === UTILITY ENDPOINTS ===

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "active_tasks": len([t for t in task_storage.values() if t.status == "processing"]),
        "total_tasks": len(task_storage),
        "static_dirs": {
            "photos": len(list(PHOTO_DIR.glob("*"))),
            "passports": len(list(PASSPORT_DIR.glob("*"))),
            "pdfs": len(list(PDF_DIR.glob("*")))
        }
    }


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Form Autofiller & File Upload Service",
        "version": "1.0.0",
        "endpoints": {
            "form_processing": [
                "/submit-form",
                "/task-status/{task_id}",
                "/tasks",
                "/task/{task_id}"
            ],
            "file_uploads": [
                "/upload-images/",
                "/upload-pdf/"
            ],
            "utility": [
                "/health",
                "/docs",
                "/static/{path}"
            ]
        }
    }


# === APPLICATION STARTUP ===

def main():
    """Run the application."""
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", 8000))
    
    logger.info(f"Starting combined FastAPI service on {HOST}:{PORT}")
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)


if __name__ == "__main__":
    main()