import os
from datetime import datetime
from extensions import db

class ChatState:
    INITIAL = "INITIAL"
    COLLECTING_MOVE_SIZE = "COLLECTING_MOVE_SIZE"
    COLLECTING_MOVE_DATE = "COLLECTING_MOVE_DATE"
    COST_ESTIMATED = "COST_ESTIMATED"
    AWAITING_DETAILS = "AWAITING_DETAILS"
    AWAITING_NAME = "AWAITING_NAME"
    AWAITING_CONTACT = "AWAITING_CONTACT"
    AWAITING_FINAL_CONFIRMATION = "AWAITING_FINAL_CONFIRMATION"
    MODIFY_DETAILS = "MODIFY_DETAILS"
    CONFIRMED = "CONFIRMED"
    AWAITING_ADDITIONAL_SERVICES = "AWAITING_ADDITIONAL_SERVICES"  # NEW STATE

class ChatSession(db.Model):
    __tablename__ = "chat_sessions"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    chat_id = db.Column(db.String(100), unique=True, nullable=False)
    username = db.Column(db.String(100), nullable=True)
    contact_no = db.Column(db.String(50), nullable=True)
    move_date = db.Column(db.String(100), nullable=True)
    estimated_cost_min = db.Column(db.Float, nullable=True)
    estimated_cost_max = db.Column(db.Float, nullable=True)
    confirmed = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    state = db.Column(db.String(50), default=ChatState.INITIAL)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    messages = db.relationship("Message", backref="chat_session", lazy=True)
    move_detail = db.relationship("MoveDetail", backref="chat_session", uselist=False)

    def __repr__(self):
        return f"<ChatSession {self.chat_id}>"

class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    chat_id = db.Column(db.String(100), db.ForeignKey("chat_sessions.chat_id"), nullable=False)
    sender = db.Column(db.String(20), nullable=False)  # 'user' or 'assistant'
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Message {self.id} from {self.sender}>"

class MoveDetail(db.Model):
    __tablename__ = "move_details"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    chat_id = db.Column(db.String(100), db.ForeignKey("chat_sessions.chat_id"), unique=True, nullable=False)
    origin = db.Column(db.String(100), nullable=True)
    destination = db.Column(db.String(100), nullable=True)
    move_size = db.Column(db.String(100), nullable=True)
    additional_services = db.Column(db.String(200), nullable=True)
    move_date = db.Column(db.String(100), nullable=True)
    username = db.Column(db.String(100), nullable=True)
    contact_no = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    estimated_cost_min = db.Column(db.Float, nullable=True)
    estimated_cost_max = db.Column(db.Float, nullable=True)
    state = db.Column(db.String(50), default=ChatState.INITIAL)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<MoveDetail {self.chat_id}>"
