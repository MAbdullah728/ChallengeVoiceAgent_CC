import logging

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    RunContext,
    cli,
    function_tool,
    inference,
    room_io,
)
from livekit.plugins import ai_coustics, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel
from sqlalchemy.orm import Session

from database import SessionLocal, init_db
from patient_schemas import PatientCreate, PatientUpdate, normalize_us_phone
from patient_service import (
    create_patient,
    get_patient,
    get_patient_by_phone,
    update_patient,
)

logger = logging.getLogger("agent")

load_dotenv(".env.local")

# UNVERIFIED: Please check docs.livekit.io for current API signatures/options.
AGENT_MODEL = "openai/gpt-5.3-chat-latest"


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""
You are a voice patient intake coordinator for a U.S. healthcare workflow.
Speak naturally, warmly, and briefly. The user is on a phone call.

Your job is to register or update a patient by collecting demographics conversationally.

Required fields:
- first_name, last_name
- date_of_birth (MM/DD/YYYY, not future)
- sex (Male, Female, Other, Decline to Answer)
- phone_number (U.S. 10 digits)
- address_line_1, city, state (2-letter U.S. abbreviation), zip_code

Optional fields:
- email, address_line_2, insurance_provider, insurance_member_id,
  preferred_language, emergency_contact_name, emergency_contact_phone

Conversation policy:
1) Greet and explain you will collect demographics.
2) Ask one thing at a time and adapt to natural phrasing.
3) If input is invalid, explain why and reprompt only that field.
4) As soon as phone number is captured, call check_existing_patient(phone_number).
   - If found, ask if caller wants to update existing record.
5) After required fields are collected, offer optional groups:
   "I can also collect your insurance information, emergency contact, and preferred language.
   Would you like to provide any of those?"
6) Before saving, read back all collected fields and ask for explicit confirmation.
7) If confirmed:
   - create_patient_record for new patients
   - update_patient_record for updates
8) Share success outcome and end gracefully.

Never fabricate tool results. Only claim save/update succeeded if the tool confirms it.
            """.strip(),
        )
        init_db()

    @staticmethod
    def _db() -> Session:
        return SessionLocal()

    @function_tool
    async def check_existing_patient(self, context: RunContext, phone_number: str) -> dict:
        """Check if an active patient exists for the provided U.S. phone number."""
        try:
            normalized = normalize_us_phone(phone_number)
            with self._db() as db:
                patient = get_patient_by_phone(db, normalized)
            if not patient:
                return {"found": False}
            return {
                "found": True,
                "patient_id": patient.patient_id,
                "first_name": patient.first_name,
                "last_name": patient.last_name,
            }
        except Exception as exc:
            logger.exception("Failed to check existing patient")
            return {"found": False, "error": str(exc)}

    @function_tool
    async def create_patient_record(
        self,
        context: RunContext,
        first_name: str,
        last_name: str,
        date_of_birth: str,
        sex: str,
        phone_number: str,
        address_line_1: str,
        city: str,
        state: str,
        zip_code: str,
        email: str | None = None,
        address_line_2: str | None = None,
        insurance_provider: str | None = None,
        insurance_member_id: str | None = None,
        preferred_language: str | None = "English",
        emergency_contact_name: str | None = None,
        emergency_contact_phone: str | None = None,
    ) -> dict:
        """Create a new patient after caller confirmation."""
        payload = PatientCreate(
            first_name=first_name,
            last_name=last_name,
            date_of_birth=date_of_birth,
            sex=sex,
            phone_number=phone_number,
            address_line_1=address_line_1,
            address_line_2=address_line_2,
            city=city,
            state=state,
            zip_code=zip_code,
            email=email,
            insurance_provider=insurance_provider,
            insurance_member_id=insurance_member_id,
            preferred_language=preferred_language,
            emergency_contact_name=emergency_contact_name,
            emergency_contact_phone=emergency_contact_phone,
        )
        try:
            with self._db() as db:
                patient = create_patient(db, payload)
            return {
                "success": True,
                "patient_id": patient.patient_id,
                "first_name": patient.first_name,
                "last_name": patient.last_name,
            }
        except Exception as exc:
            logger.exception("Failed to create patient")
            return {"success": False, "error": str(exc)}

    @function_tool
    async def update_patient_record(
        self,
        context: RunContext,
        patient_id: str,
        first_name: str | None = None,
        last_name: str | None = None,
        date_of_birth: str | None = None,
        sex: str | None = None,
        phone_number: str | None = None,
        address_line_1: str | None = None,
        city: str | None = None,
        state: str | None = None,
        zip_code: str | None = None,
        email: str | None = None,
        address_line_2: str | None = None,
        insurance_provider: str | None = None,
        insurance_member_id: str | None = None,
        preferred_language: str | None = None,
        emergency_contact_name: str | None = None,
        emergency_contact_phone: str | None = None,
    ) -> dict:
        """Update an existing patient after caller confirmation."""
        try:
            payload = PatientUpdate(
                first_name=first_name,
                last_name=last_name,
                date_of_birth=date_of_birth,
                sex=sex,
                phone_number=phone_number,
                address_line_1=address_line_1,
                address_line_2=address_line_2,
                city=city,
                state=state,
                zip_code=zip_code,
                email=email,
                insurance_provider=insurance_provider,
                insurance_member_id=insurance_member_id,
                preferred_language=preferred_language,
                emergency_contact_name=emergency_contact_name,
                emergency_contact_phone=emergency_contact_phone,
            )
            with self._db() as db:
                patient = get_patient(db, patient_id)
                if not patient:
                    return {"success": False, "error": "Patient not found"}
                updated = update_patient(db, patient, payload)
            return {
                "success": True,
                "patient_id": updated.patient_id,
                "first_name": updated.first_name,
                "last_name": updated.last_name,
            }
        except Exception as exc:
            logger.exception("Failed to update patient")
            return {"success": False, "error": str(exc)}


server = AgentServer()


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session(agent_name="my-agent")
async def my_agent(ctx: JobContext):
    # Logging setup
    # Add any other context you want in all log entries here
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    # Set up a voice AI pipeline using OpenAI, Cartesia, Deepgram, and the LiveKit turn detector
    session = AgentSession(
        # Speech-to-text (STT) is your agent's ears, turning the user's speech into text that the LLM can understand
        # See all available models at https://docs.livekit.io/agents/models/stt/
        stt=inference.STT(model="deepgram/nova-3", language="multi"),
        # A Large Language Model (LLM) is your agent's brain, processing user input and generating a response
        # See all available models at https://docs.livekit.io/agents/models/llm/
        llm=inference.LLM(model=AGENT_MODEL),
        # Text-to-speech (TTS) is your agent's voice, turning the LLM's text into speech that the user can hear
        # See all available models as well as voice selections at https://docs.livekit.io/agents/models/tts/
        tts=inference.TTS(
            model="cartesia/sonic-3", voice="9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"
        ),
        # VAD and turn detection are used to determine when the user is speaking and when the agent should respond
        # See more at https://docs.livekit.io/agents/build/turns
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        # allow the LLM to generate a response while waiting for the end of turn
        # See more at https://docs.livekit.io/agents/build/audio/#preemptive-generation
        preemptive_generation=True,
    )

    # To use a realtime model instead of a voice pipeline, use the following session setup instead.
    # (Note: This is for the OpenAI Realtime API. For other providers, see https://docs.livekit.io/agents/models/realtime/))
    # 1. Install livekit-agents[openai]
    # 2. Set OPENAI_API_KEY in .env.local
    # 3. Add `from livekit.plugins import openai` to the top of this file
    # 4. Use the following session setup instead of the version above
    # session = AgentSession(
    #     llm=openai.realtime.RealtimeModel(voice="marin")
    # )

    # # Add a virtual avatar to the session, if desired
    # # For other providers, see https://docs.livekit.io/agents/models/avatar/
    # avatar = hedra.AvatarSession(
    #   avatar_id="...",  # See https://docs.livekit.io/agents/models/avatar/plugins/hedra
    # )
    # # Start the avatar and wait for it to join
    # await avatar.start(session, room=ctx.room)

    await ctx.connect()

    # Start the session, which initializes the voice pipeline and warms up the models.
    # For telephony calls, we also trigger an initial assistant turn so callers do not
    # experience silence while waiting for the first prompt.
    await session.start(
        agent=Assistant(),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=ai_coustics.audio_enhancement(
                    model=ai_coustics.EnhancerModel.QUAIL_VF_L
                ),
            ),
        ),
    )

    if hasattr(session, "generate_reply"):
        await session.generate_reply(
            instructions=(
                "Greet the caller warmly, explain you will collect patient demographics, "
                "and ask for their first name."
            )
        )
    else:
        logger.warning("AgentSession.generate_reply is unavailable; waiting for caller input")


if __name__ == "__main__":
    cli.run_app(server)
