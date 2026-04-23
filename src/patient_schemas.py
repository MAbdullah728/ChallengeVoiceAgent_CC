import re
from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from patient_constants import US_STATES

NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z' -]{0,49}$")
ZIP_PATTERN = re.compile(r"^\d{5}(-\d{4})?$")


def _normalize_us_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) != 10:
        raise ValueError("phone number must contain exactly 10 digits")
    return digits


def normalize_us_phone(value: str) -> str:
    return _normalize_us_phone(value)


class PatientBase(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=50)
    last_name: str | None = Field(default=None, min_length=1, max_length=50)
    date_of_birth: date | None = None
    sex: Literal["Male", "Female", "Other", "Decline to Answer"] | None = None
    phone_number: str | None = None
    email: EmailStr | None = None
    address_line_1: str | None = Field(default=None, min_length=1, max_length=255)
    address_line_2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    state: str | None = None
    zip_code: str | None = None
    insurance_provider: str | None = Field(default=None, max_length=255)
    insurance_member_id: str | None = Field(default=None, max_length=64)
    preferred_language: str | None = Field(default="English", max_length=100)
    emergency_contact_name: str | None = Field(default=None, max_length=255)
    emergency_contact_phone: str | None = None

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def parse_dob(cls, value):
        if value is None or isinstance(value, date):
            return value
        if isinstance(value, str):
            candidate = value.strip()
            for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
                try:
                    return datetime.strptime(candidate, fmt).date()
                except ValueError:
                    continue
            raise ValueError("date_of_birth must be YYYY-MM-DD or MM/DD/YYYY")
        return value

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        candidate = value.strip()
        if not NAME_PATTERN.fullmatch(candidate):
            raise ValueError(
                "must start with a letter and contain only letters, spaces, hyphens, or apostrophes"
            )
        return candidate

    @field_validator("date_of_birth")
    @classmethod
    def validate_dob(cls, value: date | None) -> date | None:
        if value is None:
            return value
        if value > datetime.now(tz=timezone.utc).date():
            raise ValueError("date_of_birth cannot be in the future")
        return value

    @field_validator("phone_number", "emergency_contact_phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _normalize_us_phone(value)

    @field_validator("state")
    @classmethod
    def validate_state(cls, value: str | None) -> str | None:
        if value is None:
            return value
        state = value.strip().upper()
        if state not in US_STATES:
            raise ValueError("must be a valid 2-letter U.S. state abbreviation")
        return state

    @field_validator("zip_code")
    @classmethod
    def validate_zip_code(cls, value: str | None) -> str | None:
        if value is None:
            return value
        zip_code = value.strip()
        if not ZIP_PATTERN.fullmatch(zip_code):
            raise ValueError("must be a valid U.S. ZIP code (12345 or 12345-6789)")
        return zip_code


class PatientCreate(PatientBase):
    first_name: str = Field(min_length=1, max_length=50)
    last_name: str = Field(min_length=1, max_length=50)
    date_of_birth: date
    sex: Literal["Male", "Female", "Other", "Decline to Answer"]
    phone_number: str
    address_line_1: str = Field(min_length=1, max_length=255)
    city: str = Field(min_length=1, max_length=100)
    state: str
    zip_code: str


class PatientUpdate(PatientBase):
    pass


class PatientRead(PatientBase):
    model_config = ConfigDict(from_attributes=True)

    patient_id: str
    first_name: str
    last_name: str
    date_of_birth: date
    sex: Literal["Male", "Female", "Other", "Decline to Answer"]
    phone_number: str
    address_line_1: str
    city: str
    state: str
    zip_code: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
