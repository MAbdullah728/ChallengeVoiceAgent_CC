from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database import get_db, init_db
from patient_schemas import PatientCreate, PatientRead, PatientUpdate
from patient_service import (
    create_patient,
    get_patient,
    list_patients,
    soft_delete_patient,
    update_patient,
)

init_db()

app = FastAPI(title="Patient Intake API", version="1.0.0")


def ok(data):
    return {"data": data, "error": None}


def fail(message: str, *, code: str) -> dict:
    return {"data": None, "error": {"code": code, "message": message}}


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    if isinstance(exc.detail, dict) and "code" in exc.detail and "message" in exc.detail:
        payload = {"data": None, "error": exc.detail}
    else:
        payload = fail(str(exc.detail), code="http_error")
    return JSONResponse(status_code=exc.status_code, content=payload)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "data": None,
            "error": {
                "code": "validation_error",
                "message": "Input validation failed",
                "details": jsonable_encoder(exc.errors()),
            },
        },
    )


@app.get("/health")
def healthcheck():
    return ok({"status": "ok"})


@app.get("/patients")
def get_patients(
    last_name: str | None = Query(default=None),
    date_of_birth: date | None = Query(default=None),  # noqa: B008
    phone_number: str | None = Query(default=None),
    db: Session = Depends(get_db),  # noqa: B008
):
    patients = list_patients(
        db,
        last_name=last_name,
        date_of_birth=date_of_birth,
        phone_number=phone_number,
    )
    return ok([PatientRead.model_validate(p).model_dump(mode="json") for p in patients])


@app.get("/patients/{patient_id}")
def get_patient_by_id(patient_id: str, db: Session = Depends(get_db)):  # noqa: B008
    patient = get_patient(db, patient_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Patient not found"},
        )
    return ok(PatientRead.model_validate(patient).model_dump(mode="json"))


@app.post("/patients", status_code=status.HTTP_201_CREATED)
def post_patient(payload: PatientCreate, db: Session = Depends(get_db)):  # noqa: B008
    patient = create_patient(db, payload)
    return ok(PatientRead.model_validate(patient).model_dump(mode="json"))


@app.put("/patients/{patient_id}")
def put_patient(
    patient_id: str,
    payload: PatientUpdate,
    db: Session = Depends(get_db),  # noqa: B008
):
    patient = get_patient(db, patient_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Patient not found"},
        )
    updated = update_patient(db, patient, payload)
    return ok(PatientRead.model_validate(updated).model_dump(mode="json"))


@app.delete("/patients/{patient_id}")
def delete_patient(patient_id: str, db: Session = Depends(get_db)):  # noqa: B008
    patient = get_patient(db, patient_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Patient not found"},
        )
    deleted = soft_delete_patient(db, patient)
    return ok(PatientRead.model_validate(deleted).model_dump(mode="json"))
