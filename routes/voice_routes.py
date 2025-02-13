import random
import re
import html
import uuid
import logging
from datetime import datetime, timedelta
from dateutil import parser

# Import language detection library
from langdetect import detect, DetectorFactory
# Fix seed for reproducible language detection results
DetectorFactory.seed = 0

from flask import Blueprint, request, Response
from twilio.twiml.voice_response import VoiceResponse, Gather

from extensions import db
from models import ChatSession, Message, MoveDetail, ChatState
from globals import BOT_NAMES_LIST, BOT_NAMES_MAP
from managers.openai_manager import OpenAIManager
from managers.maps_manager import MapsManager
from managers.faq_manager import FAQManager

logger = logging.getLogger(__name__)

# Define the blueprint for voice routes
voice_bp = Blueprint('voice_bp', __name__)

# Initialize managers
openai_manager = OpenAIManager()
maps_manager = MapsManager()
faq_manager = FAQManager()
faq_manager.load_faqs("data/faqs.jsonl")

########################################
# HELPER FUNCTIONS
########################################

def create_short_system_prompt(bot_name="MoveBot"):
    return (
        f"You are {bot_name} 🤖, a friendly assistant for My Good Movers. "
        "My Good Movers is a platform that connects users and moving companies. "
        "Try to convince the user to take our services, and provide them with the estimated cost of their move. "
        "Use emoticons to make your responses more friendly and engaging. "
        "Keep your answers brief, no more than 2 short sentences."
    )

def is_faq_query(user_text):
    keywords = [
        "modify booking",
        "hidden charge",
        "refund",
        "cancel",
        "policy",
        "charges",
        "payment",
        "change booking"
    ]
    return any(kw in user_text.lower() for kw in keywords)

def standardize_date(date_str):
    try:
        parsed_date = parser.parse(date_str, fuzzy=True)
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        if parsed_date < today:
            return None, "The date you provided is in the past. Please provide a future date."
        return parsed_date.strftime("%Y-%m-%d"), None
    except Exception as e:
        logger.error(f"Date Parsing Error: {e}")
        return None, "Invalid date format. Please provide a valid date."

def parse_move_details_with_openai(user_text):
    system_prompt = (
        "You are a JSON parser for a moving service chatbot. The user may provide details about their move.\n"
        "Extract the following information into JSON with these exact keys: origin, destination, move_size, move_date, additional_services, username, contact_no.\n"
        "If a field is not mentioned, set it to null or an empty array.\n"
        "Return only JSON, no extra text."
    )
    extraction_response = openai_manager.extract_fields_from_text(system_prompt, user_text)
    logger.debug(f"OpenAI Extraction Response: {extraction_response}")
    data = extraction_response if isinstance(extraction_response, dict) else {}
    return {
        "origin": data.get("origin"),
        "destination": data.get("destination"),
        "move_size": data.get("move_size"),
        "move_date": data.get("move_date"),
        "additional_services": data.get("additional_services") or [],
        "username": data.get("username"),
        "contact_no": data.get("contact_no")
    }

def detect_language(text):
    """
    Detects the language of the given text using langdetect.
    Returns a two-letter ISO language code (e.g. "en", "es", "fr").
    If detection fails, default to English ("en").
    """
    try:
        lang = detect(text)
        return lang
    except Exception as e:
        logger.error(f"Language detection failed: {e}")
        return "en"

def normal_gpt_reply(chat_session, user_text, language="en"):
    bot_name = BOT_NAMES_MAP.get(chat_session.chat_id, "MoveBot")
    system_prompt = create_short_system_prompt(bot_name)
    # If detected language is not English, prepend an instruction for the GPT response.
    if language != "en":
        system_prompt = f"Please respond in {language.upper()} language. " + system_prompt
    combined_input = f"Chat History:\n{get_chat_history(chat_session.chat_id)}\nUser: {user_text}"
    gpt_response = openai_manager.get_general_response(
        system_content=system_prompt,
        user_content=combined_input
    )
    assistant_message = Message(
        chat_id=chat_session.chat_id,
        sender="assistant",
        message=gpt_response
    )
    db.session.add(assistant_message)
    db.session.commit()
    return gpt_response

def get_chat_history(chat_id):
    messages = Message.query.filter_by(chat_id=chat_id).order_by(Message.timestamp).all()
    return "\n".join([f"{msg.sender.capitalize()}: {msg.message}" for msg in messages])

def sanitize_input(user_input):
    return html.escape(user_input)

# For testing, email and phone validations are commented out.
def validate_and_normalize_contact_number(contact):
    return contact  # Directly return the input

def validate_email(email):
    return email  # Directly return the input

def collect_or_update_move_details(chat_session, user_text):
    extracted = parse_move_details_with_openai(user_text)
    provided_fields = [extracted.get("origin"), extracted.get("destination"),
                       extracted.get("move_size"), extracted.get("move_date")]
    any_new_info = any(provided_fields)
    if not any_new_info:
        return (False, False, None)
    move_detail = chat_session.move_detail
    if not move_detail:
        move_detail = MoveDetail(chat_id=chat_session.chat_id)
        db.session.add(move_detail)
        db.session.commit()
    if extracted.get("origin"):
        move_detail.origin = extracted["origin"]
    if extracted.get("destination"):
        move_detail.destination = extracted["destination"]
    if extracted.get("move_size"):
        move_detail.move_size = extracted["move_size"]
    if extracted.get("additional_services"):
        move_detail.additional_services = ",".join(extracted["additional_services"])
    if extracted.get("username"):
        move_detail.username = extracted["username"]
    if extracted.get("contact_no"):
        move_detail.contact_no = extracted["contact_no"]
    if extracted.get("move_date"):
        std_date, err = standardize_date(extracted["move_date"])
        if err:
            db.session.commit()
            return (True, False, f"{err} Please provide a valid future date.")
        move_detail.move_date = std_date
        chat_session.move_date = std_date
    db.session.commit()
    missing = []
    if not move_detail.origin:
        missing.append("origin")
    if not move_detail.destination:
        missing.append("destination")
    if not move_detail.move_size:
        missing.append("move size")
    if not move_detail.move_date:
        missing.append("move date")
    if missing:
        fields_str = ", ".join(missing)
        reply = f"I still need your {fields_str} to provide an estimate."
        return (True, False, reply)
    distance, cost_range = maps_manager.estimate_cost(
        move_detail.origin,
        move_detail.destination,
        move_detail.move_size,
        move_detail.additional_services.split(',') if move_detail.additional_services else [],
        move_detail.move_date
    )
    if distance is None or not isinstance(cost_range, tuple):
        reply = "I'm having trouble calculating the cost. Please verify locations or try again."
        return (True, False, reply)
    min_cost, max_cost = cost_range
    chat_session.estimated_cost_min = min_cost
    chat_session.estimated_cost_max = max_cost
    move_detail.estimated_cost_min = min_cost
    move_detail.estimated_cost_max = max_cost
    chat_session.state = ChatState.COST_ESTIMATED
    move_detail.state = ChatState.COST_ESTIMATED
    db.session.commit()
    estimate_reply = (
        f"The estimated cost for moving from {move_detail.origin.title()} to {move_detail.destination.title()} "
        f"({move_detail.move_size.title()}, date: {move_detail.move_date}) is between ${min_cost} and ${max_cost}. 🏠📦💰\n"
        f"Would you like to proceed with booking this move? Please say Yes or No."
    )
    return (True, True, estimate_reply)

def get_or_create_voice_session():
    """
    Uses the unique CallSid provided by Twilio so that every call creates a new session.
    """
    call_sid = request.values.get("CallSid")
    if not call_sid:
        call_sid = request.values.get("From")
    chat_session = ChatSession.query.filter_by(chat_id=call_sid).first()
    if not chat_session:
        chat_session = ChatSession(chat_id=call_sid, state=ChatState.INITIAL)
        chosen_bot_name = random.choice(BOT_NAMES_LIST)
        BOT_NAMES_MAP[call_sid] = chosen_bot_name
        db.session.add(chat_session)
        db.session.commit()
    return chat_session

########################################
# VOICE ENDPOINTS
########################################

@voice_bp.route("/voice", methods=["POST"])
def voice():
    """
    Called by Twilio when the call is answered.
    Greets the caller and gathers their initial spoken input.
    """
    chat_session = get_or_create_voice_session()
    response = VoiceResponse()
    gather = Gather(input="speech", action="/voice/handle_input", method="POST", timeout=4)
    call_sid = request.values.get("CallSid")
    bot_name = BOT_NAMES_MAP.get(call_sid, "MoveBot")
    gather.say(f"Hello, this is {bot_name}. How can I assist you with your move today?")
    response.append(gather)
    # Do not append any goodbye message; always return Gather so that the call remains open.
    return Response(str(response), mimetype="text/xml")

@voice_bp.route("/voice/handle_input", methods=["POST"])
def voice_handle_input():
    """
    Processes the caller's speech input using the conversation logic.
    Returns TwiML with the assistant's reply and gathers further input.
    Also stores each transcript message in the database.
    """
    chat_session = get_or_create_voice_session()
    speech_input = request.values.get("SpeechResult", "").strip()
    
    # Store the caller's transcript in the database
    user_message = Message(chat_id=chat_session.chat_id, sender="user", message=speech_input)
    db.session.add(user_message)
    db.session.commit()
    
    # Detect the language of the input
    detected_lang = "en"
    try:
        detected_lang = detect_language(speech_input)
    except Exception as e:
        logger.error(f"Language detection error: {e}")
    
    try:
        if is_faq_query(speech_input):
            bot_reply = faq_manager.find_best_match(speech_input)
        else:
            if chat_session.state in [ChatState.INITIAL, ChatState.COLLECTING_MOVE_SIZE, ChatState.MODIFY_DETAILS]:
                any_new_info, did_estimate, reply_message = collect_or_update_move_details(chat_session, speech_input)
                if any_new_info and reply_message:
                    bot_reply = reply_message
                else:
                    bot_reply = normal_gpt_reply(chat_session, speech_input, language=detected_lang)
            elif chat_session.state == ChatState.COST_ESTIMATED:
                if "yes" in speech_input.lower():
                    chat_session.state = ChatState.AWAITING_ADDITIONAL_SERVICES
                    move_detail = chat_session.move_detail
                    if move_detail and move_detail.move_size:
                        additional_costs = maps_manager.get_additional_services_costs(move_detail.move_size)
                        bot_reply = (
                            f"Would you like any additional services such as packing (cost: ${additional_costs.get('packing')}) "
                            f"or storage (cost: ${additional_costs.get('storage')})? Please specify if you want packing, storage, or both. If not, say no."
                        )
                    else:
                        bot_reply = (
                            "Would you like any additional services such as packing or storage? Please specify, or say no."
                        )
                elif "no" in speech_input.lower():
                    chat_session.state = ChatState.INITIAL
                    bot_reply = "No worries! Let me know if you have any other questions."
                else:
                    bot_reply = "Please respond with Yes or No. Would you like to proceed with booking?"
            elif chat_session.state == ChatState.AWAITING_ADDITIONAL_SERVICES:
                move_detail = chat_session.move_detail
                user_lower = speech_input.lower().strip()
                services_found = []
                if "packing" in user_lower:
                    services_found.append("packing")
                if "storage" in user_lower:
                    services_found.append("storage")
                if not services_found:
                    bot_reply = "I didn't catch any specific additional service. I'll assume you don't want any additional services."
                    move_detail.additional_services = ""
                else:
                    move_detail.additional_services = ",".join(services_found)
                    bot_reply = f"Noted. You chose additional services: {move_detail.additional_services}."
                db.session.commit()
                distance, cost_range = maps_manager.estimate_cost(
                    move_detail.origin,
                    move_detail.destination,
                    move_detail.move_size,
                    move_detail.additional_services.split(',') if move_detail.additional_services else [],
                    move_detail.move_date
                )
                if distance is not None and isinstance(cost_range, tuple):
                    min_cost, max_cost = cost_range
                    chat_session.estimated_cost_min = min_cost
                    chat_session.estimated_cost_max = max_cost
                    move_detail.estimated_cost_min = min_cost
                    move_detail.estimated_cost_max = max_cost
                    db.session.commit()
                chat_session.state = ChatState.COLLECTING_MOVE_DATE
                db.session.commit()
                bot_reply += " Please share your email address for updates on your move."
            elif chat_session.state == ChatState.COLLECTING_MOVE_DATE:
                move_detail = chat_session.move_detail
                if not move_detail:
                    bot_reply = "No move details found. Please provide origin, destination, move size, and move date first."
                else:
                    # Directly store the raw email input without validation.
                    move_detail.email = speech_input
                    db.session.commit()
                    chat_session.state = ChatState.AWAITING_NAME
                    db.session.commit()
                    bot_reply = "Great! Now please share your name."
            elif chat_session.state == ChatState.AWAITING_NAME:
                name = speech_input.strip()
                if not name:
                    bot_reply = "I didn't catch your name. Please provide your name."
                else:
                    chat_session.username = name
                    move_detail = chat_session.move_detail
                    if move_detail:
                        move_detail.username = name
                    chat_session.state = ChatState.AWAITING_CONTACT
                    db.session.commit()
                    bot_reply = "Thank you! Now please share your 10-digit contact number."
            elif chat_session.state == ChatState.AWAITING_CONTACT:
                # Directly store the raw contact number input without validation.
                chat_session.contact_no = speech_input
                move_detail = chat_session.move_detail
                if move_detail:
                    move_detail.contact_no = speech_input
                chat_session.state = ChatState.AWAITING_FINAL_CONFIRMATION
                db.session.commit()
                svc = move_detail.additional_services or ""
                svc_list = [s for s in svc.split(",") if s]
                svc_str = ", ".join(svc_list) if svc_list else "None"
                bot_reply = (
                    f"Here are your move details: From {move_detail.origin.title() if move_detail.origin else 'Not Provided'}, "
                    f"To {move_detail.destination.title() if move_detail.destination else 'Not Provided'}, "
                    f"Move Size {move_detail.move_size.title() if move_detail.move_size else 'Not Provided'}, "
                    f"Move Date {move_detail.move_date}, Additional Services {svc_str}, Email {move_detail.email or 'Not Provided'}, "
                    f"Name {move_detail.username or 'Not Provided'}, Contact Number {move_detail.contact_no}. "
                    "Do you confirm this booking? Please say Yes or No."
                )
            elif chat_session.state == ChatState.AWAITING_FINAL_CONFIRMATION:
                if "yes" in speech_input.lower():
                    chat_session.confirmed = True
                    chat_session.is_active = False
                    chat_session.state = ChatState.CONFIRMED
                    db.session.commit()
                    bot_reply = "Your move has been successfully confirmed! Our team will be in touch soon."
                elif "no" in speech_input.lower():
                    chat_session.state = ChatState.MODIFY_DETAILS
                    db.session.commit()
                    bot_reply = "I understand. Which details would you like to change? For example, a new date or different origin/destination?"
                else:
                    bot_reply = "Please respond with Yes or No. Do you confirm this booking?"
            elif chat_session.state == ChatState.MODIFY_DETAILS:
                any_new_info, did_estimate, reply_message = collect_or_update_move_details(chat_session, speech_input)
                if any_new_info and reply_message:
                    bot_reply = reply_message
                else:
                    bot_reply = normal_gpt_reply(chat_session, speech_input, language=detected_lang)
            else:
                bot_reply = normal_gpt_reply(chat_session, speech_input, language=detected_lang)
        db.session.commit()

        # Build the TwiML response with the assistant's reply and gather further input.
        response = VoiceResponse()
        gather = Gather(input="speech", action="/voice/handle_input", method="POST", timeout=4)
        gather.say(bot_reply)
        response.append(gather)
        # No goodbye message added so that the call stays open.
        return Response(str(response), mimetype="text/xml")
    except Exception as e:
        logger.error(f"Error processing voice input: {e}")
        response = VoiceResponse()
        response.say("An error occurred. Please try again later.")
        return Response(str(response), mimetype="text/xml")
