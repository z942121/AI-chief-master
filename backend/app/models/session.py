from sqlalchemy import Column, String, Integer, BigInteger, DateTime, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Session(Base):
    """会话模型"""
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    thread_id = Column(String(255), unique=True, nullable=False, index=True)
    title = Column(String(255), nullable=False, default="新对话")
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "thread_id": self.thread_id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }