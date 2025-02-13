# app.py
import logging
from datetime import datetime, timedelta

from flask import Flask
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler

from config import Config
from extensions import db
from globals import BOT_NAMES_MAP, BOT_NAMES_LIST

# Create the Flask app and load configuration
app = Flask(__name__)
app.config.from_object(Config)
CORS(app)

# Initialize extensions
db.init_app(app)

# Import models so they are registered with SQLAlchemy
import models  # noqa

# Register Blueprints
from routes.text_routes import text_bp
from routes.voice_routes import voice_bp

app.register_blueprint(text_bp)
app.register_blueprint(voice_bp)

# Create database tables if they do not exist
with app.app_context():
    db.create_all()

if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    
    # Background job: deactivate sessions older than 24 hours
    def deactivate_inactive_sessions():
        from models import ChatSession
        cutoff = datetime.utcnow() - timedelta(hours=24)
        inactive = ChatSession.query.filter(
            ChatSession.created_at < cutoff,
            ChatSession.is_active == True
        ).all()
        for s in inactive:
            s.is_active = False
        db.session.commit()
        logging.info(f"Deactivated {len(inactive)} inactive sessions.")

    scheduler = BackgroundScheduler()
    scheduler.add_job(func=deactivate_inactive_sessions, trigger="interval", hours=1)
    scheduler.start()

    try:
        app.run(host="0.0.0.0", port=5001, debug=True)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
