from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Float
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class UserMessage(Base):
    __tablename__ = 'user_messages'
    
    id = Column(Integer, primary_key=True)
    username = Column(String(255), nullable=False, unique=True)
    message = Column(Text, nullable=False)
    approved = Column(Integer, default=0)  # 0 - на проверке, 1 - одобрено, -1 - отклонено
    check_result = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    last_sent = Column(DateTime, nullable=True)
    last_update = Column(DateTime, default=datetime.now)  # Время последнего обновления сообщения
    
    def __repr__(self):
        return f"<UserMessage(username='{self.username}', approved={self.approved})>" 