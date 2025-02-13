# config.py
import os

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'
    # Use SQLite for simplicity
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'chatbot.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Twilio configuration (replace with your secured credentials in production)
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID') or 'AC18537f619b1203a8272dcb94b9be46f6'
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN') or 'aaf88d532b45fed882b9dc0cabd4a49d'
    TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER') or '+18153398399'
