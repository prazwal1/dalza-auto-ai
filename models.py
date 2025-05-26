from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator

# Pydantic models for request validation
class FormData(BaseModel):
    id: str  # Unique identifier for the form submission
    nationality: str
    travel_from: str
    package_id: str
    start_date: str  # Format: YYYY-MM-DD
    end_date: str    # Format: YYYY-MM-DD
    surname: str
    given_name: str
    phone_number: str
    email: EmailStr
    dob: str  # Format: YYYY-MM-DD
    address: str
    emergency_contact: str
    passport_no: str
    profile_image_path: Optional[str] = None
    passport_image_path: Optional[str] = None
    callback_api_url: Optional[str] = None  # API endpoint to call after processing
    
    @field_validator('start_date', 'end_date', 'dob')
    def validate_date_format(cls, v):
        try:
            datetime.strptime(v, '%Y-%m-%d')
            return v
        except ValueError:
            raise ValueError('Date must be in YYYY-MM-DD format')

class TaskStatus(BaseModel):
    task_id: str
    status: str
    message: str
    created_at: datetime
    completed_at: Optional[datetime] = None
