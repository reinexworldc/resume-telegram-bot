from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, select
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost/telegram_bot')

# Create SQLAlchemy engine
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create base class for models
Base = declarative_base()

# Define message model
class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)
    text = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    sent = Column(Integer, default=0)  # 0 - not sent, 1 - sent

# Create tables in database
def create_tables():
    Base.metadata.create_all(bind=engine)

# Get database session
def get_db():
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()

# Get unsent messages
def get_unsent_messages():
    db = get_db()
    try:
        return db.query(Message).filter(Message.sent == 0).all()
    except Exception as e:
        db.close()
        raise e

# Mark message as sent
def mark_message_as_sent(message_id):
    db = get_db()
    try:
        message = db.query(Message).filter(Message.id == message_id).first()
        if message:
            message.sent = 1
            db.commit()
            return True
        return False
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close() 