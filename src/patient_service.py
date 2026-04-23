from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from patient_models import Patient
from patient_schemas import PatientCreate, PatientUpdate


def list_patients(
    db: Session,
    *,
    last_name: str | None = None,
    date_of_birth: date | None = None,
    phone_number: str | None = None,
) -> list[Patient]:
    query = select(Patient).where(Patient.deleted_at.is_(None))
    if last_name:
        query = query.where(Patient.last_name == last_name)
    if date_of_birth:
        query = query.where(Patient.date_of_birth == date_of_birth)
    if phone_number:
        query = query.where(Patient.phone_number == phone_number)
    return list(db.scalars(query.order_by(Patient.created_at.desc())).all())


def get_patient(db: Session, patient_id: str) -> Patient | None:
    query = select(Patient).where(
        Patient.patient_id == patient_id,
        Patient.deleted_at.is_(None),
    )
    return db.scalar(query)


def get_patient_by_phone(db: Session, phone_number: str) -> Patient | None:
    query = select(Patient).where(
        Patient.phone_number == phone_number,
        Patient.deleted_at.is_(None),
    )
    return db.scalar(query.order_by(Patient.created_at.desc()))


def create_patient(db: Session, payload: PatientCreate) -> Patient:
    patient = Patient(**payload.model_dump())
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


def update_patient(db: Session, patient: Patient, payload: PatientUpdate) -> Patient:
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(patient, key, value)
    patient.updated_at = datetime.now(tz=timezone.utc)
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


def soft_delete_patient(db: Session, patient: Patient) -> Patient:
    patient.deleted_at = datetime.now(tz=timezone.utc)
    patient.updated_at = patient.deleted_at
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient
