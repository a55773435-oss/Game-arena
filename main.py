import asyncio
from collections import defaultdict, deque
import hashlib
import hmac
import html
import json
import os
import random
import secrets
import time
from datetime import datetime, timezone, date, timedelta
from typing import Literal, Optional
from pathlib import Path
from urllib.parse import parse_qsl

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo, MenuButtonWebApp
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Depends, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi import UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, UniqueConstraint, select, func, inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
import uvicorn

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "7347642182"))
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip().rstrip("/")
PORT = int(os.getenv("PORT", "8000"))
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./gamearena.db").strip()
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
(STATIC_DIR / "owner").mkdir(parents=True, exist_ok=True)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    first_name: Mapped[str] = mapped_column(String(120), default="بازیکن")
    username: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    xp: Mapped[int] = mapped_column(Integer, default=0)
    games: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    streak: Mapped[int] = mapped_column(Integer, default=0)
    coins: Mapped[int] = mapped_column(BigInteger, default=100)
    level: Mapped[int] = mapped_column(Integer, default=1)
    photo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    equipped_avatar_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    equipped_character_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    custom_character_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    equipped_frame_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    equipped_badge_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    equipped_gift_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    equipped_showcase_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    vip_tier: Mapped[str] = mapped_column(String(20), default="none")
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_daily: Mapped[str] = mapped_column(String(10), default="")
    wheel_date: Mapped[str] = mapped_column(String(10), default="")
    wheel_spins: Mapped[int] = mapped_column(Integer, default=0)
    daily_date: Mapped[str] = mapped_column(String(10), default="")
    daily_games: Mapped[int] = mapped_column(Integer, default=0)
    daily_wins: Mapped[int] = mapped_column(Integer, default=0)
    mission_claims: Mapped[str] = mapped_column(String(30), default="")
    referred_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Challenge(Base):
    __tablename__ = "challenges"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    game: Mapped[str] = mapped_column(String(30))
    payload: Mapped[str] = mapped_column(Text)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class GameRecord(Base):
    __tablename__ = "game_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    game: Mapped[str] = mapped_column(String(40), index=True)
    won: Mapped[bool] = mapped_column(Boolean, default=False)
    xp: Mapped[int] = mapped_column(Integer, default=0)
    coins: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    amount: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(180))
    balance_after: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class InventoryTransaction(Base):
    __tablename__ = "inventory_transactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    product_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    product_name: Mapped[str] = mapped_column(String(100), default="آیتم")
    action: Mapped[str] = mapped_column(String(30), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    details: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500), default="")
    category: Mapped[str] = mapped_column(String(40), default="item")
    rarity: Mapped[str] = mapped_column(String(30), default="common")
    price_coins: Mapped[int] = mapped_column(Integer, default=0)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    reward_only: Mapped[bool] = mapped_column(Boolean, default=False)
    bundle_items: Mapped[str] = mapped_column(Text, default="[]")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class InventoryItem(Base):
    __tablename__ = "inventory_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    purchased_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Clan(Base):
    __tablename__ = "clans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(40), unique=True)
    description: Mapped[str] = mapped_column(String(300), default="")
    owner_id: Mapped[int] = mapped_column(BigInteger, index=True)
    xp: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[int] = mapped_column(Integer, default=1)
    motto: Mapped[str] = mapped_column(String(120), default="")
    treasury: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class ClanMember(Base):
    __tablename__ = "clan_members"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    clan_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    role: Mapped[str] = mapped_column(String(20), default="member")
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class ClanChatMessage(Base):
    __tablename__ = "clan_chat_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    clan_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    sender_name: Mapped[str] = mapped_column(String(120), default="بازیکن")
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

class ClanBattle(Base):
    __tablename__ = "clan_battles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    challenger_clan_id: Mapped[int] = mapped_column(Integer, index=True)
    opponent_clan_id: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    challenger_score: Mapped[int] = mapped_column(Integer, default=0)
    opponent_score: Mapped[int] = mapped_column(Integer, default=0)
    winner_clan_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

class ClanBattleParticipant(Base):
    __tablename__ = "clan_battle_participants"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    battle_id: Mapped[int] = mapped_column(Integer, index=True)
    clan_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    rewarded: Mapped[bool] = mapped_column(Boolean, default=False)

class FriendChallenge(Base):
    __tablename__ = "friend_challenges"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sender_id: Mapped[int] = mapped_column(BigInteger, index=True)
    target_id: Mapped[int] = mapped_column(BigInteger, index=True)
    game: Mapped[str] = mapped_column(String(40), default="math")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    winner_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    sender_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    target_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Tournament(Base):
    __tablename__ = "tournaments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    game: Mapped[str] = mapped_column(String(40), default="math")
    prize_coins: Mapped[int] = mapped_column(Integer, default=0)
    max_players: Mapped[int] = mapped_column(Integer, default=16)
    status: Mapped[str] = mapped_column(String(20), default="open")
    bracket: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class TournamentEntry(Base):
    __tablename__ = "tournament_entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tournament_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class UserAchievement(Base):
    __tablename__ = "user_achievements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    code: Mapped[str] = mapped_column(String(40))
    unlocked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class LeagueConfig(Base):
    __tablename__ = "league_config"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    threshold: Mapped[int] = mapped_column(Integer, unique=True)
    title: Mapped[str] = mapped_column(String(50))

class GameConfig(Base):
    __tablename__ = "game_config"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game: Mapped[str] = mapped_column(String(40), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

class AppSetting(Base):
    __tablename__ = "app_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(60), unique=True)
    value: Mapped[str] = mapped_column(String(120))

class SecurityEvent(Base):
    __tablename__ = "security_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    code: Mapped[str] = mapped_column(String(50), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    detail: Mapped[str] = mapped_column(String(500), default="")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

class FriendRequest(Base):
    __tablename__ = "friend_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    requester_id: Mapped[int] = mapped_column(BigInteger, index=True)
    target_id: Mapped[int] = mapped_column(BigInteger, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

class Friendship(Base):
    __tablename__ = "friendships"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_low: Mapped[int] = mapped_column(BigInteger, index=True)
    user_high: Mapped[int] = mapped_column(BigInteger, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class PrivateMessage(Base):
    __tablename__ = "private_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sender_id: Mapped[int] = mapped_column(BigInteger, index=True)
    recipient_id: Mapped[int] = mapped_column(BigInteger, index=True)
    message: Mapped[str] = mapped_column(String(900))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

class ArenaEvent(Base):
    __tablename__ = "arena_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500), default="")
    bonus_xp: Mapped[int] = mapped_column(Integer, default=0)
    starts_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class AdminAudit(Base):
    __tablename__ = "admin_audit"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(BigInteger, index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    target_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    detail: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

class ArenaSeason(Base):
    __tablename__ = "arena_seasons"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    starts_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ends_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class SeasonScore(Base):
    __tablename__ = "season_scores"
    __table_args__ = (UniqueConstraint("season_id", "user_id", name="uq_season_user"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    points: Mapped[int] = mapped_column(Integer, default=0)
    games: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class GlobalChatMessage(Base):
    __tablename__ = "global_chat_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    message: Mapped[str] = mapped_column(String(450))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

class ArenaNotification(Base):
    __tablename__ = "arena_notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    kind: Mapped[str] = mapped_column(String(40), default="general")
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(String(500), default="")
    data_json: Mapped[str] = mapped_column(Text, default="{}")
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

class UserBlock(Base):
    __tablename__ = "user_blocks"
    __table_args__ = (UniqueConstraint("blocker_id", "blocked_id", name="uq_user_block"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    blocker_id: Mapped[int] = mapped_column(BigInteger, index=True)
    blocked_id: Mapped[int] = mapped_column(BigInteger, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class UserReport(Base):
    __tablename__ = "user_reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reporter_id: Mapped[int] = mapped_column(BigInteger, index=True)
    target_id: Mapped[int] = mapped_column(BigInteger, index=True)
    reason: Mapped[str] = mapped_column(String(40), default="other")
    details: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    reviewed_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

class ClanTerritory(Base):
    __tablename__ = "clan_territories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    territory_key: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    owner_clan_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    level: Mapped[int] = mapped_column(Integer, default=1)
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

class ArenaQueueEntry(Base):
    __tablename__ = "arena_queue_entries"
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    game: Mapped[str] = mapped_column(String(40), default="math", index=True)
    status: Mapped[str] = mapped_column(String(20), default="waiting", index=True)
    match_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

class ArenaLiveMatch(Base):
    __tablename__ = "arena_live_matches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game: Mapped[str] = mapped_column(String(40), default="math")
    player_one_id: Mapped[int] = mapped_column(BigInteger, index=True)
    player_two_id: Mapped[int] = mapped_column(BigInteger, index=True)
    question: Mapped[str] = mapped_column(String(100))
    expected_answer: Mapped[int] = mapped_column(Integer)
    player_one_answer: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    player_two_answer: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="playing", index=True)
    winner_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    rewarded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

app = FastAPI(title="GAME ARENA 3.0 API", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
dp = Dispatcher()
bot_username = ""
bot: Optional[Bot] = None
CLAN_CHAT_USERS: set[int] = set()
PRIVATE_CHAT_TARGET: dict[int, int] = {}
CLAN_CHAT_LAST: dict[int, float] = {}
GLOBAL_CHAT_LAST: dict[int, float] = {}
REQUEST_TIMES = defaultdict(deque)
MUTATION_TIMES = defaultdict(deque)
SECURITY_ALERT_COOLDOWN: dict[tuple[int, str], float] = {}

LEAGUES = [
    (0, "🪵 Wood"), (250, "🥉 Bronze"), (1000, "🥈 Silver"),
    (2000, "🥇 Gold"), (3000, "💎 Diamond"), (5000, "🔥 Master"), (8000, "👑 Legend")
]
ACHIEVEMENTS = [
    ("first_win", "اولین پیروزی", "🏅", "اولین مسابقه را ببر"),
    ("games_10", "بازیکن فعال", "🎮", "۱۰ بازی انجام بده"),
    ("wins_10", "قهرمان کوچک", "🥉", "۱۰ مسابقه را ببر"),
    ("wins_100", "افسانه میدان", "👑", "۱۰۰ مسابقه را ببر"),
    ("games_50", "همیشه در میدان", "⚡", "۵۰ بازی انجام بده"),
    ("streak_7", "هفت روز طلایی", "🔥", "۷ روز متوالی وارد شو"),
    ("streak_10", "ده روز وفاداری", "💫", "۱۰ روز متوالی وارد شو"),
]
GAME_STATUS = {"math": True, "ttt": True, "penalty": True, "basketball": True, "volleyball": True, "guess": True, "memory": True, "neon-breakout": True, "neon-runner": False, "space-shooter": True, "neon-drift": True}
TTT_DIFFICULTY = "hard"


def league_for(xp: int) -> str:
    result = LEAGUES[0][1]
    for threshold, title in LEAGUES:
        if xp >= threshold:
            result = title
    return result

def next_league(xp: int):
    for threshold, title in LEAGUES:
        if xp < threshold:
            return {"name": title, "at": threshold, "left": threshold - xp}
    return {"name": "حداکثر لیگ", "at": xp, "left": 0}

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # create_all does not add columns to existing Railway databases; migrate safely.
        columns = await conn.run_sync(lambda c: {col["name"] for col in inspect(c).get_columns("users")})
        migrations = {
            "coins": "BIGINT NOT NULL DEFAULT 100",
            "level": "INTEGER NOT NULL DEFAULT 1",
            "photo_url": "VARCHAR(500)",
            "is_verified": "BOOLEAN NOT NULL DEFAULT FALSE",
            "equipped_avatar_id": "INTEGER",
            "equipped_character_id": "INTEGER",
            "custom_character_url": "VARCHAR(500)",
            "equipped_frame_id": "INTEGER",
            "equipped_badge_id": "INTEGER",
            "equipped_gift_id": "INTEGER",
            "equipped_showcase_id": "INTEGER",
            "is_banned": "BOOLEAN NOT NULL DEFAULT FALSE",
            "wheel_date": "VARCHAR(10) NOT NULL DEFAULT ''",
            "wheel_spins": "INTEGER NOT NULL DEFAULT 0",
            "vip_tier": "VARCHAR(20) NOT NULL DEFAULT 'none'",
            "last_seen_at": "TIMESTAMP",
        }
        for name, sql_type in migrations.items():
            if name not in columns:
                await conn.execute(text(f"ALTER TABLE users ADD COLUMN {name} {sql_type}"))
        product_columns = await conn.run_sync(lambda c: {col["name"] for col in inspect(c).get_columns("products")})
        product_migrations = {
            "reward_only": "BOOLEAN NOT NULL DEFAULT FALSE",
            "bundle_items": "TEXT NOT NULL DEFAULT '[]'",
        }
        for name, sql_type in product_migrations.items():
            if name not in product_columns:
                await conn.execute(text(f"ALTER TABLE products ADD COLUMN {name} {sql_type}"))
        clan_columns = await conn.run_sync(lambda c: {col["name"] for col in inspect(c).get_columns("clans")})
        for name, sql_type in {"xp": "INTEGER NOT NULL DEFAULT 0", "level": "INTEGER NOT NULL DEFAULT 1", "motto": "VARCHAR(120) NOT NULL DEFAULT ''", "treasury": "BIGINT NOT NULL DEFAULT 0"}.items():
            if name not in clan_columns:
                await conn.execute(text(f"ALTER TABLE clans ADD COLUMN {name} {sql_type}"))
        # Migrate previously sold avatar-style products into character renders.
        await conn.execute(text("UPDATE products SET category='character' WHERE category='avatar'"))
        await conn.execute(text("UPDATE users SET equipped_character_id=equipped_avatar_id WHERE equipped_character_id IS NULL AND equipped_avatar_id IS NOT NULL"))
        await conn.execute(text("UPDATE products SET reward_only=TRUE WHERE category IN ('gift','pack','item')"))
        # Legacy wheel_date means the old app already granted today's free spin.
        await conn.execute(text("UPDATE users SET wheel_spins = 1 WHERE wheel_date <> '' AND wheel_spins = 0"))
    async with SessionLocal() as session:
        existing = (await session.execute(select(LeagueConfig))).scalars().all()
        if not existing:
            for threshold, title in LEAGUES:
                session.add(LeagueConfig(threshold=threshold, title=title))
        else:
            saved_leagues = sorted([(x.threshold, x.title) for x in existing], key=lambda x: x[0])
            legacy_thresholds = [0, 75, 250, 600, 1200, 2500, 5000]
            if [x[0] for x in saved_leagues] == legacy_thresholds:
                await session.execute(text("DELETE FROM league_config"))
                for threshold, title in LEAGUES:
                    session.add(LeagueConfig(threshold=threshold, title=title))
            else:
                LEAGUES[:] = saved_leagues
        saved_games = (await session.execute(select(GameConfig))).scalars().all()
        if not saved_games:
            session.add_all([GameConfig(game=key, enabled=value) for key, value in GAME_STATUS.items()])
        else:
            saved_map = {row.game: row for row in saved_games}
            for row in saved_games:
                GAME_STATUS[row.game] = row.enabled
            if "neon-runner" in saved_map:
                saved_map["neon-runner"].enabled = False
                GAME_STATUS["neon-runner"] = False
            for key, value in GAME_STATUS.items():
                if key not in saved_map:
                    session.add(GameConfig(game=key, enabled=value))
        setting = await session.scalar(select(AppSetting).where(AppSetting.key == "ttt_difficulty"))
        if setting:
            global TTT_DIFFICULTY
            TTT_DIFFICULTY = setting.value if setting.value in ("easy", "medium", "hard") else "hard"
        else:
            session.add(AppSetting(key="ttt_difficulty", value="hard"))
        product_count = await session.scalar(select(func.count()).select_from(Product))
        if not product_count:
            session.add_all([
                Product(name="قاب الماسی", description="قاب بیرونی عکس پروفایل", category="frame", rarity="epic", price_coins=150),
                Product(name="نشان قهرمان", description="نشان ویژه کنار نام", category="badge", rarity="rare", price_coins=100),
                Product(name="گیفت ویژه مالک", description="هدیه اختصاصی که فقط مالک اعطا می‌کند", category="gift", rarity="legendary", price_coins=0, reward_only=True),
            ])
        await ensure_active_season(session)
        await session.commit()

async def ensure_user(session: AsyncSession, telegram_user: dict, referrer: Optional[int] = None):
    uid = int(telegram_user["id"])
    user = await session.get(User, uid)
    created = False
    if user is None:
        valid_ref = referrer if referrer and referrer != uid else None
        user = User(
            id=uid,
            first_name=(telegram_user.get("first_name") or "بازیکن")[:120],
            username=telegram_user.get("username"),
            photo_url=telegram_user.get("photo_url"),
            referred_by=valid_ref,
        )
        session.add(user)
        created = True
        if valid_ref:
            inviter = await session.get(User, valid_ref)
            if inviter:
                await grant_xp(session, inviter, 25, "دعوت دوست")
    else:
        user.first_name = (telegram_user.get("first_name") or user.first_name or "بازیکن")[:120]
        user.username = telegram_user.get("username")
        user.photo_url = telegram_user.get("photo_url") or user.photo_url
    user.last_seen_at = datetime.utcnow()
    await session.commit()
    return user, created

async def add_coins(session: AsyncSession, user: User, amount: int, reason: str):
    if amount == 0:
        return
    user.coins = max(0, int(user.coins or 0) + int(amount))
    session.add(WalletTransaction(user_id=user.id, amount=amount, reason=reason[:180], balance_after=user.coins))

async def grant_xp(session: AsyncSession, user: User, amount: int, reason: str = "کسب تجربه"):
    old_level = max(1, int(user.xp or 0) // 100 + 1)
    user.xp = max(0, int(user.xp or 0) + int(amount))
    new_level = max(1, user.xp // 100 + 1)
    user.level = new_level
    if new_level > old_level:
        bonus = (new_level - old_level) * 25
        await add_coins(session, user, bonus, f"جایزه ارتقای سطح {new_level}")

async def unlock_achievements(session: AsyncSession, user: User):
    existing = set((await session.execute(select(UserAchievement.code).where(UserAchievement.user_id == user.id))).scalars().all())
    rules = [
        ("first_win", user.wins >= 1), ("games_10", user.games >= 10),
        ("wins_10", user.wins >= 10), ("wins_100", user.wins >= 100),
        ("games_50", user.games >= 50), ("streak_7", user.streak >= 7), ("streak_10", user.streak >= 10),
    ]
    for code, ok in rules:
        if ok and code not in existing:
            session.add(UserAchievement(user_id=user.id, code=code))
            await add_coins(session, user, 20, "پاداش دستاورد")

async def ensure_active_season(session: AsyncSession) -> ArenaSeason:
    now = datetime.utcnow()
    season = await session.scalar(select(ArenaSeason).where(ArenaSeason.status == "active").order_by(ArenaSeason.id.desc()).limit(1))
    if season and season.ends_at > now:
        return season
    if season:
        season.status = "completed"
    latest_id = int(await session.scalar(select(func.max(ArenaSeason.id))) or 0)
    season = ArenaSeason(name=f"SEASON {latest_id + 1:02d} · ARENA ASCENSION",
                         starts_at=now, ends_at=now + timedelta(days=30), status="active")
    session.add(season)
    await session.flush()
    return season

async def create_notification(session: AsyncSession, user_id: int, kind: str, title: str, body: str = "", data: Optional[dict] = None):
    session.add(ArenaNotification(user_id=user_id, kind=kind[:40], title=title[:120], body=body[:500],
                                  data_json=json.dumps(data or {}, ensure_ascii=False)))

async def is_blocked_between(session: AsyncSession, user_a: int, user_b: int) -> bool:
    row = await session.scalar(select(UserBlock.id).where(
        ((UserBlock.blocker_id == user_a) & (UserBlock.blocked_id == user_b)) |
        ((UserBlock.blocker_id == user_b) & (UserBlock.blocked_id == user_a))).limit(1))
    return row is not None

async def record_game(session: AsyncSession, user: User, xp: int, won: bool, game: str = "game", commit: bool = True):
    minute_ago = datetime.utcnow() - timedelta(seconds=60)
    recent_games = await session.scalar(select(func.count()).select_from(GameRecord).where(
        GameRecord.user_id == user.id, GameRecord.created_at >= minute_ago))
    if int(recent_games or 0) >= 10:
        await flag_security_event(user.id, "rapid_game_completions",
                                  f"بیش از ۱۰ نتیجه بازی در یک دقیقه ثبت شده؛ بازی اخیر: {game}",
                                  "high", {"game": game, "recent_count": int(recent_games or 0)})
    today = date.today().isoformat()
    if user.daily_date != today:
        user.daily_date = today
        user.daily_games = 0
        user.daily_wins = 0
        user.mission_claims = ""
    user.games += 1
    user.daily_games += 1
    if won:
        user.wins += 1
        user.daily_wins += 1
    else:
        user.losses += 1
    vip_multiplier = {"none": 1.0, "vip": 1.10, "vip_plus": 1.20, "elite": 1.30, "legend": 1.40}.get(user.vip_tier or "none", 1.0)
    event_bonus = int(await session.scalar(select(func.max(ArenaEvent.bonus_xp)).where(ArenaEvent.active == True, ArenaEvent.starts_at <= datetime.utcnow(), ArenaEvent.ends_at >= datetime.utcnow())) or 0)
    awarded_xp = int(round(max(0, xp) * vip_multiplier)) + (event_bonus if xp > 0 else 0)
    await grant_xp(session, user, awarded_xp, f"نتیجه بازی {game}")
    coin_reward = (12 if won else 2) + (2 if user.vip_tier in ("vip_plus", "elite", "legend") and won else 0)
    await add_coins(session, user, coin_reward, f"پاداش بازی {game}")
    session.add(GameRecord(user_id=user.id, game=game, won=won, xp=awarded_xp, coins=coin_reward))
    season = await ensure_active_season(session)
    season_score = await session.scalar(select(SeasonScore).where(SeasonScore.season_id == season.id, SeasonScore.user_id == user.id).with_for_update())
    if season_score is None:
        season_score = SeasonScore(season_id=season.id, user_id=user.id)
        session.add(season_score)
    season_score.points += awarded_xp + (5 if won else 0)
    season_score.games += 1
    season_score.wins += 1 if won else 0
    season_score.updated_at = datetime.utcnow()
    member = await session.scalar(select(ClanMember).where(ClanMember.user_id == user.id))
    if member:
        clan = await session.get(Clan, member.clan_id)
        if clan:
            clan.xp += 2 + (3 if won else 0)
            clan.level = max(1, clan.xp // 250 + 1)
    await unlock_achievements(session, user)
    if commit:
        await session.commit()


def validate_init_data(init_data: str) -> dict:
    if not BOT_TOKEN:
        raise HTTPException(status_code=503, detail="BOT_TOKEN روی سرور تنظیم نشده است.")
    if not init_data:
        raise HTTPException(status_code=401, detail="مینی‌اپ را از داخل تلگرام باز کنید.")
    values = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = values.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=401, detail="اطلاعات ورود تلگرام معتبر نیست.")
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(values.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, received_hash):
        raise HTTPException(status_code=401, detail="امضای تلگرام معتبر نیست.")
    try:
        auth_date = int(values.get("auth_date", "0"))
        if time.time() - auth_date > 86400 or auth_date > time.time() + 60:
            raise HTTPException(status_code=401, detail="نشست تلگرام منقضی شده است؛ مینی‌اپ را دوباره باز کنید.")
        tg_user = json.loads(values.get("user", "{}"))
        if not tg_user.get("id"):
            raise ValueError("missing user id")
    except (ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="اطلاعات کاربر تلگرام قابل خواندن نیست.")
    return tg_user

async def flag_security_event(user_id: int, code: str, detail: str, severity: str = "medium", metadata: Optional[dict] = None):
    """Persist a deduplicated anomaly and alert the owner for high-severity events."""
    now_mono = time.monotonic()
    cooldown_key = (int(user_id), code)
    if now_mono - SECURITY_ALERT_COOLDOWN.get(cooldown_key, 0) < 600:
        return
    SECURITY_ALERT_COOLDOWN[cooldown_key] = now_mono
    try:
        async with SessionLocal() as session:
            cutoff = datetime.utcnow() - timedelta(minutes=10)
            prior = await session.scalar(select(SecurityEvent.id).where(
                SecurityEvent.user_id == user_id, SecurityEvent.code == code,
                SecurityEvent.created_at >= cutoff).limit(1))
            if prior:
                return
            event = SecurityEvent(user_id=user_id, code=code, severity=severity,
                                  detail=detail[:500], metadata_json=json.dumps(metadata or {}, ensure_ascii=False))
            session.add(event)
            await session.commit()
        if severity == "high" and bot:
            try:
                await bot.send_message(ADMIN_ID, f"🚨 رفتار مشکوک در GAME ARENA\nکاربر: {user_id}\nنوع: {code}\nجزئیات: {detail[:350]}")
            except Exception as exc:
                print(f"Owner security alert failed: {exc}")
    except Exception as exc:
        print(f"Security event persistence failed: {exc}")

async def inspect_request_behavior(user_id: int, method: str, path: str):
    now = time.monotonic()
    all_events = REQUEST_TIMES[user_id]
    all_events.append(now)
    while all_events and now - all_events[0] > 60:
        all_events.popleft()
    if method.upper() in ("POST", "PUT", "PATCH", "DELETE"):
        mutations = MUTATION_TIMES[user_id]
        mutations.append(now)
        while mutations and now - mutations[0] > 10:
            mutations.popleft()
        if len(mutations) >= 30:
            await flag_security_event(user_id, "rapid_mutations", f"تعداد {len(mutations)} درخواست تغییردهنده در ۱۰ ثانیه؛ مسیر آخر: {path}", "high", {"path": path, "count": len(mutations)})
        if len(mutations) >= 45:
            raise HTTPException(status_code=429, detail="درخواست‌ها بیش از حد سریع ارسال می‌شوند؛ چند لحظه بعد دوباره امتحان کن.")
    if len(all_events) >= 140:
        await flag_security_event(user_id, "rapid_requests", f"تعداد {len(all_events)} درخواست احراز‌شده در یک دقیقه؛ مسیر آخر: {path}", "high", {"path": path, "count": len(all_events)})
    if len(all_events) >= 200:
        raise HTTPException(status_code=429, detail="تعداد درخواست‌ها از حد مجاز بیشتر شده است.")

async def current_user(request: Request, x_telegram_init_data: str = Header(default="")) -> User:
    tg_user = validate_init_data(x_telegram_init_data)
    async with SessionLocal() as session:
        user, _ = await ensure_user(session, tg_user)
        if user.is_banned:
            raise HTTPException(status_code=403, detail="حساب کاربری شما مسدود شده است.")
        await inspect_request_behavior(user.id, request.method, request.url.path)
        # Return a detached snapshot; API handlers re-load the user in their own session.
        return user

class MathAnswer(BaseModel):
    challenge_id: str
    answer: str = Field(max_length=30)

class SportsPlay(BaseModel):
    game: str
    choice: str

class TTTMove(BaseModel):
    challenge_id: str
    index: int = Field(ge=0, le=8)

class DailyClaim(BaseModel):
    pass

class IQAnswer(BaseModel):
    challenge_id: str
    answer: str = Field(max_length=50)

class GuessAttempt(BaseModel):
    challenge_id: str
    guess: int = Field(ge=1, le=50)

class MemoryAnswer(BaseModel):
    challenge_id: str
    answer: str = Field(max_length=100)

class MemoryStart(BaseModel):
    pairs: int = Field(default=8, ge=6, le=12)

class MemoryFlip(BaseModel):
    challenge_id: str
    index: int = Field(ge=0, le=23)

class RunnerAction(BaseModel):
    challenge_id: str
    action: Literal["run", "jump", "slide"]

class BreakoutFinish(BaseModel):
    challenge_id: str
    score: int = Field(ge=0, le=100000)
    duration_ms: int = Field(ge=0, le=900000)

class ArcadeStart(BaseModel):
    game: Literal["space-shooter", "neon-drift"]

class ArcadeFinish(BaseModel):
    challenge_id: str
    score: int = Field(ge=0, le=50000)

class ForceJoinInput(BaseModel):
    enabled: bool = False
    chat_id: str = Field(default="", max_length=100)
    invite_url: str = Field(default="", max_length=120)
    title: str = Field(default="کانال رسمی GAME ARENA", max_length=100)

class BuyItem(BaseModel):
    product_id: int

class EquipItem(BaseModel):
    product_id: int

class VerifyUserInput(BaseModel):
    user_id: int
    verified: bool = True

class ClanCreate(BaseModel):
    name: str = Field(min_length=3, max_length=40)
    description: str = Field(default="", max_length=300)

class ClanJoin(BaseModel):
    clan_id: int

class ClanBattleCreate(BaseModel):
    opponent_clan_id: int

class ClanBattleRespond(BaseModel):
    accept: bool

class FriendChallengeCreate(BaseModel):
    target_id: int
    game: str = Field(default="math", max_length=40)

class FriendChallengeResponse(BaseModel):
    challenge_id: int
    accept: bool

class FriendChallengePlay(BaseModel):
    challenge_id: int
    answer: str = Field(max_length=100)

class TournamentCreate(BaseModel):
    name: str = Field(min_length=3, max_length=100)
    game: str = Field(default="math", max_length=40)
    prize_coins: int = Field(default=0, ge=0, le=1000000)
    max_players: int = Field(default=16, ge=2, le=256)

class TournamentMatchResult(BaseModel):
    round_index: int = Field(ge=0, le=12)
    match_index: int = Field(ge=0, le=255)
    winner_id: int

class ProductInput(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str = Field(default="", max_length=500)
    category: str = Field(default="item", max_length=40)
    rarity: str = Field(default="common", max_length=30)
    price_coins: int = Field(ge=0, le=10000000)
    image_url: Optional[str] = Field(default=None, max_length=500)
    reward_only: bool = False
    bundle_items: list[dict] = Field(default_factory=list)
    active: bool = True

class GrantRewardInput(BaseModel):
    user_id: int
    product_id: int
    quantity: int = Field(default=1, ge=1, le=100)

class OpenPackInput(BaseModel):
    product_id: int

class CoinAdjustment(BaseModel):
    user_id: int
    amount: int = Field(ge=-100000000, le=100000000)
    reason: str = Field(default="تغییر موجودی توسط مدیر", max_length=180)

class BanUserInput(BaseModel):
    user_id: int
    banned: bool = True

class AdminBroadcast(BaseModel):
    message: str = Field(min_length=1, max_length=3500)

class LeagueInput(BaseModel):
    leagues: list[dict]

class GameToggleInput(BaseModel):
    game: str
    enabled: bool

class TTTHardnessInput(BaseModel):
    difficulty: Literal["easy", "medium", "hard"]

class FriendRequestInput(BaseModel):
    target_id: int

class FriendRequestRespond(BaseModel):
    accept: bool

class ClanMemberRoleInput(BaseModel):
    role: Literal["member", "leader"]

class ClanTransferInput(BaseModel):
    new_owner_id: int

class VipGrantInput(BaseModel):
    user_id: int
    tier: Literal["none", "vip", "vip_plus", "elite", "legend"]

class EventInput(BaseModel):
    title: str = Field(min_length=3, max_length=100)
    description: str = Field(default="", max_length=500)
    bonus_xp: int = Field(default=5, ge=0, le=500)
    duration_hours: int = Field(default=72, ge=1, le=24*90)
    active: bool = True

class GlobalChatInput(BaseModel):
    message: str = Field(min_length=1, max_length=300)

class SocialBlockInput(BaseModel):
    target_id: int = Field(gt=0)

class UserReportInput(BaseModel):
    target_id: int = Field(gt=0)
    reason: Literal["harassment", "spam", "cheating", "impersonation", "other"] = "other"
    details: str = Field(default="", max_length=500)

class TerritoryClaimInput(BaseModel):
    territory_key: str = Field(min_length=2, max_length=40)

class ClanDepositInput(BaseModel):
    amount: int = Field(gt=0, le=5000)

class MatchmakingInput(BaseModel):
    game: Literal["math"] = "math"

class LiveMatchAnswer(BaseModel):
    answer: int = Field(ge=-1000000, le=1000000)

class SeasonInput(BaseModel):
    name: str = Field(min_length=3, max_length=100)
    duration_days: int = Field(default=30, ge=7, le=120)

async def load_force_join_settings(session: AsyncSession):
    keys = ("force_join_enabled", "force_join_chat", "force_join_url", "force_join_title")
    rows = (await session.execute(select(AppSetting).where(AppSetting.key.in_(keys)))).scalars().all()
    values = {row.key: row.value for row in rows}
    enabled = values.get("force_join_enabled", "0") == "1"
    chat_id = values.get("force_join_chat", "").strip()
    invite_url = values.get("force_join_url", "").strip()
    title = values.get("force_join_title", "کانال رسمی GAME ARENA")
    return {"enabled": enabled, "chat_id": chat_id, "invite_url": invite_url, "title": title}

async def check_required_membership(user_id: int, settings: dict) -> bool:
    if user_id == ADMIN_ID or not settings.get("enabled"):
        return True
    chat_id = settings.get("chat_id", "").strip()
    if not chat_id or bot is None:
        return False
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        status = getattr(member.status, "value", str(member.status))
        if status in ("creator", "administrator", "member"):
            return True
        return status == "restricted" and bool(getattr(member, "is_member", False))
    except Exception as exc:
        # Membership cannot be verified unless the bot can inspect the target channel.
        print(f"Force-join membership check failed for {user_id}: {exc}")
        return False

async def require_user_id(user: User = Depends(current_user)) -> int:
    if user.id == ADMIN_ID:
        return user.id
    async with SessionLocal() as session:
        settings = await load_force_join_settings(session)
    if settings["enabled"] and not await check_required_membership(user.id, settings):
        raise HTTPException(403, "برای استفاده از GAME ARENA ابتدا در کانال اعلام‌شده عضو شو و سپس عضویتت را بررسی کن.")
    return user.id

@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))

@app.get("/health")
async def health():
    return {"ok": True, "service": "game-arena", "version": "3.0.0"}

@app.get("/api/access")
async def access_status(user: User = Depends(current_user)):
    async with SessionLocal() as session:
        settings = await load_force_join_settings(session)
    required = bool(settings["enabled"] and user.id != ADMIN_ID)
    joined = await check_required_membership(user.id, settings) if required else True
    message = "اگر عضو کانال هستی اما تأیید نمی‌شوی، از مدیر بخواه شناسه کانال و ادمین‌بودن ربات را بررسی کند." if required and not joined else ""
    return {"required": required, "joined": joined, "title": settings["title"], "invite_url": settings["invite_url"], "message": message}

async def active_events_for(session: AsyncSession):
    now = datetime.utcnow()
    rows = (await session.execute(select(ArenaEvent).where(ArenaEvent.active == True, ArenaEvent.starts_at <= now, ArenaEvent.ends_at >= now).order_by(ArenaEvent.ends_at.asc()).limit(6))).scalars().all()
    return [{"id": e.id, "title": e.title, "description": e.description, "bonus_xp": e.bonus_xp, "ends_at": e.ends_at.isoformat()} for e in rows]

@app.get("/api/bootstrap")
async def bootstrap(uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        user = await session.get(User, uid)
        today = date.today().isoformat()
        games_today = user.daily_games if user.daily_date == today else 0
        wins_today = user.daily_wins if user.daily_date == today else 0
        referral_link = f"https://t.me/{bot_username}?start=ref_{uid}" if bot_username else ""
        season = await ensure_active_season(session)
        await session.commit()
        return {
            "profile": profile_dict(user),
            "missions": [
                {"id": 0, "title": "۳ بازی امروز انجام بده", "progress": min(games_today, 3), "target": 3, "reward": 20, "claimed": "0" in (user.mission_claims if user.daily_date == today else "")},
                {"id": 1, "title": "یک مسابقه را ببر", "progress": min(wins_today, 1), "target": 1, "reward": 15, "claimed": "1" in (user.mission_claims if user.daily_date == today else "")},
                {"id": 2, "title": "۵ بازی در یک روز", "progress": min(games_today, 5), "target": 5, "reward": 35, "claimed": "2" in (user.mission_claims if user.daily_date == today else "")},
            ],
            "referral_link": referral_link,
            "is_admin": uid == ADMIN_ID,
            "game_status": GAME_STATUS,
            "daily_claimed": user.last_daily == today,
            "achievement_count": int(await session.scalar(select(func.count()).select_from(UserAchievement).where(UserAchievement.user_id == uid)) or 0),
            "clan": await current_clan(session, uid),
            "vip_tier": user.vip_tier or "none",
            "active_events": await active_events_for(session),
            "season": {"id": season.id, "name": season.name, "starts_at": season.starts_at.isoformat(), "ends_at": season.ends_at.isoformat(), "ends_in_days": max(0, (season.ends_at - datetime.utcnow()).days)},
        }


def profile_dict(user: User):
    nxt = next_league(user.xp)
    return {
        "id": user.id, "name": user.first_name, "username": user.username,
        "photo_url": user.photo_url, "coins": int(user.coins or 0), "level": max(1, int(user.xp or 0) // 100 + 1),
        "xp": user.xp, "games": user.games, "wins": user.wins,
        "losses": user.losses, "streak": user.streak,
        "league": league_for(user.xp), "next_league": nxt,
        "win_rate": round((user.wins / user.games) * 100) if user.games else 0,
        "is_verified": bool(getattr(user, "is_verified", False)),
        "is_owner": user.id == ADMIN_ID,
        "vip_tier": getattr(user, "vip_tier", "none") or "none",
        "last_seen_at": user.last_seen_at.isoformat() if getattr(user, "last_seen_at", None) else None,
        "equipped_avatar_id": getattr(user, "equipped_avatar_id", None),
        "equipped_character_id": getattr(user, "equipped_character_id", None),
        "custom_character_url": getattr(user, "custom_character_url", None),
        # A fixed, bundled render is used for the owner and is not dependent on user uploads.
        "owner_character_url": (user.custom_character_url or "/static/owner/royal-throne.glb?v=3.0.0") if user.id == ADMIN_ID else None,
        "equipped_frame_id": getattr(user, "equipped_frame_id", None),
        "equipped_badge_id": getattr(user, "equipped_badge_id", None),
        "equipped_gift_id": getattr(user, "equipped_gift_id", None),
        "equipped_showcase_id": getattr(user, "equipped_showcase_id", None),
    }

@app.get("/api/users/{user_id}/public-profile")
async def public_profile(user_id: int, uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        if await is_blocked_between(session, uid, user_id):
            raise HTTPException(403, "نمایش این پروفایل به‌دلیل تنظیمات مسدودسازی در دسترس نیست.")
        user = await session.get(User, user_id)
        if not user:
            raise HTTPException(404, "پروفایل پیدا نشد.")
        result = profile_dict(user)
        result.pop("coins", None)
        cosmetic_ids = [user.equipped_character_id or user.equipped_avatar_id, user.equipped_frame_id, user.equipped_badge_id,
                        user.equipped_gift_id, user.equipped_showcase_id]
        products = (await session.execute(select(Product).where(Product.id.in_([x for x in cosmetic_ids if x])))).scalars().all() if any(cosmetic_ids) else []
        cosmetics = {str(product.id): {"id": product.id, "name": product.name, "category": product.category,
                                      "image_url": product.image_url, "rarity": product.rarity} for product in products}
        return {"profile": result, "cosmetics": cosmetics}

@app.get("/api/leaderboard")
async def leaderboard(period: str = "all", uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        if period == "season":
            season = await ensure_active_season(session)
            await session.commit()
            rows = (await session.execute(select(SeasonScore, User).join(User, User.id == SeasonScore.user_id).where(SeasonScore.season_id == season.id).order_by(SeasonScore.points.desc(), SeasonScore.wins.desc()).limit(50))).all()
            users = [(user, int(score.points or 0)) for score, user in rows]
            mine = await session.scalar(select(SeasonScore.points).where(SeasonScore.season_id == season.id, SeasonScore.user_id == uid)) or 0
            rank_count = await session.scalar(select(func.count()).select_from(select(SeasonScore.user_id).where(SeasonScore.season_id == season.id, SeasonScore.points > mine).subquery())) or 0
            rank = int(rank_count) + 1
        elif period in ("week", "month"):
            since = datetime.utcnow() - (timedelta(days=7) if period == "week" else timedelta(days=30))
            totals = await session.execute(select(GameRecord.user_id, func.sum(GameRecord.xp).label("score")).where(GameRecord.created_at >= since).group_by(GameRecord.user_id).order_by(func.sum(GameRecord.xp).desc()).limit(50))
            rows = totals.all()
            ids = [row.user_id for row in rows]
            users_by_id = {u.id: u for u in (await session.execute(select(User).where(User.id.in_(ids)))).scalars().all()} if ids else {}
            users = [(users_by_id[row.user_id], int(row.score or 0)) for row in rows if row.user_id in users_by_id]
            mine = await session.scalar(select(func.coalesce(func.sum(GameRecord.xp), 0)).where(GameRecord.user_id == uid, GameRecord.created_at >= since)) or 0
            rank_count = await session.scalar(select(func.count()).select_from(select(GameRecord.user_id).where(GameRecord.created_at >= since).group_by(GameRecord.user_id).having(func.sum(GameRecord.xp) > mine).subquery())) or 0
            rank = int(rank_count) + 1
        else:
            result = await session.execute(select(User).order_by(User.xp.desc(), User.wins.desc()).limit(50))
            raw = result.scalars().all()
            users = [(u, u.xp) for u in raw]
            me = await session.get(User, uid)
            rank_count = await session.scalar(select(func.count()).select_from(User).where(User.xp > me.xp))
            rank = int(rank_count or 0) + 1
        return {"users": [{"rank": i + 1, "id": u.id, "name": u.first_name, "xp": score, "league": league_for(u.xp), "is_me": u.id == uid, "is_verified": bool(u.is_verified), "is_owner": u.id == ADMIN_ID} for i, (u, score) in enumerate(users)], "my_rank": rank, "period": period}

@app.post("/api/daily-claim")
async def daily_claim(uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        user = await session.get(User, uid)
        today = date.today().isoformat()
        if user.last_daily == today:
            return {"ok": False, "message": "جایزه امروزت رو قبلاً گرفتی."}
        yesterday = (date.today().fromordinal(date.today().toordinal() - 1)).isoformat()
        user.streak = user.streak + 1 if user.last_daily == yesterday else 1
        user.last_daily = today
        reward = random.randint(20, 35) + min(user.streak, 7) * 2
        await grant_xp(session, user, reward, "جایزه ورود روزانه")
        await unlock_achievements(session, user)
        await session.commit()
        return {"ok": True, "reward": reward, "streak": user.streak, "profile": profile_dict(user)}

class MissionClaim(BaseModel):
    mission_id: int = Field(ge=0, le=2)

@app.post("/api/missions/claim")
async def mission_claim(body: MissionClaim, uid: int = Depends(require_user_id)):
    rewards = {0: (3, 20), 1: (None, 15), 2: (5, 35)}
    async with SessionLocal() as session:
        user = await session.get(User, uid)
        today = date.today().isoformat()
        if user.daily_date != today:
            user.daily_date = today
            user.daily_games = 0
            user.daily_wins = 0
            user.mission_claims = ""
        claimed = set(user.mission_claims or "")
        key = str(body.mission_id)
        if key in claimed:
            raise HTTPException(400, "جایزه این مأموریت را قبلاً گرفتی.")
        required_games, reward = rewards[body.mission_id]
        complete = (user.daily_wins >= 1) if body.mission_id == 1 else (user.daily_games >= required_games)
        if not complete:
            raise HTTPException(400, "هنوز مأموریت کامل نشده است.")
        claimed.add(key)
        user.mission_claims = "".join(sorted(claimed))
        await grant_xp(session, user, reward, "جایزه مأموریت")
        await session.commit()
        return {"ok": True, "reward": reward, "profile": profile_dict(user)}

def ensure_game_enabled(game: str):
    if not GAME_STATUS.get(game, True):
        raise HTTPException(403, "این بازی موقتاً توسط مدیریت غیرفعال شده است.")

@app.post("/api/games/math/start")
async def math_start(uid: int = Depends(require_user_id)):
    ensure_game_enabled("math")
    a, b = random.randint(4, 30), random.randint(2, 15)
    op = random.choice(["+", "−", "×", "÷"])
    if op == "+": answer = a + b
    elif op == "−": answer = a - b
    elif op == "×": answer = a * b
    else:
        answer = a
        a, b = a * b, b
    question = f"{a} {op} {b} = ?"
    cid = secrets.token_urlsafe(16)
    async with SessionLocal() as session:
        session.add(Challenge(id=cid, user_id=uid, game="math", payload=json.dumps({"answer": str(answer), "question": question}, ensure_ascii=False)))
        await session.commit()
    return {"challenge_id": cid, "question": question, "seconds": 45}

@app.post("/api/games/math/answer")
async def math_answer(body: MathAnswer, uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        challenge = await session.get(Challenge, body.challenge_id)
        if not challenge or challenge.user_id != uid or challenge.game != "math" or challenge.completed:
            raise HTTPException(404, "این سؤال معتبر نیست یا قبلاً پاسخ داده شده است.")
        challenge.completed = True
        data = json.loads(challenge.payload)
        expired = (datetime.utcnow() - challenge.created_at).total_seconds() > 45
        correct = not expired and body.answer.strip() == data["answer"]
        user = await session.get(User, uid)
        await record_game(session, user, 12 if correct else 0, correct, "math")
        return {"correct": correct, "expired": expired, "answer": data["answer"], "earned": 12 if correct else 0, "profile": profile_dict(user)}

@app.post("/api/games/iq/start")
async def iq_start(uid: int = Depends(require_user_id)):
    ensure_game_enabled("iq")
    bank = [
        {"q": "کدام عدد بعدی است؟ ۲، ۴، ۸، ۱۶، ...", "options": ["۱۸", "۲۴", "۳۲", "۳۶"], "answer": "۳۲"},
        {"q": "اگر امروز دوشنبه باشد، ۱۰ روز دیگر چه روزی است؟", "options": ["سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"], "answer": "پنجشنبه"},
        {"q": "کدام مورد با بقیه متفاوت است؟", "options": ["مثلث", "مربع", "دایره", "مستطیل"], "answer": "دایره"},
        {"q": "نصفِ نصفِ ۸۰ چند است؟", "options": ["۱۰", "۲۰", "۳۰", "۴۰"], "answer": "۲۰"},
    ]
    item = random.choice(bank)
    cid = secrets.token_urlsafe(16)
    async with SessionLocal() as session:
        session.add(Challenge(id=cid, user_id=uid, game="iq", payload=json.dumps(item, ensure_ascii=False)))
        await session.commit()
    return {"challenge_id": cid, "question": item["q"], "options": item["options"]}

@app.post("/api/games/iq/answer")
async def iq_answer(body: IQAnswer, uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        challenge = await session.get(Challenge, body.challenge_id)
        if not challenge or challenge.user_id != uid or challenge.game != "iq" or challenge.completed:
            raise HTTPException(404, "این سؤال معتبر نیست یا قبلاً پاسخ داده شده است.")
        challenge.completed = True
        data = json.loads(challenge.payload)
        correct = body.answer == data["answer"]
        user = await session.get(User, uid)
        await record_game(session, user, 15 if correct else 0, correct, "iq")
        return {"correct": correct, "answer": data["answer"], "earned": 15 if correct else 0, "profile": profile_dict(user)}

@app.post("/api/games/sports/play")
async def sports_play(body: SportsPlay, uid: int = Depends(require_user_id)):
    ensure_game_enabled(body.game)
    if body.game == "penalty":
        if body.choice not in ["left", "center", "right"]: raise HTTPException(400, "انتخاب نامعتبر است.")
        keeper = random.choice(["left", "center", "right"])
        won = keeper != body.choice
        message = "گل شد! دروازه‌بان جهت اشتباه رفت." if won else "دروازه‌بان توپ رو مهار کرد!"
        earned = 14 if won else 0
    elif body.game == "basketball":
        if body.choice not in ["free", "three"]: raise HTTPException(400, "انتخاب نامعتبر است.")
        won = random.random() < (0.74 if body.choice == "free" else 0.40)
        message = "توپ داخل حلقه! چه پرتابی!" if won else "این پرتاب وارد سبد نشد."
        earned = 12 if won else 0
    elif body.game == "volleyball":
        if body.choice not in ["serve", "spike", "block"]: raise HTTPException(400, "انتخاب نامعتبر است.")
        won = random.random() < {"serve": 0.65, "spike": 0.58, "block": 0.52}[body.choice]
        message = "امتیاز برای تیم تو! عالی بود." if won else "حریف توپ رو برگردوند؛ دوباره تلاش کن."
        earned = 13 if won else 0
    else:
        raise HTTPException(400, "نوع بازی ناشناخته است.")
    async with SessionLocal() as session:
        user = await session.get(User, uid)
        await record_game(session, user, earned, won, body.game)
        return {"won": won, "message": message, "earned": earned, "profile": profile_dict(user)}

@app.post("/api/games/ttt/start")
async def ttt_start(uid: int = Depends(require_user_id)):
    ensure_game_enabled("ttt")
    cid = secrets.token_urlsafe(16)
    board = ["" for _ in range(9)]
    async with SessionLocal() as session:
        session.add(Challenge(id=cid, user_id=uid, game="ttt", payload=json.dumps({"board": board}, ensure_ascii=False)))
        await session.commit()
    return {"challenge_id": cid, "board": board, "message": "تو با ❌ بازی می‌کنی؛ نوبت توئه!"}

def has_line(board, mark):
    lines = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
    return any(all(board[i] == mark for i in line) for line in lines)

def bot_ttt_move(board, difficulty: str = "hard"):
    empty = [i for i, x in enumerate(board) if not x]
    if not empty:
        return None
    if difficulty == "easy" or (difficulty == "medium" and random.random() < 0.35):
        return random.choice(empty)
    for mark in ["⭕", "❌"]:
        for i in empty:
            test = board.copy(); test[i] = mark
            if has_line(test, mark): return i
    if 4 in empty: return 4
    corners = [i for i in [0,2,6,8] if i in empty]
    if corners: return random.choice(corners)
    return random.choice(empty) if empty else None

@app.post("/api/games/ttt/move")
async def ttt_move(body: TTTMove, uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        challenge = await session.get(Challenge, body.challenge_id)
        if not challenge or challenge.user_id != uid or challenge.game != "ttt" or challenge.completed:
            raise HTTPException(404, "این بازی معتبر نیست یا تمام شده است.")
        data = json.loads(challenge.payload)
        board = data["board"]
        if board[body.index]: raise HTTPException(400, "این خانه پر است.")
        board[body.index] = "❌"
        status = "playing"
        if has_line(board, "❌"):
            status = "win"; challenge.completed = True
        elif all(board):
            status = "draw"; challenge.completed = True
        else:
            move = bot_ttt_move(board, TTT_DIFFICULTY)
            if move is not None: board[move] = "⭕"
            if has_line(board, "⭕"):
                status = "loss"; challenge.completed = True
            elif all(board):
                status = "draw"; challenge.completed = True
        challenge.payload = json.dumps({"board": board}, ensure_ascii=False)
        if status != "playing":
            user = await session.get(User, uid)
            award = 25 if status == "win" else 5 if status == "draw" else 0
            await record_game(session, user, award, status == "win", "ttt")
        else:
            await session.commit()
        return {"board": board, "status": status, "earned": 25 if status == "win" else 5 if status == "draw" else 0,
                "message": {"playing": "نوبت توئه!", "win": "بردی! ۲۵ امتیاز گرفتی 🎉", "draw": "مساوی شد؛ ۵ امتیاز گرفتی.", "loss": "ربات این دور رو برد. دوباره تلاش کن!"}[status]}


def current_clan_query(session: AsyncSession, uid: int):
    return select(Clan).join(ClanMember, ClanMember.clan_id == Clan.id).where(ClanMember.user_id == uid)

async def current_clan(session: AsyncSession, uid: int):
    clan = await session.scalar(current_clan_query(session, uid))
    if not clan:
        return None
    count = await session.scalar(select(func.count()).select_from(ClanMember).where(ClanMember.clan_id == clan.id))
    member = await session.scalar(select(ClanMember).where(ClanMember.clan_id == clan.id, ClanMember.user_id == uid))
    return {"id": clan.id, "name": clan.name, "description": clan.description, "motto": clan.motto, "xp": clan.xp, "level": clan.level, "members": int(count or 0), "owner_id": clan.owner_id, "role": member.role if member else "member"}

@app.get("/api/games/guess/start")
async def guess_start(uid: int = Depends(require_user_id)):
    ensure_game_enabled("guess")
    secret = random.randint(1, 50)
    cid = secrets.token_urlsafe(16)
    async with SessionLocal() as session:
        session.add(Challenge(id=cid, user_id=uid, game="guess", payload=json.dumps({"secret": secret, "attempts": 7, "used": 0})))
        await session.commit()
    return {"challenge_id": cid, "attempts": 7, "message": "عدد مخفی بین ۱ تا ۵۰ را در ۷ تلاش پیدا کن."}

@app.post("/api/games/guess/attempt")
async def guess_attempt(body: GuessAttempt, uid: int = Depends(require_user_id)):
    ensure_game_enabled("guess")
    async with SessionLocal() as session:
        challenge = await session.get(Challenge, body.challenge_id)
        if not challenge or challenge.user_id != uid or challenge.game != "guess" or challenge.completed:
            raise HTTPException(404, "این مرحله معتبر نیست یا تمام شده است.")
        data = json.loads(challenge.payload)
        data["used"] += 1
        correct = body.guess == data["secret"]
        finished = correct or data["used"] >= data["attempts"]
        challenge.payload = json.dumps(data)
        if finished:
            challenge.completed = True
            user = await session.get(User, uid)
            won = bool(correct)
            earned = 20 if won else 0
            await record_game(session, user, earned, won, "guess")
        else:
            await session.commit()
            earned = 0
        return {"correct": correct, "finished": finished, "attempts_left": data["attempts"] - data["used"], "hint": "بالاتر" if body.guess < data["secret"] else "پایین‌تر" if body.guess > data["secret"] else "درست", "answer": data["secret"] if finished else None, "earned": earned, "profile": profile_dict(user) if finished else None}

@app.post("/api/games/memory/start")
async def memory_start(body: MemoryStart, uid: int = Depends(require_user_id)):
    ensure_game_enabled("memory")
    if body.pairs not in (6, 8, 12):
        raise HTTPException(400, "سطح بازی معتبر نیست؛ ۶، ۸ یا ۱۲ جفت را انتخاب کن.")
    symbols = ["🍒", "⭐", "🚀", "🎲", "💎", "🎯", "🍀", "🔥", "🪐", "🧿", "⚡", "🦊"]
    deck = symbols[:body.pairs] * 2
    random.shuffle(deck)
    cid = secrets.token_urlsafe(18)
    payload = {"deck": deck, "pairs_total": body.pairs, "matched": [], "first_index": None, "attempts": 0, "started_at": time.time()}
    async with SessionLocal() as session:
        session.add(Challenge(id=cid, user_id=uid, game="memory", payload=json.dumps(payload, ensure_ascii=False)))
        await session.commit()
    return {"challenge_id": cid, "card_count": len(deck), "pairs": body.pairs, "symbols": body.pairs, "mode": "match-pairs"}

@app.post("/api/games/memory/flip")
async def memory_flip(body: MemoryFlip, uid: int = Depends(require_user_id)):
    ensure_game_enabled("memory")
    async with SessionLocal() as session:
        challenge = await session.scalar(select(Challenge).where(Challenge.id == body.challenge_id).with_for_update())
        if not challenge or challenge.user_id != uid or challenge.game != "memory" or challenge.completed:
            raise HTTPException(404, "این صفحه معتبر نیست یا قبلاً تمام شده است.")
        data = json.loads(challenge.payload or "{}")
        deck = data.get("deck", [])
        if body.index >= len(deck):
            raise HTTPException(400, "شماره کارت معتبر نیست.")
        matched = set(data.get("matched", []))
        if body.index in matched:
            raise HTTPException(400, "این جفت قبلاً پیدا شده است.")
        first = data.get("first_index")
        if first is None:
            data["first_index"] = body.index
            challenge.payload = json.dumps(data, ensure_ascii=False)
            await session.commit()
            return {"state": "one", "revealed": [{"index": body.index, "symbol": deck[body.index]}], "matched": len(matched)//2, "attempts": data["attempts"]}
        if body.index == first:
            raise HTTPException(400, "یک کارت را دوبار انتخاب نکن.")
        data["attempts"] = int(data.get("attempts", 0)) + 1
        first_symbol, second_symbol = deck[first], deck[body.index]
        is_match = first_symbol == second_symbol
        if is_match:
            matched.update((first, body.index))
            data["matched"] = sorted(matched)
        data["first_index"] = None
        finished = len(matched) == len(deck)
        earned = 0
        user = await session.get(User, uid)
        if finished:
            challenge.completed = True
            pairs_total = int(data.get("pairs_total", 8))
            earned = max(15, 48 + (pairs_total - 8) * 5 - max(0, data["attempts"] - pairs_total) * 3)
            await record_game(session, user, earned, True, "memory")
            await add_coins(session, user, 8, "جایزه تکمیل بازی حافظه")
            await session.commit()
        else:
            challenge.payload = json.dumps(data, ensure_ascii=False)
            await session.commit()
        return {"state": "match" if is_match else "miss", "revealed": [{"index": first, "symbol": first_symbol}, {"index": body.index, "symbol": second_symbol}], "matched": len(matched)//2, "attempts": data["attempts"], "finished": finished, "earned": earned, "bonus_coins": 8 if finished else 0, "profile": profile_dict(user) if finished else None}

# Neon Breakout: real-time canvas arcade game. The server records each challenge once and caps rewards by elapsed server time.
@app.post("/api/games/neon-breakout/start")
async def neon_breakout_start(uid: int = Depends(require_user_id)):
    ensure_game_enabled("neon-breakout")
    cid = secrets.token_urlsafe(18)
    payload = {"started_at": time.time(), "version": 1}
    async with SessionLocal() as session:
        session.add(Challenge(id=cid, user_id=uid, game="neon-breakout", payload=json.dumps(payload)))
        await session.commit()
    return {"challenge_id": cid, "levels": 3, "bricks_per_level": 32}

@app.post("/api/games/neon-breakout/finish")
async def neon_breakout_finish(body: BreakoutFinish, uid: int = Depends(require_user_id)):
    ensure_game_enabled("neon-breakout")
    async with SessionLocal() as session:
        challenge = await session.scalar(select(Challenge).where(Challenge.id == body.challenge_id).with_for_update())
        if not challenge or challenge.user_id != uid or challenge.game != "neon-breakout" or challenge.completed:
            raise HTTPException(404, "این دور معتبر نیست یا قبلاً ثبت شده است.")
        data = json.loads(challenge.payload or "{}")
        elapsed = max(0.0, time.time() - float(data.get("started_at", time.time())))
        if elapsed < 5:
            raise HTTPException(400, "برای ثبت نتیجه، حداقل ۵ ثانیه بازی کن.")
        if elapsed > 900:
            challenge.completed = True
            await session.commit()
            raise HTTPException(400, "زمان این مرحله تمام شده است؛ یک دور تازه شروع کن.")
        # A generous time-based ceiling discourages forged client-side scores.
        score = min(body.score, int(elapsed * 75) + 200)
        won = score >= 1200
        earned_xp = min(70, score // 55) if won else min(25, score // 100)
        bonus_coins = min(40, score // 110) if won else min(8, score // 250)
        challenge.completed = True
        user = await session.get(User, uid)
        await record_game(session, user, earned_xp, won, "neon-breakout")
        if bonus_coins:
            await add_coins(session, user, bonus_coins, "جایزه NEON BREAKOUT")
            await session.commit()
        return {"score": score, "won": won, "earned": earned_xp, "bonus_coins": bonus_coins,
                "duration_seconds": int(elapsed), "profile": profile_dict(user)}

# Neon Runner: a compact side-scrolling reaction platformer. The server validates every segment.
def make_runner_course():
    course = []
    for idx in range(12):
        kind = random.choices(["clear", "crate", "gap", "drone"], weights=[35, 25, 22, 18])[0]
        coin = random.random() < 0.48
        course.append({"kind": kind, "coin": coin})
    return course

def runner_view(data, status="playing", earned=0, message=""):
    item = data["course"][data["step"]] if data["step"] < len(data["course"]) else None
    return {"step": data["step"], "total": len(data["course"]), "hearts": data["hearts"], "coins": data["coins"], "score": data["score"], "next": item, "status": status, "earned": earned, "message": message}

@app.post("/api/games/neon-runner/start")
async def neon_runner_start(uid: int = Depends(require_user_id)):
    ensure_game_enabled("neon-runner")
    data = {"course": make_runner_course(), "step": 0, "hearts": 3, "coins": 0, "score": 0}
    cid = secrets.token_urlsafe(16)
    async with SessionLocal() as session:
        session.add(Challenge(id=cid, user_id=uid, game="neon-runner", payload=json.dumps(data)))
        await session.commit()
    return {"challenge_id": cid, **runner_view(data), "message": "برای هر مانع، حرکت درست را انتخاب کن؛ کریستال‌ها را هم جمع کن."}

@app.post("/api/games/neon-runner/action")
async def neon_runner_action(body: RunnerAction, uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        challenge = await session.get(Challenge, body.challenge_id)
        if not challenge or challenge.user_id != uid or challenge.game != "neon-runner" or challenge.completed:
            raise HTTPException(404, "این دور معتبر نیست یا تمام شده است.")
        data = json.loads(challenge.payload)
        if data["step"] >= len(data["course"]):
            raise HTTPException(400, "مسیر تمام شده است.")
        obstacle = data["course"][data["step"]]
        required = {"crate": "jump", "gap": "jump", "drone": "slide", "clear": None}[obstacle["kind"]]
        success = required is None or body.action == required
        if success:
            data["score"] += 10
            if obstacle["coin"]:
                data["coins"] += 1
                data["score"] += 25
        else:
            data["hearts"] -= 1
        data["step"] += 1
        finished = data["hearts"] <= 0 or data["step"] >= len(data["course"])
        challenge.payload = json.dumps(data)
        earned = 0
        status = "playing"
        profile = None
        if finished:
            challenge.completed = True
            won = data["hearts"] > 0
            earned = (15 + data["coins"] * 3 + data["score"] // 12) if won else max(0, data["score"] // 20)
            user = await session.get(User, uid)
            await record_game(session, user, earned, won, "neon-runner")
            status = "won" if won else "lost"
            profile = profile_dict(user)
        else:
            await session.commit()
        message = "عالی! مسیر رو رد کردی." if success else "برخورد کردی؛ یک قلب کم شد!"
        return {**runner_view(data, status, earned, message), "success": success, "profile": profile}

@app.post("/api/games/arcade/start")
async def arcade_start(body: ArcadeStart, uid: int = Depends(require_user_id)):
    game = body.game
    ensure_game_enabled(game)
    async with SessionLocal() as session:
        challenge_id = secrets.token_hex(16)
        session.add(Challenge(id=challenge_id, user_id=uid, game=game, payload=json.dumps({"started_at": datetime.utcnow().isoformat()})))
        await session.commit()
        return {"challenge_id": challenge_id, "game": game, "duration_limit_seconds": 180}

@app.post("/api/games/arcade/finish")
async def arcade_finish(body: ArcadeFinish, uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        challenge = await session.get(Challenge, body.challenge_id)
        if not challenge or challenge.user_id != uid or challenge.game not in ("space-shooter", "neon-drift"):
            raise HTTPException(404, "نشست بازی پیدا نشد.")
        if challenge.completed:
            raise HTTPException(409, "نتیجه این بازی قبلاً ثبت شده است.")
        elapsed = max(0, int((datetime.utcnow() - challenge.created_at).total_seconds()))
        if elapsed < 8:
            raise HTTPException(400, "برای ثبت نتیجه باید حداقل ۸ ثانیه بازی کنی.")
        if elapsed > 240:
            elapsed = 240
        max_plausible_score = elapsed * 18
        if body.score > max_plausible_score:
            await flag_security_event(uid, "arcade_score_outlier", f"امتیاز غیرعادی در {challenge.game}: {body.score} طی {elapsed} ثانیه", "medium", {"game": challenge.game, "score": body.score, "elapsed": elapsed})
        score = min(body.score, max_plausible_score)
        xp = min(60, score // 12 + elapsed // 20)
        won = score >= 100
        challenge.completed = True
        user = await session.get(User, uid)
        await record_game(session, user, xp, won, challenge.game)
        return {"ok": True, "score": score, "earned_xp": xp, "won": won, "profile": profile_dict(user)}

@app.get("/api/shop/products")
async def shop_products(uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        # Owner rewards, gifts and packs are intentionally never purchasable.
        products = (await session.execute(select(Product).where(
            Product.active == True, Product.reward_only == False,
            Product.category.notin_(["pack", "gift", "item"])
        ).order_by(Product.price_coins))).scalars().all()
        return {"products": [{"id": x.id, "name": x.name, "description": x.description, "category": x.category,
                              "rarity": x.rarity, "price_coins": x.price_coins, "image_url": x.image_url}
                             for x in products]}

@app.post("/api/shop/buy")
async def shop_buy(body: BuyItem, uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.id == uid).with_for_update())
        product = await session.get(Product, body.product_id)
        if not product or not product.active:
            raise HTTPException(404, "این محصول دیگر در فروشگاه موجود نیست.")
        if product.reward_only or product.category in ("pack", "gift", "item"):
            await flag_security_event(uid, "restricted_reward_purchase", f"تلاش برای خرید آیتم جایزه‌ای {product.id}", "medium", {"product_id": product.id})
            raise HTTPException(403, "این آیتم جایزه اختصاصی است و فقط مالک می‌تواند آن را اعطا کند.")
        if user.coins < product.price_coins:
            raise HTTPException(400, "موجودی سکه کافی نیست.")
        user.coins -= product.price_coins
        session.add(WalletTransaction(user_id=uid, amount=-product.price_coins, reason=f"خرید {product.name}", balance_after=user.coins))
        item = await session.scalar(select(InventoryItem).where(InventoryItem.user_id == uid, InventoryItem.product_id == product.id))
        if item:
            item.quantity += 1
        else:
            session.add(InventoryItem(user_id=uid, product_id=product.id, quantity=1))
        session.add(InventoryTransaction(user_id=uid, product_id=product.id, product_name=product.name,
                                         action="purchase", quantity=1, details="خرید از فروشگاه با سکه"))
        await session.commit()
        return {"ok": True, "profile": profile_dict(user), "message": f"{product.name} به کوله‌پشتی اضافه شد."}

@app.get("/api/shop/inventory")
async def shop_inventory(uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        user = await session.get(User, uid)
        rows = await session.execute(select(InventoryItem, Product).join(Product, Product.id == InventoryItem.product_id).where(InventoryItem.user_id == uid).order_by(InventoryItem.purchased_at.desc()))
        equipped = {"character": user.equipped_character_id or user.equipped_avatar_id, "frame": user.equipped_frame_id,
                    "badge": user.equipped_badge_id, "gift": user.equipped_gift_id, "showcase": user.equipped_showcase_id}
        items = []
        for item, product in rows.all():
            category = "character" if product.category in ("avatar", "skin") else product.category
            slot = category if category in ("character", "frame", "badge", "gift") else ("pack" if category == "pack" else "showcase")
            items.append({"id": item.id, "product_id": product.id, "name": product.name, "description": product.description,
                          "category": category, "rarity": product.rarity, "image_url": product.image_url,
                          "quantity": item.quantity, "purchased_at": item.purchased_at.isoformat(),
                          "equip_slot": slot, "equipped": equipped.get(slot) == product.id,
                          "is_pack": category == "pack", "reward_only": bool(product.reward_only)})
        return {"items": items, "equipped": equipped}

@app.post("/api/profile/equip")
async def profile_equip(body: EquipItem, uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        inventory = await session.scalar(select(InventoryItem).where(InventoryItem.user_id == uid, InventoryItem.product_id == body.product_id))
        product = await session.get(Product, body.product_id)
        if not inventory or not product:
            raise HTTPException(404, "این آیتم در کوله‌پشتی تو نیست.")
        category = "character" if product.category in ("avatar", "skin") else product.category
        if category == "pack":
            raise HTTPException(400, "بسته جایزه قابل تجهیز نیست؛ آن را باز کن.")
        slot = category if category in ("character", "frame", "badge", "gift") else "showcase"
        field = {"character": "equipped_character_id", "frame": "equipped_frame_id", "badge": "equipped_badge_id",
                 "gift": "equipped_gift_id", "showcase": "equipped_showcase_id"}[slot]
        user = await session.get(User, uid)
        setattr(user, field, None if getattr(user, field) == product.id else product.id)
        if slot == "character":
            user.equipped_avatar_id = user.equipped_character_id
            user.custom_character_url = None
        await session.commit()
        return {"ok": True, "slot": slot, "equipped": getattr(user, field), "profile": profile_dict(user)}

@app.post("/api/shop/packs/open")
async def open_reward_pack(body: OpenPackInput, uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        pack = await session.get(Product, body.product_id)
        inventory = await session.scalar(select(InventoryItem).where(
            InventoryItem.user_id == uid, InventoryItem.product_id == body.product_id).with_for_update())
        if not pack or pack.category != "pack" or not inventory or inventory.quantity < 1:
            await flag_security_event(uid, "unauthorized_pack_open", f"تلاش برای بازکردن بسته بدون مالکیت؛ محصول {body.product_id}", "medium", {"product_id": body.product_id})
            raise HTTPException(404, "بسته‌ای با این مشخصات در کوله‌پشتی وجود ندارد.")
        try:
            contents = json.loads(pack.bundle_items or "[]")
        except (TypeError, json.JSONDecodeError):
            contents = []
        if not contents:
            raise HTTPException(400, "این بسته هنوز محتویات معتبری ندارد؛ به مالک اطلاع بده.")
        inventory.quantity -= 1
        if inventory.quantity <= 0:
            await session.delete(inventory)
        normalized_contents = {}
        for entry in contents:
            try:
                product_id = int(entry.get("product_id", 0))
                quantity = max(1, min(100, int(entry.get("quantity", 1))))
            except (AttributeError, TypeError, ValueError):
                continue
            if product_id > 0 and product_id != pack.id:
                normalized_contents[product_id] = min(100, normalized_contents.get(product_id, 0) + quantity)
        received = []
        for product_id, quantity in normalized_contents.items():
            product = await session.get(Product, product_id)
            if not product or product.category == "pack":
                continue
            owned = await session.scalar(select(InventoryItem).where(
                InventoryItem.user_id == uid, InventoryItem.product_id == product_id))
            if owned:
                owned.quantity += quantity
            else:
                session.add(InventoryItem(user_id=uid, product_id=product_id, quantity=quantity))
            received.append({"name": product.name, "quantity": quantity, "product_id": product.id})
        if not received:
            raise HTTPException(400, "محتویات این بسته در دسترس نیست.")
        session.add(InventoryTransaction(user_id=uid, product_id=pack.id, product_name=pack.name,
                                         action="pack_open", quantity=1, details="بازکردن بسته جایزه"))
        for reward in received:
            session.add(InventoryTransaction(user_id=uid, product_id=reward["product_id"], product_name=reward["name"],
                                             action="pack_reward", quantity=reward["quantity"],
                                             details=f"دریافت از بسته {pack.name}"))
        await session.commit()
        return {"ok": True, "received": received, "message": "بسته با موفقیت باز شد."}

async def collect_economy_transactions(session: AsyncSession, user_id: Optional[int], limit: int):
    wallet_stmt = select(WalletTransaction, User).join(User, User.id == WalletTransaction.user_id)
    item_stmt = select(InventoryTransaction, User).join(User, User.id == InventoryTransaction.user_id)
    if user_id:
        wallet_stmt = wallet_stmt.where(WalletTransaction.user_id == user_id)
        item_stmt = item_stmt.where(InventoryTransaction.user_id == user_id)
    wallet_rows = (await session.execute(wallet_stmt.order_by(WalletTransaction.created_at.desc()).limit(limit))).all()
    item_rows = (await session.execute(item_stmt.order_by(InventoryTransaction.created_at.desc()).limit(limit))).all()
    feed = []
    for txn, user in wallet_rows:
        feed.append((txn.created_at, {"kind": "wallet", "user_id": txn.user_id, "name": user.first_name,
                      "username": user.username, "amount": txn.amount, "reason": txn.reason,
                      "balance_after": txn.balance_after, "created_at": txn.created_at.isoformat()}))
    for txn, user in item_rows:
        feed.append((txn.created_at, {"kind": "item", "user_id": txn.user_id, "name": user.first_name,
                      "username": user.username, "product_name": txn.product_name, "action": txn.action,
                      "quantity": txn.quantity, "details": txn.details, "created_at": txn.created_at.isoformat()}))
    feed.sort(key=lambda item: item[0], reverse=True)
    return [payload for _, payload in feed[:limit]]

@app.get("/api/wallet/transactions")
async def wallet_transactions(uid: int = Depends(require_user_id)):
    # The full economy ledger is owner-only. Ordinary users only see their current balance.
    await admin_guard(uid)
    async with SessionLocal() as session:
        return {"transactions": await collect_economy_transactions(session, None, 100)}

@app.post("/api/profile/character-upload")
async def upload_custom_character(file: UploadFile = File(...), uid: int = Depends(require_user_id)):
    """Players, including the owner, may upload a GLB model or a rendered character image."""
    name = (file.filename or "").lower()
    content_type = (file.content_type or "").lower()
    allowed_images = {"image/png": (".png", b"\x89PNG\r\n\x1a\n"),
                      "image/jpeg": (".jpg", b"\xff\xd8\xff"),
                      "image/webp": (".webp", b"RIFF")}
    is_glb = name.endswith(".glb")
    spec = allowed_images.get(content_type)
    content = await file.read()
    if is_glb:
        if len(content) > 16 * 1024 * 1024 or len(content) < 20 or content[:4] != b"glTF":
            raise HTTPException(400, "فایل GLB معتبر نیست یا حجم آن بیشتر از ۱۶ مگابایت است.")
        ext = ".glb"
    elif spec:
        if len(content) > 4 * 1024 * 1024:
            raise HTTPException(400, "حجم تصویر کاراکتر حداکثر ۴ مگابایت است.")
        if not content.startswith(spec[1]) or (content_type == "image/webp" and content[8:12] != b"WEBP"):
            raise HTTPException(400, "فایل ارسالی تصویر معتبر نیست.")
        ext = spec[0]
    else:
        raise HTTPException(400, "فقط GLB، PNG، JPG یا WEBP قابل قبول است.")
    async with SessionLocal() as session:
        user = await session.get(User, uid)
        if not user:
            raise HTTPException(404, "حساب کاربری پیدا نشد.")
        old_url = user.custom_character_url
        character_dir = STATIC_DIR / "uploads" / "characters"
        character_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{uid}_{secrets.token_hex(10)}{ext}"
        target_path = character_dir / filename
        target_path.write_bytes(content)
        user.custom_character_url = f"/static/uploads/characters/{filename}"
        user.equipped_character_id = None
        user.equipped_avatar_id = None
        user_url = user.custom_character_url
        session.add(AdminAudit(admin_id=ADMIN_ID, action="owner_character_upload" if uid == ADMIN_ID else "user_character_upload", target_id=uid, detail=f"آپلود مدل شخصی ({ext})")) if uid == ADMIN_ID else None
        await session.commit()
        profile = profile_dict(user)
    if old_url and old_url.startswith("/static/uploads/characters/"):
        managed_dir = (STATIC_DIR / "uploads" / "characters").resolve()
        old_path = (STATIC_DIR / old_url.removeprefix("/static/")).resolve()
        try:
            old_path.relative_to(managed_dir)
            if old_path.is_file(): old_path.unlink()
        except (ValueError, OSError): pass
    return {"ok": True, "image_url": user_url, "profile": profile,
            "message": "کاراکتر شخصی‌ات ثبت شد. برای مالک، این مدل جایگزین فرمانروای پیش‌فرض می‌شود." if uid == ADMIN_ID else "کاراکتر شخصی‌ات در پروفایل ثبت شد."}

@app.delete("/api/profile/character-upload")
async def delete_custom_character(uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        user = await session.get(User, uid)
        if not user:
            raise HTTPException(404, "حساب کاربری پیدا نشد.")
        old_url = user.custom_character_url
        user.custom_character_url = None
        await session.commit()
        profile = profile_dict(user)
    if old_url and old_url.startswith("/static/uploads/characters/"):
        managed_dir = (STATIC_DIR / "uploads" / "characters").resolve()
        old_path = (STATIC_DIR / old_url.removeprefix("/static/")).resolve()
        try:
            old_path.relative_to(managed_dir)
            if old_path.is_file():
                old_path.unlink()
        except (ValueError, OSError):
            pass
    return {"ok": True, "profile": profile, "message": "کاراکتر شخصی برداشته شد؛ فرمانروای پیش‌فرض مالک دوباره نمایش داده می‌شود." if uid == ADMIN_ID else "کاراکتر شخصی از پروفایل برداشته شد."}

@app.get("/api/profile/history")
async def profile_history(uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        rows = (await session.execute(select(GameRecord).where(GameRecord.user_id == uid).order_by(GameRecord.created_at.desc()).limit(30))).scalars().all()
        return {"history": [{"game": x.game, "won": x.won, "xp": x.xp, "created_at": x.created_at.isoformat()} for x in rows]}

@app.get("/api/achievements")
async def achievements(uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        earned = set((await session.execute(select(UserAchievement.code).where(UserAchievement.user_id == uid))).scalars().all())
        return {"achievements": [{"code": code, "title": title, "icon": icon, "description": desc, "unlocked": code in earned} for code, title, icon, desc in ACHIEVEMENTS]}

@app.get("/api/clans")
async def clans(uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        rows = (await session.execute(select(Clan).order_by(Clan.created_at.desc()).limit(50))).scalars().all()
        result = []
        for clan in rows:
            count = await session.scalar(select(func.count()).select_from(ClanMember).where(ClanMember.clan_id == clan.id))
            owner = await session.get(User, clan.owner_id)
            result.append({"id": clan.id, "name": clan.name, "description": clan.description, "motto": clan.motto, "xp": clan.xp, "level": clan.level, "members": int(count or 0), "owner_id": clan.owner_id, "owner_name": owner.first_name if owner else "بازیکن", "owner_verified": bool(owner and owner.is_verified), "owner_is_owner": clan.owner_id == ADMIN_ID})
        return {"clans": result, "my_clan": await current_clan(session, uid)}

@app.get("/api/clans/{clan_id}/members")
async def clan_members(clan_id: int, uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        clan = await session.get(Clan, clan_id)
        if not clan:
            raise HTTPException(404, "کلن پیدا نشد.")
        rows = await session.execute(select(ClanMember, User).join(User, User.id == ClanMember.user_id).where(ClanMember.clan_id == clan_id).order_by(ClanMember.role.desc(), User.xp.desc()))
        members = [{"id": user.id, "name": user.first_name, "username": user.username, "xp": user.xp, "level": max(1, user.xp//100+1), "league": league_for(user.xp), "role": member.role, "vip_tier": user.vip_tier or "none", "online": bool(user.last_seen_at and (datetime.utcnow()-user.last_seen_at).total_seconds() < 300), "is_verified": bool(user.is_verified), "is_owner": user.id == ADMIN_ID} for member, user in rows.all()]
        return {"clan": {"id": clan.id, "name": clan.name, "description": clan.description, "owner_id": clan.owner_id}, "members": members}

@app.post("/api/clans/create")
async def clan_create(body: ClanCreate, uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        member = await session.scalar(select(ClanMember).where(ClanMember.user_id == uid))
        if member:
            raise HTTPException(400, "ابتدا از کلن فعلی خارج شو.")
        existing = await session.scalar(select(Clan).where(func.lower(Clan.name) == body.name.lower()))
        if existing:
            raise HTTPException(400, "این نام کلن قبلاً استفاده شده است.")
        clan = Clan(name=body.name, description=body.description, owner_id=uid)
        session.add(clan)
        await session.flush()
        session.add(ClanMember(clan_id=clan.id, user_id=uid, role="owner"))
        await session.commit()
        return {"ok": True, "clan": await current_clan(session, uid)}

@app.post("/api/clans/join")
async def clan_join(body: ClanJoin, uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        member = await session.scalar(select(ClanMember).where(ClanMember.user_id == uid))
        clan = await session.get(Clan, body.clan_id)
        if not clan:
            raise HTTPException(404, "کلن پیدا نشد.")
        if member:
            raise HTTPException(400, "هر بازیکن فقط می‌تواند عضو یک کلن باشد.")
        session.add(ClanMember(clan_id=clan.id, user_id=uid))
        await session.commit()
        return {"ok": True, "clan": await current_clan(session, uid)}

@app.post("/api/clans/leave")
async def clan_leave(uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        member = await session.scalar(select(ClanMember).where(ClanMember.user_id == uid))
        if not member:
            raise HTTPException(400, "عضو هیچ کلنی نیستی.")
        clan = await session.get(Clan, member.clan_id)
        if clan and clan.owner_id == uid:
            count = await session.scalar(select(func.count()).select_from(ClanMember).where(ClanMember.clan_id == clan.id))
            if count and count > 1:
                raise HTTPException(400, "برای خروج، ابتدا مالکیت کلن را منتقل کن یا اعضا را خارج کن.")
            await session.delete(clan)
        await session.delete(member)
        await session.commit()
        return {"ok": True}

@app.put("/api/clans/{clan_id}/members/{member_id}/role")
async def clan_member_role_update(clan_id: int, member_id: int, body: ClanMemberRoleInput, uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        clan = await session.get(Clan, clan_id)
        actor = await session.scalar(select(ClanMember).where(ClanMember.clan_id == clan_id, ClanMember.user_id == uid))
        target = await session.scalar(select(ClanMember).where(ClanMember.clan_id == clan_id, ClanMember.user_id == member_id))
        if not clan or not actor or actor.role != "owner" or not target or member_id == clan.owner_id:
            raise HTTPException(403, "فقط مالک کلن می‌تواند نقش اعضای دیگر را تغییر دهد.")
        target.role = body.role
        await session.commit()
        return {"ok": True, "role": target.role}

@app.delete("/api/clans/{clan_id}/members/{member_id}")
async def clan_member_remove(clan_id: int, member_id: int, uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        clan = await session.get(Clan, clan_id)
        actor = await session.scalar(select(ClanMember).where(ClanMember.clan_id == clan_id, ClanMember.user_id == uid))
        target = await session.scalar(select(ClanMember).where(ClanMember.clan_id == clan_id, ClanMember.user_id == member_id))
        if not clan or not actor or actor.role != "owner" or not target or member_id == clan.owner_id:
            raise HTTPException(403, "فقط مالک کلن می‌تواند عضو دیگری را اخراج کند.")
        await session.delete(target)
        await session.commit()
        return {"ok": True}

@app.post("/api/clans/{clan_id}/transfer")
async def clan_transfer_owner(clan_id: int, body: ClanTransferInput, uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        clan = await session.get(Clan, clan_id)
        if not clan or clan.owner_id != uid:
            raise HTTPException(403, "فقط مالک فعلی می‌تواند مالکیت کلن را منتقل کند.")
        target = await session.scalar(select(ClanMember).where(ClanMember.clan_id == clan_id, ClanMember.user_id == body.new_owner_id))
        current = await session.scalar(select(ClanMember).where(ClanMember.clan_id == clan_id, ClanMember.user_id == uid))
        if not target or body.new_owner_id == uid:
            raise HTTPException(400, "عضو جدید مالک معتبر نیست.")
        target.role = "owner"
        if current: current.role = "leader"
        clan.owner_id = body.new_owner_id
        await session.commit()
        return {"ok": True, "owner_id": clan.owner_id}

async def _clan_member_role(session: AsyncSession, uid: int, clan_id: int):
    return await session.scalar(select(ClanMember).where(ClanMember.user_id == uid, ClanMember.clan_id == clan_id))

async def _clan_battle_snapshot(session: AsyncSession, battle: ClanBattle):
    return {"id": battle.id, "challenger_clan_id": battle.challenger_clan_id, "opponent_clan_id": battle.opponent_clan_id, "status": battle.status, "challenger_score": battle.challenger_score, "opponent_score": battle.opponent_score, "winner_clan_id": battle.winner_clan_id, "starts_at": battle.starts_at.isoformat() if battle.starts_at else None, "ends_at": battle.ends_at.isoformat() if battle.ends_at else None}

async def _finalize_clan_battle(session: AsyncSession, battle: ClanBattle):
    if battle.status != "active" or not battle.ends_at or datetime.utcnow() < battle.ends_at:
        return
    for clan_id, attr in ((battle.challenger_clan_id, "challenger_score"), (battle.opponent_clan_id, "opponent_score")):
        participants = (await session.execute(select(ClanBattleParticipant.user_id).where(ClanBattleParticipant.battle_id == battle.id, ClanBattleParticipant.clan_id == clan_id))).scalars().all()
        score = 0
        if participants:
            score = int(await session.scalar(select(func.count()).select_from(GameRecord).where(GameRecord.user_id.in_(participants), GameRecord.won == True, GameRecord.created_at >= battle.starts_at, GameRecord.created_at <= battle.ends_at)) or 0)
        setattr(battle, attr, score)
    battle.status = "completed"
    if battle.challenger_score > battle.opponent_score:
        battle.winner_clan_id = battle.challenger_clan_id
    elif battle.opponent_score > battle.challenger_score:
        battle.winner_clan_id = battle.opponent_clan_id
    if battle.winner_clan_id:
        winners = (await session.execute(select(ClanBattleParticipant).where(ClanBattleParticipant.battle_id == battle.id, ClanBattleParticipant.clan_id == battle.winner_clan_id, ClanBattleParticipant.rewarded == False))).scalars().all()
        for participant in winners:
            player = await session.get(User, participant.user_id)
            if player:
                await add_coins(session, player, 30, "جایزه پیروزی نبرد کلنی")
            participant.rewarded = True

@app.get("/api/clan-battles")
async def clan_battles(uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        member = await session.scalar(select(ClanMember).where(ClanMember.user_id == uid))
        if not member:
            return {"battles": []}
        rows = (await session.execute(select(ClanBattle).where((ClanBattle.challenger_clan_id == member.clan_id) | (ClanBattle.opponent_clan_id == member.clan_id)).order_by(ClanBattle.created_at.desc()).limit(20).with_for_update())).scalars().all()
        result = []
        for battle in rows:
            if battle.status == "active" and battle.starts_at:
                until = min(datetime.utcnow(), battle.ends_at) if battle.ends_at else datetime.utcnow()
                for clan_id, attr in ((battle.challenger_clan_id, "challenger_score"), (battle.opponent_clan_id, "opponent_score")):
                    participants = (await session.execute(select(ClanBattleParticipant.user_id).where(ClanBattleParticipant.battle_id == battle.id, ClanBattleParticipant.clan_id == clan_id))).scalars().all()
                    score = 0
                    if participants:
                        score = int(await session.scalar(select(func.count()).select_from(GameRecord).where(GameRecord.user_id.in_(participants), GameRecord.won == True, GameRecord.created_at >= battle.starts_at, GameRecord.created_at <= until)) or 0)
                    setattr(battle, attr, score)
            await _finalize_clan_battle(session, battle)
            result.append(await _clan_battle_snapshot(session, battle))
        await session.commit()
        return {"battles": result}

@app.post("/api/clan-battles")
async def clan_battle_create(body: ClanBattleCreate, uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        mine = await session.scalar(select(ClanMember).where(ClanMember.user_id == uid))
        if not mine or mine.role not in ("owner", "leader"):
            raise HTTPException(403, "فقط مالک یا فرمانده کلن می‌تواند مبارزه ایجاد کند.")
        opponent = await session.get(Clan, body.opponent_clan_id)
        if not opponent or opponent.id == mine.clan_id:
            raise HTTPException(400, "کلن حریف معتبر نیست.")
        pending = await session.scalar(select(ClanBattle).where(ClanBattle.status.in_(["pending", "active"]),
            ((ClanBattle.challenger_clan_id.in_([mine.clan_id, opponent.id])) |
             (ClanBattle.opponent_clan_id.in_([mine.clan_id, opponent.id])))))
        if pending:
            raise HTTPException(400, "یکی از دو کلن در حال حاضر دعوت یا نبرد فعال دیگری دارد.")
        battle = ClanBattle(challenger_clan_id=mine.clan_id, opponent_clan_id=opponent.id, status="pending")
        session.add(battle)
        await session.commit()
        if bot:
            leader = await session.scalar(select(ClanMember.user_id).where(ClanMember.clan_id == opponent.id, ClanMember.role == "owner"))
            if leader:
                try: await bot.send_message(leader, f"⚔️ کلن شما به نبرد کلنی دعوت شده است. GAME ARENA را باز کن تا دعوت را ببینی.")
                except Exception: pass
        return {"ok": True, "battle": await _clan_battle_snapshot(session, battle)}

@app.post("/api/clan-battles/{battle_id}/respond")
async def clan_battle_respond(battle_id: int, body: ClanBattleRespond, uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        battle = await session.get(ClanBattle, battle_id)
        if not battle or battle.status != "pending":
            raise HTTPException(404, "دعوت نبرد پیدا نشد یا منقضی شده است.")
        member = await _clan_member_role(session, uid, battle.opponent_clan_id)
        if not member or member.role not in ("owner", "leader"):
            raise HTTPException(403, "فقط مالک یا فرمانده کلن حریف می‌تواند پاسخ دهد.")
        if not body.accept:
            battle.status = "rejected"
            await session.commit()
            return {"ok": True, "status": battle.status}
        now = datetime.utcnow()
        battle.status = "active"
        battle.starts_at = now
        battle.ends_at = now + timedelta(hours=24)
        for clan_id in (battle.challenger_clan_id, battle.opponent_clan_id):
            ids = (await session.execute(select(ClanMember.user_id).where(ClanMember.clan_id == clan_id))).scalars().all()
            for player_id in ids:
                session.add(ClanBattleParticipant(battle_id=battle.id, clan_id=clan_id, user_id=player_id))
        await session.commit()
        return {"ok": True, "status": battle.status, "battle": await _clan_battle_snapshot(session, battle)}

@app.get("/api/friends")
async def friends_list(uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        links = (await session.execute(select(Friendship).where((Friendship.user_low == uid) | (Friendship.user_high == uid)))).scalars().all()
        friend_ids = [x.user_high if x.user_low == uid else x.user_low for x in links]
        users = (await session.execute(select(User).where(User.id.in_(friend_ids)))).scalars().all() if friend_ids else []
        friend_rows = [{"id": u.id, "name": u.first_name, "username": u.username, "online": bool(u.last_seen_at and (datetime.utcnow()-u.last_seen_at).total_seconds() < 300), "vip_tier": u.vip_tier or "none", "is_verified": bool(u.is_verified)} for u in users]
        reqs = (await session.execute(select(FriendRequest).where(FriendRequest.status == "pending", ((FriendRequest.target_id == uid) | (FriendRequest.requester_id == uid))).order_by(FriendRequest.created_at.desc()).limit(50))).scalars().all()
        requests = []
        for r in reqs:
            other_id = r.requester_id if r.target_id == uid else r.target_id
            other = await session.get(User, other_id)
            requests.append({"id": r.id, "other_id": other_id, "other_name": other.first_name if other else "بازیکن", "incoming": r.target_id == uid})
        return {"friends": friend_rows, "requests": requests}

@app.post("/api/friends/request")
async def friend_request_create(body: FriendRequestInput, uid: int = Depends(require_user_id)):
    if body.target_id == uid: raise HTTPException(400, "نمی‌توانی برای خودت درخواست دوستی بفرستی.")
    async with SessionLocal() as session:
        target = await session.get(User, body.target_id)
        if not target or target.is_banned: raise HTTPException(404, "کاربر فعال پیدا نشد.")
        if await is_blocked_between(session, uid, body.target_id): raise HTTPException(403, "به‌دلیل مسدودسازی، درخواست دوستی ممکن نیست.")
        low, high = sorted((uid, body.target_id))
        existing_link = await session.scalar(select(Friendship).where(Friendship.user_low == low, Friendship.user_high == high))
        if existing_link: raise HTTPException(400, "این کاربر از قبل در فهرست دوستانت است.")
        existing = await session.scalar(select(FriendRequest).where(FriendRequest.status == "pending", FriendRequest.requester_id == uid, FriendRequest.target_id == body.target_id))
        if existing: raise HTTPException(400, "درخواست دوستی قبلاً ارسال شده است.")
        reverse = await session.scalar(select(FriendRequest).where(FriendRequest.status == "pending", FriendRequest.requester_id == body.target_id, FriendRequest.target_id == uid))
        if reverse:
            reverse.status = "accepted"
            session.add(Friendship(user_low=low, user_high=high))
            await session.commit()
            return {"ok": True, "accepted": True}
        row = FriendRequest(requester_id=uid, target_id=body.target_id)
        session.add(row)
        await create_notification(session, body.target_id, "friend_request", "درخواست دوستی جدید", "یک بازیکن برایت درخواست دوستی فرستاده است.", {"from": uid})
        await session.commit()
        requester = await session.get(User, uid)
        if bot:
            try: await bot.send_message(body.target_id, f"👥 {html.escape(requester.first_name if requester else 'یک بازیکن')} برای دوستی دعوتت کرده است. در ربات دستور /friends را بزن و از درخواست‌ها قبول کن.", parse_mode="HTML")
            except Exception: pass
        return {"ok": True, "request_id": row.id}

@app.post("/api/friends/request/{request_id}/respond")
async def friend_request_respond(request_id: int, body: FriendRequestRespond, uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        row = await session.get(FriendRequest, request_id)
        if not row or row.target_id != uid or row.status != "pending": raise HTTPException(404, "درخواست دوستی پیدا نشد.")
        row.status = "accepted" if body.accept else "rejected"
        if body.accept:
            await create_notification(session, row.requester_id, "friend_accepted", "درخواست دوستی پذیرفته شد", "درخواست دوستی تو پذیرفته شد.", {"friend_id": uid})
            low, high = sorted((row.requester_id, row.target_id))
            exists = await session.scalar(select(Friendship).where(Friendship.user_low == low, Friendship.user_high == high))
            if not exists: session.add(Friendship(user_low=low, user_high=high))
        await session.commit()
        if body.accept and bot:
            try: await bot.send_message(row.requester_id, "✅ درخواست دوستی‌ات پذیرفته شد. برای گفتگو /dm شناسه_کاربر را بفرست.")
            except Exception: pass
        return {"ok": True, "status": row.status}

@app.delete("/api/friends/{friend_id}")
async def friend_remove(friend_id: int, uid: int = Depends(require_user_id)):
    low, high = sorted((uid, friend_id))
    async with SessionLocal() as session:
        link = await session.scalar(select(Friendship).where(Friendship.user_low == low, Friendship.user_high == high))
        if not link: raise HTTPException(404, "این کاربر در فهرست دوستانت نیست.")
        await session.delete(link); await session.commit()
        return {"ok": True}

@app.get("/api/events")
async def list_events(uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        return {"events": await active_events_for(session)}

@app.post("/api/friends/challenge")
async def friend_challenge_create(body: FriendChallengeCreate, uid: int = Depends(require_user_id)):
    if body.target_id == uid:
        raise HTTPException(400, "نمی‌توانی خودت را به چالش دعوت کنی.")
    async with SessionLocal() as session:
        target = await session.get(User, body.target_id)
        if not target or target.is_banned:
            raise HTTPException(404, "کاربر مقصد پیدا نشد.")
        if await is_blocked_between(session, uid, body.target_id):
            raise HTTPException(403, "امکان چالش این کاربر وجود ندارد.")
        if body.game == "guess":
            payload = {"question": "عدد مخفی بین ۱ تا ۲۰ چنده؟", "answer": str(random.randint(1, 20))}
        elif body.game == "memory":
            seq = [random.choice(["🍒", "⭐", "🚀", "🎲", "💎"]) for _ in range(3)]
            payload = {"question": "ترتیب نمادها را به خاطر بسپار.", "sequence": seq, "answer": "|".join(seq)}
        else:
            a, b = random.randint(8, 30), random.randint(3, 18)
            payload = {"question": f"{a} × {b} = ?", "answer": str(a*b)}
        challenge = FriendChallenge(sender_id=uid, target_id=body.target_id, game=body.game, payload=json.dumps(payload, ensure_ascii=False))
        session.add(challenge)
        await create_notification(session, body.target_id, "friend_challenge", "دعوت به چالش", f"یک بازیکن تو را به بازی {body.game} دعوت کرده است.", {"from": uid, "challenge_id": challenge.id})
        await session.commit()
        if bot:
            try:
                await bot.send_message(body.target_id, f"⚔️ یک دعوت چالش از بازیکن {uid} دریافت کردی. مینی‌اپ GAME ARENA را باز کن.")
            except Exception:
                pass
        return {"ok": True, "id": challenge.id, "status": challenge.status}

@app.get("/api/friends/challenges")
async def friend_challenges(uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        rows = (await session.execute(select(FriendChallenge).where((FriendChallenge.sender_id == uid) | (FriendChallenge.target_id == uid)).order_by(FriendChallenge.created_at.desc()).limit(40))).scalars().all()
        result = []
        for x in rows:
            result.append({"id": x.id, "sender_id": x.sender_id, "target_id": x.target_id, "game": x.game, "status": x.status, "incoming": x.target_id == uid, "sender_score": x.sender_score, "target_score": x.target_score, "winner_id": x.winner_id})
        return {"challenges": result}

@app.get("/api/friends/challenges/{challenge_id}/prompt")
async def friend_challenge_prompt(challenge_id: int, uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        item = await session.get(FriendChallenge, challenge_id)
        if not item or uid not in (item.sender_id, item.target_id) or item.status != "accepted":
            raise HTTPException(404, "چالش فعال پیدا نشد.")
        if (uid == item.sender_id and item.sender_score is not None) or (uid == item.target_id and item.target_score is not None):
            raise HTTPException(400, "پاسخت قبلاً ثبت شده است.")
        payload = json.loads(item.payload or "{}")
        return {"game": item.game, "question": payload.get("question", "سؤال چالش"), "sequence": payload.get("sequence")}

@app.post("/api/friends/challenges/respond")
async def friend_challenge_respond(body: FriendChallengeResponse, uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        item = await session.get(FriendChallenge, body.challenge_id)
        if not item or item.target_id != uid or item.status != "pending":
            raise HTTPException(404, "دعوت معتبر نیست.")
        item.status = "accepted" if body.accept else "rejected"
        await session.commit()
        return {"ok": True, "status": item.status}

@app.post("/api/friends/challenges/play")
async def friend_challenge_play(body: FriendChallengePlay, uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        item = await session.get(FriendChallenge, body.challenge_id)
        if not item or uid not in (item.sender_id, item.target_id) or item.status != "accepted":
            raise HTTPException(404, "چالش فعال پیدا نشد.")
        if (uid == item.sender_id and item.sender_score is not None) or (uid == item.target_id and item.target_score is not None):
            raise HTTPException(400, "پاسخت قبلاً ثبت شده است.")
        payload = json.loads(item.payload or "{}")
        score = 100 if body.answer.strip() == str(payload.get("answer", "")) else 0
        if uid == item.sender_id:
            item.sender_score = score
        else:
            item.target_score = score
        if item.sender_score is not None and item.target_score is not None:
            item.status = "completed"
            item.winner_id = item.sender_id if item.sender_score > item.target_score else item.target_id if item.target_score > item.sender_score else None
            if item.winner_id:
                winner = await session.get(User, item.winner_id)
                await add_coins(session, winner, 20, "برد چالش دوستان")
        await session.commit()
        return {"ok": True, "score": score, "status": item.status, "winner_id": item.winner_id, "sender_score": item.sender_score, "target_score": item.target_score}

@app.get("/api/tournaments")
async def tournaments(uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        rows = (await session.execute(select(Tournament).order_by(Tournament.created_at.desc()).limit(50))).scalars().all()
        result = []
        for item in rows:
            count = await session.scalar(select(func.count()).select_from(TournamentEntry).where(TournamentEntry.tournament_id == item.id))
            joined = await session.scalar(select(func.count()).select_from(TournamentEntry).where(TournamentEntry.tournament_id == item.id, TournamentEntry.user_id == uid))
            result.append({"id": item.id, "name": item.name, "game": item.game, "prize_coins": item.prize_coins, "max_players": item.max_players, "status": item.status, "players": int(count or 0), "joined": bool(joined), "bracket": json.loads(item.bracket) if item.bracket else None})
        return {"tournaments": result}

@app.post("/api/tournaments/{tournament_id}/join")
async def tournament_join(tournament_id: int, uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        item = await session.get(Tournament, tournament_id)
        if not item or item.status != "open":
            raise HTTPException(400, "ثبت‌نام این تورنمنت بسته شده است.")
        count = await session.scalar(select(func.count()).select_from(TournamentEntry).where(TournamentEntry.tournament_id == tournament_id))
        exists = await session.scalar(select(TournamentEntry).where(TournamentEntry.tournament_id == tournament_id, TournamentEntry.user_id == uid))
        if exists:
            raise HTTPException(400, "قبلاً در این تورنمنت ثبت‌نام کرده‌ای.")
        if count >= item.max_players:
            raise HTTPException(400, "ظرفیت تورنمنت تکمیل شده است.")
        session.add(TournamentEntry(tournament_id=tournament_id, user_id=uid))
        await session.commit()
        return {"ok": True}

def wheel_paid_cost(paid_spins: int) -> int:
    """Cost for the next paid spin after the daily free spin: 10, 30, 50, 90, 120, then +30."""
    schedule = (10, 30, 50, 90, 120)
    if paid_spins < len(schedule):
        return schedule[paid_spins]
    return 120 + 30 * (paid_spins - 4)

@app.get("/api/wheel")
async def wheel_status(uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        user = await session.get(User, uid)
        today = date.today().isoformat()
        spins = int(user.wheel_spins or 0) if user.wheel_date == today else 0
        paid_spins = max(0, spins - 1)
        free_ticket = spins == 0
        next_cost = 0 if free_ticket else wheel_paid_cost(paid_spins)
        return {"free_ticket": free_ticket, "spins_today": spins, "next_cost": next_cost,
                "coins": int(user.coins or 0), "cost_schedule": [10, 30, 50, 90, 120, 150, 180]}

@app.post("/api/wheel/spin")
async def wheel_spin(uid: int = Depends(require_user_id)):
    prizes = [5, 10, 15, 20, 30, 50, 75, 100]
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.id == uid).with_for_update())
        if user is None:
            raise HTTPException(404, "پروفایل کاربر پیدا نشد.")
        today = date.today().isoformat()
        if user.wheel_date != today:
            user.wheel_date = today
            user.wheel_spins = 0
        spins_before = int(user.wheel_spins or 0)
        is_free = spins_before == 0
        cost = 0 if is_free else wheel_paid_cost(spins_before - 1)
        if cost and int(user.coins or 0) < cost:
            raise HTTPException(400, f"برای این چرخش به {cost} سکه نیاز داری.")
        if cost:
            await add_coins(session, user, -cost, f"هزینه چرخش شماره {spins_before + 1} گردونه")
        user.wheel_spins = spins_before + 1
        reward = random.choice(prizes)
        await add_coins(session, user, reward, "جایزه گردونه شانس")
        await session.commit()
        paid_spins_after = max(0, user.wheel_spins - 1)
        next_cost = wheel_paid_cost(paid_spins_after) if user.wheel_spins else 0
        return {"reward": reward, "cost": cost, "is_free": is_free,
                "spins_today": user.wheel_spins, "next_cost": next_cost,
                "profile": profile_dict(user)}

# GAME ARENA 3.0 — seasons, social safety, notifications, matchmaking and clan economy

TERRITORY_SEEDS = [
    ("nexus", "NEXUS DISTRICT"), ("neon_city", "NEON CITY"),
    ("orbit", "ORBIT STATION"), ("ember", "EMBER FIELDS"),
    ("skyharbor", "SKYHARBOR"), ("void", "VOID FRONTIER"),
]

@app.get("/api/season")
async def season_overview(uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        season = await ensure_active_season(session)
        await session.commit()
        score = await session.scalar(select(SeasonScore).where(SeasonScore.season_id == season.id, SeasonScore.user_id == uid))
        leaders = (await session.execute(select(SeasonScore, User).join(User, User.id == SeasonScore.user_id).where(SeasonScore.season_id == season.id).order_by(SeasonScore.points.desc(), SeasonScore.wins.desc()).limit(10))).all()
        return {"season": {"id": season.id, "name": season.name, "starts_at": season.starts_at.isoformat(), "ends_at": season.ends_at.isoformat(), "status": season.status},
                "my_score": int(score.points if score else 0), "my_games": int(score.games if score else 0),
                "leaders": [{"rank": i + 1, "id": u.id, "name": u.first_name, "points": sc.points, "wins": sc.wins, "is_me": u.id == uid} for i, (sc, u) in enumerate(leaders)],
                "reward_track": [{"points": 100, "reward": "قاب فصل"}, {"points": 300, "reward": "نشان فصل"}, {"points": 700, "reward": "عنوان قهرمان فصل"}, {"points": 1200, "reward": "جایزه ویژه فصل"}]}

@app.get("/api/notifications")
async def notifications_list(uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        rows = (await session.execute(select(ArenaNotification).where(ArenaNotification.user_id == uid).order_by(ArenaNotification.created_at.desc()).limit(40))).scalars().all()
        unread = sum(1 for x in rows if x.read_at is None)
        return {"unread": unread, "items": [{"id": x.id, "kind": x.kind, "title": x.title, "body": x.body, "data": json.loads(x.data_json or "{}"), "read": x.read_at is not None, "created_at": x.created_at.isoformat()} for x in rows]}

@app.post("/api/notifications/{notification_id}/read")
async def notification_mark_read(notification_id: int, uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        row = await session.scalar(select(ArenaNotification).where(ArenaNotification.id == notification_id, ArenaNotification.user_id == uid))
        if not row:
            raise HTTPException(404, "اعلان پیدا نشد.")
        if row.read_at is None:
            row.read_at = datetime.utcnow()
            await session.commit()
        return {"ok": True}

@app.get("/api/social/global-chat")
async def global_chat_list(uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        blocked_ids = set((await session.execute(select(UserBlock.blocked_id).where(UserBlock.blocker_id == uid))).scalars().all())
        blocked_by_ids = set((await session.execute(select(UserBlock.blocker_id).where(UserBlock.blocked_id == uid))).scalars().all())
        rows = (await session.execute(select(GlobalChatMessage, User).join(User, User.id == GlobalChatMessage.user_id).order_by(GlobalChatMessage.created_at.desc()).limit(80))).all()
        messages = []
        for row, user in reversed(rows):
            if row.user_id in blocked_ids or row.user_id in blocked_by_ids or user.is_banned:
                continue
            messages.append({"id": row.id, "user_id": user.id, "name": user.first_name, "username": user.username,
                             "is_owner": user.id == ADMIN_ID, "is_verified": bool(user.is_verified),
                             "message": row.message, "created_at": row.created_at.isoformat(), "is_me": user.id == uid})
        return {"messages": messages}

@app.post("/api/social/global-chat")
async def global_chat_send(body: GlobalChatInput, uid: int = Depends(require_user_id)):
    clean = body.message.strip()
    if not clean:
        raise HTTPException(400, "پیام خالی قابل ارسال نیست.")
    now = time.monotonic()
    previous = GLOBAL_CHAT_LAST.get(uid, 0)
    if now - previous < 2.0:
        raise HTTPException(429, "برای ارسال پیام بعدی کمی صبر کن.")
    async with SessionLocal() as session:
        row = GlobalChatMessage(user_id=uid, message=clean[:300])
        session.add(row)
        await session.commit()
        GLOBAL_CHAT_LAST[uid] = now
        return {"ok": True, "id": row.id, "created_at": row.created_at.isoformat()}

@app.post("/api/social/block")
async def social_block(body: SocialBlockInput, uid: int = Depends(require_user_id)):
    if body.target_id == uid:
        raise HTTPException(400, "نمی‌توانی خودت را مسدود کنی.")
    async with SessionLocal() as session:
        target = await session.get(User, body.target_id)
        if not target:
            raise HTTPException(404, "کاربر پیدا نشد.")
        existing = await session.scalar(select(UserBlock).where(UserBlock.blocker_id == uid, UserBlock.blocked_id == body.target_id))
        if existing:
            return {"ok": True, "already_blocked": True}
        session.add(UserBlock(blocker_id=uid, blocked_id=body.target_id))
        low, high = sorted((uid, body.target_id))
        friendship = await session.scalar(select(Friendship).where(Friendship.user_low == low, Friendship.user_high == high))
        if friendship:
            await session.delete(friendship)
        pending = (await session.execute(select(FriendRequest).where(FriendRequest.status == "pending", ((FriendRequest.requester_id == uid) & (FriendRequest.target_id == body.target_id)) | ((FriendRequest.requester_id == body.target_id) & (FriendRequest.target_id == uid))))).scalars().all()
        for row in pending:
            row.status = "cancelled"
        await create_notification(session, body.target_id, "safety", "تنظیمات ارتباطی تغییر کرد", "امکان ارتباط و دعوت جدید بین این دو حساب غیرفعال شد.")
        await session.commit()
        return {"ok": True}

@app.delete("/api/social/block/{target_id}")
async def social_unblock(target_id: int, uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        row = await session.scalar(select(UserBlock).where(UserBlock.blocker_id == uid, UserBlock.blocked_id == target_id))
        if row:
            await session.delete(row)
            await session.commit()
        return {"ok": True}

@app.get("/api/social/blocks")
async def social_blocks(uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        rows = (await session.execute(select(UserBlock, User).join(User, User.id == UserBlock.blocked_id).where(UserBlock.blocker_id == uid).order_by(UserBlock.created_at.desc()).limit(100))).all()
        return {"items": [{"id": u.id, "name": u.first_name, "username": u.username} for _, u in rows]}

@app.post("/api/social/report")
async def social_report(body: UserReportInput, uid: int = Depends(require_user_id)):
    if body.target_id == uid:
        raise HTTPException(400, "نمی‌توانی حساب خودت را گزارش کنی.")
    async with SessionLocal() as session:
        target = await session.get(User, body.target_id)
        if not target:
            raise HTTPException(404, "کاربر موردنظر پیدا نشد.")
        day_ago = datetime.utcnow() - timedelta(days=1)
        count = await session.scalar(select(func.count()).select_from(UserReport).where(UserReport.reporter_id == uid, UserReport.created_at >= day_ago))
        if int(count or 0) >= 5:
            raise HTTPException(429, "سقف گزارش روزانه پر شده است.")
        duplicate = await session.scalar(select(UserReport.id).where(UserReport.reporter_id == uid, UserReport.target_id == body.target_id, UserReport.status == "open", UserReport.created_at >= day_ago).limit(1))
        if duplicate:
            raise HTTPException(409, "گزارش باز قبلی برای این کاربر وجود دارد.")
        row = UserReport(reporter_id=uid, target_id=body.target_id, reason=body.reason, details=body.details.strip())
        session.add(row)
        await session.commit()
        return {"ok": True, "report_id": row.id}

@app.get("/api/social/arena-feed")
async def social_arena_feed(uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        now = datetime.utcnow()
        online = await session.scalar(select(func.count()).select_from(User).where(User.last_seen_at >= now - timedelta(minutes=5), User.is_banned == False))
        matches = (await session.execute(select(ArenaLiveMatch).where(ArenaLiveMatch.status == "completed").order_by(ArenaLiveMatch.created_at.desc()).limit(12))).scalars().all()
        return {"online": int(online or 0), "completed_matches": [{"id": x.id, "game": x.game, "winner_id": x.winner_id, "created_at": x.created_at.isoformat()} for x in matches]}

@app.get("/api/clans/territories")
async def clan_territories(uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        for key, name in TERRITORY_SEEDS:
            row = await session.scalar(select(ClanTerritory).where(ClanTerritory.territory_key == key))
            if row is None:
                session.add(ClanTerritory(territory_key=key, name=name))
        await session.commit()
        rows = (await session.execute(select(ClanTerritory).order_by(ClanTerritory.name.asc()))).scalars().all()
        result = []
        for territory in rows:
            clan = await session.get(Clan, territory.owner_clan_id) if territory.owner_clan_id else None
            result.append({"key": territory.territory_key, "name": territory.name, "owner_clan_id": territory.owner_clan_id, "owner_name": clan.name if clan else None, "level": territory.level})
        member = await session.scalar(select(ClanMember).where(ClanMember.user_id == uid))
        clan = await session.get(Clan, member.clan_id) if member else None
        return {"territories": result, "my_clan": ({"id": clan.id, "name": clan.name, "treasury": clan.treasury, "role": member.role} if clan else None)}

@app.post("/api/clans/treasury/deposit")
async def clan_treasury_deposit(body: ClanDepositInput, uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        member = await session.scalar(select(ClanMember).where(ClanMember.user_id == uid))
        if not member:
            raise HTTPException(400, "ابتدا عضو یک کلن شو.")
        user = await session.scalar(select(User).where(User.id == uid).with_for_update())
        clan = await session.scalar(select(Clan).where(Clan.id == member.clan_id).with_for_update())
        if not user or not clan:
            raise HTTPException(404, "کلن یا کاربر پیدا نشد.")
        if user.coins < body.amount:
            raise HTTPException(400, "موجودی سکه کافی نیست.")
        await add_coins(session, user, -body.amount, f"واریز به خزانه کلن {clan.name}")
        clan.treasury += body.amount
        clan.xp += max(1, body.amount // 100)
        clan.level = max(1, clan.xp // 250 + 1)
        await session.commit()
        return {"ok": True, "treasury": clan.treasury, "coins": user.coins, "clan_xp": clan.xp}

@app.post("/api/clans/territories/claim")
async def clan_territory_claim(body: TerritoryClaimInput, uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        member = await session.scalar(select(ClanMember).where(ClanMember.user_id == uid))
        if not member or member.role not in ("owner", "leader"):
            raise HTTPException(403, "فقط مالک یا فرمانده کلن می‌تواند قلمرو بگیرد.")
        territory = await session.scalar(select(ClanTerritory).where(ClanTerritory.territory_key == body.territory_key).with_for_update())
        clan = await session.scalar(select(Clan).where(Clan.id == member.clan_id).with_for_update())
        if not territory:
            raise HTTPException(404, "قلمرو ناشناخته است.")
        if territory.owner_clan_id:
            raise HTTPException(409, "این قلمرو قبلاً تصاحب شده است.")
        if clan.treasury < 500:
            raise HTTPException(400, "خزانه کلن برای تصاحب قلمرو به ۵۰۰ سکه نیاز دارد.")
        clan.treasury -= 500
        territory.owner_clan_id = clan.id
        territory.claimed_at = datetime.utcnow()
        await create_notification(session, clan.owner_id, "clan", "قلمرو جدید", f"کلن شما قلمرو {territory.name} را تصاحب کرد.")
        await session.commit()
        return {"ok": True, "territory": territory.name, "treasury": clan.treasury}

@app.post("/api/clans/territories/{territory_key}/upgrade")
async def clan_territory_upgrade(territory_key: str, uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        member = await session.scalar(select(ClanMember).where(ClanMember.user_id == uid))
        if not member or member.role not in ("owner", "leader"):
            raise HTTPException(403, "فقط مالک یا فرمانده کلن می‌تواند قلمرو را ارتقا دهد.")
        territory = await session.scalar(select(ClanTerritory).where(ClanTerritory.territory_key == territory_key).with_for_update())
        clan = await session.scalar(select(Clan).where(Clan.id == member.clan_id).with_for_update())
        if not territory or territory.owner_clan_id != clan.id:
            raise HTTPException(404, "این قلمرو متعلق به کلن شما نیست.")
        cost = 500 * territory.level
        if clan.treasury < cost:
            raise HTTPException(400, f"برای ارتقای بعدی به {cost} سکه خزانه نیاز دارید.")
        clan.treasury -= cost
        territory.level += 1
        clan.xp += 100
        clan.level = max(1, clan.xp // 250 + 1)
        await session.commit()
        return {"ok": True, "level": territory.level, "treasury": clan.treasury}

@app.post("/api/arena/matchmaking/join")
async def arena_matchmaking_join(body: MatchmakingInput, uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        existing = await session.get(ArenaQueueEntry, uid)
        if existing and existing.status == "matched" and existing.match_id:
            return {"status": "matched", "match_id": existing.match_id}
        now = datetime.utcnow()
        if existing and existing.status == "waiting" and existing.created_at >= now - timedelta(minutes=5):
            return {"status": "queued", "created_at": existing.created_at.isoformat()}
        if existing:
            await session.delete(existing)
            await session.flush()
        candidates = (await session.execute(select(ArenaQueueEntry).where(ArenaQueueEntry.game == body.game, ArenaQueueEntry.status == "waiting", ArenaQueueEntry.user_id != uid, ArenaQueueEntry.created_at >= now - timedelta(minutes=5)).order_by(ArenaQueueEntry.created_at.asc()).limit(20))).scalars().all()
        opponent = None
        for candidate in candidates:
            if not await is_blocked_between(session, uid, candidate.user_id):
                opponent = candidate
                break
        if opponent:
            user_pair = [uid, opponent.user_id]
            p1, p2 = user_pair[0], user_pair[1]
            a = random.randint(12, 49); b = random.randint(7, 29)
            op = random.choice(["+", "-"])
            question = f"{a} {op} {b} = ?"
            answer = a + b if op == "+" else a - b
            match = ArenaLiveMatch(game=body.game, player_one_id=p1, player_two_id=p2, question=question,
                                   expected_answer=answer, expires_at=now + timedelta(seconds=90))
            session.add(match)
            await session.flush()
            opponent.status = "matched"; opponent.match_id = match.id
            session.add(ArenaQueueEntry(user_id=uid, game=body.game, status="matched", match_id=match.id, created_at=now))
            await create_notification(session, p1, "live_match", "حریف پیدا شد!", "مسابقه زنده ریاضی آماده است.", {"match_id": match.id})
            await create_notification(session, p2, "live_match", "حریف پیدا شد!", "مسابقه زنده ریاضی آماده است.", {"match_id": match.id})
            await session.commit()
            return {"status": "matched", "match_id": match.id}
        session.add(ArenaQueueEntry(user_id=uid, game=body.game, status="waiting", created_at=now))
        await session.commit()
        return {"status": "queued", "created_at": now.isoformat()}

@app.get("/api/arena/matchmaking")
async def arena_matchmaking_status(uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        row = await session.get(ArenaQueueEntry, uid)
        if not row:
            return {"status": "idle"}
        if row.status == "waiting" and row.created_at < datetime.utcnow() - timedelta(minutes=5):
            await session.delete(row); await session.commit()
            return {"status": "idle"}
        return {"status": row.status, "match_id": row.match_id}

@app.post("/api/arena/matchmaking/cancel")
async def arena_matchmaking_cancel(uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        row = await session.get(ArenaQueueEntry, uid)
        if row and row.status == "waiting":
            await session.delete(row); await session.commit()
        return {"ok": True}

@app.get("/api/arena/matches/{match_id}")
async def arena_match_status(match_id: int, uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        match = await session.get(ArenaLiveMatch, match_id)
        if not match or uid not in (match.player_one_id, match.player_two_id):
            raise HTTPException(404, "مسابقه پیدا نشد.")
        if match.status == "playing" and match.expires_at <= datetime.utcnow():
            match.status = "expired"
            for queue_user in (match.player_one_id, match.player_two_id):
                queue_row = await session.get(ArenaQueueEntry, queue_user)
                if queue_row:
                    await session.delete(queue_row)
            await session.commit()
        opponent = match.player_two_id if uid == match.player_one_id else match.player_one_id
        my_answer = match.player_one_answer if uid == match.player_one_id else match.player_two_answer
        opponent_answer = match.player_two_answer if uid == match.player_one_id else match.player_one_answer
        return {"id": match.id, "status": match.status, "game": match.game, "question": match.question,
                "my_answered": my_answer is not None, "opponent_answered": opponent_answer is not None,
                "winner_id": match.winner_id, "is_winner": match.winner_id == uid if match.status == "completed" else None,
                "expires_at": match.expires_at.isoformat()}

@app.post("/api/arena/matches/{match_id}/answer")
async def arena_match_answer(match_id: int, body: LiveMatchAnswer, uid: int = Depends(require_user_id)):
    async with SessionLocal() as session:
        match = await session.scalar(select(ArenaLiveMatch).where(ArenaLiveMatch.id == match_id).with_for_update())
        if not match or uid not in (match.player_one_id, match.player_two_id):
            raise HTTPException(404, "مسابقه پیدا نشد.")
        if match.status != "playing" or match.expires_at <= datetime.utcnow():
            if match.status == "playing":
                match.status = "expired"
                for queue_user in (match.player_one_id, match.player_two_id):
                    queue_row = await session.get(ArenaQueueEntry, queue_user)
                    if queue_row:
                        await session.delete(queue_row)
            await session.commit()
            raise HTTPException(400, "زمان مسابقه تمام شده یا مسابقه بسته است.")
        if uid == match.player_one_id:
            if match.player_one_answer is not None: raise HTTPException(409, "پاسخ تو قبلاً ثبت شده است.")
            match.player_one_answer = body.answer
        else:
            if match.player_two_answer is not None: raise HTTPException(409, "پاسخ تو قبلاً ثبت شده است.")
            match.player_two_answer = body.answer
        result = {"status": "playing"}
        if match.player_one_answer is not None and match.player_two_answer is not None:
            one_ok = match.player_one_answer == match.expected_answer
            two_ok = match.player_two_answer == match.expected_answer
            if one_ok and two_ok: match.winner_id = None
            elif one_ok: match.winner_id = match.player_one_id
            elif two_ok: match.winner_id = match.player_two_id
            match.status = "completed"
            p1 = await session.get(User, match.player_one_id)
            p2 = await session.get(User, match.player_two_id)
            if p1 and p2:
                await record_game(session, p1, 35 if match.winner_id == p1.id else 10, match.winner_id == p1.id, "live-math", commit=False)
                await record_game(session, p2, 35 if match.winner_id == p2.id else 10, match.winner_id == p2.id, "live-math", commit=False)
            for queue_user in (match.player_one_id, match.player_two_id):
                q = await session.get(ArenaQueueEntry, queue_user)
                if q: await session.delete(q)
            await create_notification(session, match.player_one_id, "match_result", "نتیجه مسابقه زنده", "مسابقه ریاضی زنده به پایان رسید.", {"match_id": match.id, "winner_id": match.winner_id})
            await create_notification(session, match.player_two_id, "match_result", "نتیجه مسابقه زنده", "مسابقه ریاضی زنده به پایان رسید.", {"match_id": match.id, "winner_id": match.winner_id})
            result = {"status": "completed", "winner_id": match.winner_id, "is_winner": match.winner_id == uid if match.winner_id else None}
        await session.commit()
        return result

@app.get("/api/admin/reports")
async def admin_reports(uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    async with SessionLocal() as session:
        rows = (await session.execute(select(UserReport).order_by(UserReport.created_at.desc()).limit(150))).scalars().all()
        return {"reports": [{"id": r.id, "reporter_id": r.reporter_id, "target_id": r.target_id, "reason": r.reason, "details": r.details, "status": r.status, "created_at": r.created_at.isoformat()} for r in rows]}

@app.post("/api/admin/reports/{report_id}/review")
async def admin_review_report(report_id: int, uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    async with SessionLocal() as session:
        row = await session.get(UserReport, report_id)
        if not row: raise HTTPException(404, "گزارش پیدا نشد.")
        if row.status == "open":
            row.status = "reviewed"; row.reviewed_by = uid
            session.add(AdminAudit(admin_id=uid, action="report_review", target_id=row.target_id, detail=f"report #{row.id}"))
            await session.commit()
        return {"ok": True, "status": row.status}

@app.get("/api/admin/seasons")
async def admin_list_seasons(uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    async with SessionLocal() as session:
        rows = (await session.execute(select(ArenaSeason).order_by(ArenaSeason.id.desc()).limit(20))).scalars().all()
        return {"seasons": [{"id": x.id, "name": x.name, "starts_at": x.starts_at.isoformat(), "ends_at": x.ends_at.isoformat(), "status": x.status} for x in rows]}

@app.post("/api/admin/seasons")
async def admin_create_season(body: SeasonInput, uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    async with SessionLocal() as session:
        active = (await session.execute(select(ArenaSeason).where(ArenaSeason.status == "active"))).scalars().all()
        now = datetime.utcnow()
        for row in active: row.status = "completed"
        latest_id = int(await session.scalar(select(func.max(ArenaSeason.id))) or 0)
        season = ArenaSeason(name=body.name.strip(), starts_at=now, ends_at=now + timedelta(days=body.duration_days), status="active")
        session.add(season)
        await session.flush()
        session.add(AdminAudit(admin_id=uid, action="season_create", target_id=season.id, detail=f"{season.name} · {body.duration_days} days"))
        await session.commit()
        return {"ok": True, "season": {"id": season.id, "name": season.name, "ends_at": season.ends_at.isoformat()}}

# Admin APIs
async def admin_guard(uid: int):
    if uid != ADMIN_ID:
        raise HTTPException(403, "دسترسی مدیر لازم است.")

@app.get("/api/admin/force-join")
async def admin_get_force_join(uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    async with SessionLocal() as session:
        settings = await load_force_join_settings(session)
    return {"enabled": settings["enabled"], "chat_id": settings["chat_id"],
            "invite_url": settings["invite_url"], "title": settings["title"]}

async def verify_bot_channel_admin(chat_id: str) -> str:
    if not bot:
        raise HTTPException(503, "ربات هنوز راه‌اندازی نشده است؛ لاگ Railway را بررسی کن.")
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(chat_id=chat_id, user_id=me.id)
        status = getattr(member.status, "value", str(member.status))
        if status not in ("creator", "administrator"):
            raise HTTPException(400, "ربات در این کانال ادمین نیست. ابتدا ربات را به کانال اضافه و مدیر کن.")
        chat = await bot.get_chat(chat_id)
        return getattr(chat, "title", None) or getattr(chat, "username", None) or chat_id
    except HTTPException:
        raise
    except Exception as exc:
        print(f"Force-join channel verification failed: {exc}")
        raise HTTPException(400, "بررسی کانال ناموفق بود. شناسه کانال را بررسی کن و مطمئن شو ربات در کانال دسترسی مدیر دارد.")

@app.post("/api/admin/force-join/test")
async def admin_test_force_join(body: ForceJoinInput, uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    chat_id = body.chat_id.strip()
    if not chat_id:
        raise HTTPException(400, "ابتدا شناسه کانال یا @username را وارد کن.")
    title = await verify_bot_channel_admin(chat_id)
    return {"ok": True, "channel_title": title, "message": "دسترسی ربات تأیید شد؛ می‌توانی تنظیمات را ذخیره کنی."}

@app.put("/api/admin/force-join")
async def admin_set_force_join(body: ForceJoinInput, uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    chat_id = body.chat_id.strip()
    invite_url = body.invite_url.strip()
    title = body.title.strip() or "کانال رسمی GAME ARENA"
    if body.enabled:
        if not chat_id:
            raise HTTPException(400, "شناسه کانال یا @username را وارد کن.")
        if not invite_url.startswith(("https://t.me/", "https://telegram.me/")):
            raise HTTPException(400, "لینک عضویت باید از نوع https://t.me/... باشد.")
        await verify_bot_channel_admin(chat_id)
    values = {
        "force_join_enabled": "1" if body.enabled else "0",
        "force_join_chat": chat_id,
        "force_join_url": invite_url,
        "force_join_title": title,
    }
    async with SessionLocal() as session:
        for key, value in values.items():
            row = await session.scalar(select(AppSetting).where(AppSetting.key == key))
            if row is None:
                session.add(AppSetting(key=key, value=value[:120]))
            else:
                row.value = value[:120]
        await session.commit()
    return {"ok": True, "enabled": body.enabled, "chat_id": chat_id,
            "invite_url": invite_url, "title": title}

@app.get("/api/admin/stats")
async def admin_stats(uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    async with SessionLocal() as session:
        total = await session.scalar(select(func.count()).select_from(User))
        banned = await session.scalar(select(func.count()).select_from(User).where(User.is_banned == True))
        xp = await session.scalar(select(func.coalesce(func.sum(User.xp), 0)))
        coins = await session.scalar(select(func.coalesce(func.sum(User.coins), 0)))
        games = await session.scalar(select(func.coalesce(func.sum(User.games), 0)))
        today = date.today().isoformat()
        daily = await session.scalar(select(func.count()).select_from(User).where(User.last_daily == today))
        reports = await session.scalar(select(func.count()).select_from(UserReport).where(UserReport.status == "open"))
        live_matches = await session.scalar(select(func.count()).select_from(ArenaLiveMatch).where(ArenaLiveMatch.status == "playing"))
        return {"users": int(total or 0), "banned": int(banned or 0), "xp": int(xp or 0), "coins": int(coins or 0), "games": int(games or 0), "daily_active": int(daily or 0), "open_reports": int(reports or 0), "live_matches": int(live_matches or 0)}

@app.get("/api/admin/users")
async def admin_users(q: str = "", uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    async with SessionLocal() as session:
        stmt = select(User).order_by(User.created_at.desc()).limit(100)
        if q.isdigit():
            stmt = select(User).where(User.id == int(q))
        elif q:
            stmt = select(User).where(User.username.ilike(f"%{q}%") | User.first_name.ilike(f"%{q}%")).limit(100)
        users = (await session.execute(stmt)).scalars().all()
        return {"users": [{"id": x.id, "name": x.first_name, "username": x.username, "coins": x.coins, "xp": x.xp, "banned": x.is_banned, "verified": bool(x.is_verified), "vip_tier": x.vip_tier or "none", "is_owner": x.id == ADMIN_ID} for x in users]}

@app.post("/api/admin/coins")
async def admin_adjust_coins(body: CoinAdjustment, uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    async with SessionLocal() as session:
        user = await session.get(User, body.user_id)
        if not user:
            raise HTTPException(404, "کاربر پیدا نشد.")
        if user.coins + body.amount < 0:
            raise HTTPException(400, "موجودی کاربر منفی می‌شود.")
        await add_coins(session, user, body.amount, body.reason)
        session.add(AdminAudit(admin_id=uid, action="coin_adjustment", target_id=user.id, detail=f"{body.amount:+d} سکه · {body.reason[:350]}"))
        await session.commit()
        return {"ok": True, "coins": user.coins}

@app.post("/api/admin/verify")
async def admin_verify_user(body: VerifyUserInput, uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    async with SessionLocal() as session:
        user = await session.get(User, body.user_id)
        if not user:
            raise HTTPException(404, "کاربر پیدا نشد.")
        if user.id == ADMIN_ID and not body.verified:
            raise HTTPException(400, "نشان مالک قابل حذف نیست.")
        user.is_verified = body.verified
        session.add(AdminAudit(admin_id=uid, action="verification_change", target_id=user.id, detail=f"verified={body.verified}"))
        await session.commit()
        return {"ok": True, "user_id": user.id, "verified": user.is_verified, "is_owner": user.id == ADMIN_ID}

@app.post("/api/admin/ban")
async def admin_ban(body: BanUserInput, uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    if body.user_id == ADMIN_ID:
        raise HTTPException(400, "حساب مدیر اصلی قابل مسدودسازی نیست.")
    async with SessionLocal() as session:
        user = await session.get(User, body.user_id)
        if not user:
            raise HTTPException(404, "کاربر پیدا نشد.")
        user.is_banned = body.banned
        session.add(AdminAudit(admin_id=uid, action="ban_change", target_id=user.id, detail=f"banned={body.banned}"))
        await session.commit()
        return {"ok": True, "banned": user.is_banned}

@app.post("/api/admin/broadcast")
async def admin_broadcast(body: AdminBroadcast, uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    if not bot:
        raise HTTPException(503, "ربات هنوز آماده ارسال پیام نیست.")
    async with SessionLocal() as session:
        ids = (await session.execute(select(User.id).where(User.is_banned == False))).scalars().all()
    sent = failed = 0
    for user_id in ids:
        try:
            await bot.send_message(user_id, body.message)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.04)
    return {"sent": sent, "failed": failed, "total": len(ids)}

@app.post("/api/admin/products")
async def admin_create_product(body: ProductInput, uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    payload = body.model_dump()
    bundle_items = payload.pop("bundle_items", [])
    if payload["category"] in ("pack", "gift", "item"):
        payload["reward_only"] = True
    if payload["category"] == "character" and not payload.get("image_url"):
        raise HTTPException(400, "برای کاراکتر سه‌بعدی باید تصویر رندر با پس‌زمینه سفید آپلود شود.")
    if payload["category"] == "pack":
        if not bundle_items:
            raise HTTPException(400, "برای ساخت بسته، حداقل یک آیتم در فهرست محتویات وارد کن.")
        normalized = []
        for entry in bundle_items:
            try:
                product_id = int(entry.get("product_id", 0)); quantity = int(entry.get("quantity", 1))
            except (AttributeError, TypeError, ValueError):
                raise HTTPException(400, "محتویات بسته باید به‌صورت شناسه محصول و تعداد معتبر باشد.")
            if product_id <= 0 or quantity < 1 or quantity > 100:
                raise HTTPException(400, "شناسه و تعداد هر آیتم بسته معتبر نیست.")
            normalized.append({"product_id": product_id, "quantity": quantity})
        payload["bundle_items"] = json.dumps(normalized, ensure_ascii=False)
    else:
        payload["bundle_items"] = "[]"
    async with SessionLocal() as session:
        if payload["category"] == "pack":
            refs = {x["product_id"] for x in normalized}
            contents = (await session.execute(select(Product).where(Product.id.in_(refs)))).scalars().all()
            found = {x.id for x in contents if x.category != "pack"}
            if refs != found:
                raise HTTPException(400, "همه شناسه‌های محتویات بسته باید محصول موجود و غیر از بسته باشند.")
        product = Product(**payload)
        session.add(product)
        await session.commit()
        return {"ok": True, "id": product.id}

@app.put("/api/admin/products/{product_id}")
async def admin_update_product(product_id: int, body: ProductInput, uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        if not product:
            raise HTTPException(404, "محصول پیدا نشد.")
        payload = body.model_dump()
        bundle_items = payload.pop("bundle_items", [])
        if payload["category"] in ("pack", "gift", "item"):
            payload["reward_only"] = True
        if payload["category"] == "character" and not payload.get("image_url"):
            raise HTTPException(400, "برای کاراکتر سه‌بعدی باید تصویر رندر با پس‌زمینه سفید آپلود شود.")
        if payload["category"] == "pack":
            if not bundle_items:
                raise HTTPException(400, "برای بسته، محتویات معتبر لازم است.")
            normalized = []
            for entry in bundle_items:
                try:
                    product_id = int(entry.get("product_id", 0)); quantity = int(entry.get("quantity", 1))
                except (AttributeError, TypeError, ValueError):
                    raise HTTPException(400, "محتویات بسته معتبر نیست.")
                if product_id <= 0 or quantity < 1 or quantity > 100:
                    raise HTTPException(400, "شناسه و تعداد آیتم بسته معتبر نیست.")
                normalized.append({"product_id": product_id, "quantity": quantity})
            payload["bundle_items"] = json.dumps(normalized, ensure_ascii=False)
        else:
            payload["bundle_items"] = "[]"
        if payload["category"] == "pack":
            refs = {x["product_id"] for x in normalized}
            contents = (await session.execute(select(Product).where(Product.id.in_(refs)))).scalars().all()
            found = {x.id for x in contents if x.category != "pack" and x.id != product_id}
            if refs != found:
                raise HTTPException(400, "همه شناسه‌های محتویات بسته باید محصول موجود و غیر از خود بسته باشند.")
        for key, value in payload.items():
            setattr(product, key, value)
        await session.commit()
        return {"ok": True}

@app.delete("/api/admin/products/{product_id}")
async def admin_delete_product(product_id: int, uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        if not product:
            raise HTTPException(404, "محصول پیدا نشد.")
        product.active = False
        await session.commit()
        return {"ok": True}

@app.post("/api/admin/products/upload")
async def admin_upload_product_image(file: UploadFile = File(...), uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    if file.content_type not in ("image/png", "image/jpeg", "image/webp", "image/gif"):
        raise HTTPException(400, "فرمت تصویر باید PNG، JPG، WEBP یا GIF باشد.")
    content = await file.read()
    if len(content) > 3 * 1024 * 1024:
        raise HTTPException(400, "حجم تصویر حداکثر ۳ مگابایت است.")
    ext = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}[file.content_type]
    name = secrets.token_hex(12) + ext
    upload_dir = STATIC_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / name).write_bytes(content)
    return {"image_url": f"/static/uploads/{name}"}

@app.get("/api/admin/products")
async def admin_products(uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    async with SessionLocal() as session:
        rows = (await session.execute(select(Product).order_by(Product.id.desc()))).scalars().all()
        return {"products": [{"id": x.id, "name": x.name, "description": x.description, "category": x.category,
                              "rarity": x.rarity, "price_coins": x.price_coins, "image_url": x.image_url,
                              "reward_only": bool(x.reward_only), "bundle_items": json.loads(x.bundle_items or "[]"),
                              "active": x.active} for x in rows]}

@app.post("/api/admin/rewards/grant")
async def admin_grant_reward(body: GrantRewardInput, uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    async with SessionLocal() as session:
        user = await session.get(User, body.user_id)
        product = await session.get(Product, body.product_id)
        if not user or not product or not product.active:
            raise HTTPException(404, "کاربر یا آیتم فعال پیدا نشد.")
        if not product.reward_only and product.category not in ("pack", "gift", "item"):
            raise HTTPException(400, "فقط بسته‌ها و آیتم‌های جایزه‌ای قابل اعطا هستند.")
        inventory = await session.scalar(select(InventoryItem).where(
            InventoryItem.user_id == user.id, InventoryItem.product_id == product.id))
        if inventory:
            inventory.quantity += body.quantity
        else:
            session.add(InventoryItem(user_id=user.id, product_id=product.id, quantity=body.quantity))
        session.add(InventoryTransaction(user_id=user.id, product_id=product.id, product_name=product.name,
                                         action="owner_grant", quantity=body.quantity, details="اعطای دستی توسط مالک"))
        session.add(AdminAudit(admin_id=uid, action="reward_grant", target_id=user.id, detail=f"{product.name} × {body.quantity}"))
        await session.commit()
        try:
            if bot:
                await bot.send_message(user.id, f"🎁 مالک GAME ARENA برایت {body.quantity} عدد «{product.name}» ارسال کرد.")
        except Exception:
            pass
        return {"ok": True, "user_id": user.id, "product": product.name, "quantity": body.quantity}

@app.get("/api/admin/transactions")
async def admin_transactions(user_id: Optional[int] = None, limit: int = 50, uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    limit = max(1, min(200, limit))
    async with SessionLocal() as session:
        return {"transactions": await collect_economy_transactions(session, user_id, limit)}

@app.get("/api/admin/security/events")
async def admin_security_events(uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    async with SessionLocal() as session:
        rows = (await session.execute(select(SecurityEvent).order_by(SecurityEvent.created_at.desc()).limit(100))).scalars().all()
        open_count = await session.scalar(select(func.count()).select_from(SecurityEvent).where(SecurityEvent.reviewed == False))
        return {"open_count": int(open_count or 0), "events": [{"id": x.id, "user_id": x.user_id, "code": x.code,
                "severity": x.severity, "detail": x.detail, "reviewed": bool(x.reviewed),
                "created_at": x.created_at.isoformat()} for x in rows]}

@app.post("/api/admin/security/events/{event_id}/review")
async def admin_review_security_event(event_id: int, uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    async with SessionLocal() as session:
        event = await session.get(SecurityEvent, event_id)
        if not event:
            raise HTTPException(404, "گزارش پیدا نشد.")
        event.reviewed = True
        await session.commit()
        return {"ok": True}

@app.post("/api/admin/vip")
async def admin_set_vip(body: VipGrantInput, uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    async with SessionLocal() as session:
        user = await session.get(User, body.user_id)
        if not user: raise HTTPException(404, "کاربر پیدا نشد.")
        user.vip_tier = body.tier
        session.add(AdminAudit(admin_id=uid, action="vip_change", target_id=user.id, detail=f"VIP={body.tier}"))
        await session.commit()
        return {"ok": True, "user_id": user.id, "vip_tier": user.vip_tier}

@app.post("/api/admin/events")
async def admin_create_event(body: EventInput, uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    now = datetime.utcnow()
    async with SessionLocal() as session:
        event = ArenaEvent(title=body.title, description=body.description, bonus_xp=body.bonus_xp,
                           starts_at=now, ends_at=now + timedelta(hours=body.duration_hours), active=body.active)
        session.add(event); await session.flush()
        session.add(AdminAudit(admin_id=uid, action="event_create", target_id=event.id, detail=f"{event.title} · +{event.bonus_xp} XP"))
        await session.commit()
        return {"ok": True, "id": event.id}

@app.get("/api/admin/events")
async def admin_list_events(uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    async with SessionLocal() as session:
        rows = (await session.execute(select(ArenaEvent).order_by(ArenaEvent.created_at.desc()).limit(50))).scalars().all()
        return {"events": [{"id": e.id, "title": e.title, "description": e.description, "bonus_xp": e.bonus_xp, "starts_at": e.starts_at.isoformat(), "ends_at": e.ends_at.isoformat(), "active": e.active} for e in rows]}

@app.put("/api/admin/events/{event_id}/toggle")
async def admin_toggle_event(event_id: int, uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    async with SessionLocal() as session:
        event = await session.get(ArenaEvent, event_id)
        if not event: raise HTTPException(404, "رویداد پیدا نشد.")
        event.active = not event.active
        session.add(AdminAudit(admin_id=uid, action="event_toggle", target_id=event.id, detail=f"active={event.active}"))
        await session.commit()
        return {"ok": True, "active": event.active}

@app.get("/api/admin/audit")
async def admin_audit(uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    async with SessionLocal() as session:
        rows = (await session.execute(select(AdminAudit).order_by(AdminAudit.created_at.desc()).limit(100))).scalars().all()
        return {"items": [{"id": x.id, "action": x.action, "target_id": x.target_id, "detail": x.detail, "created_at": x.created_at.isoformat()} for x in rows]}

@app.get("/api/admin/tournaments")
async def admin_tournaments(uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    async with SessionLocal() as session:
        rows = (await session.execute(select(Tournament).order_by(Tournament.created_at.desc()))).scalars().all()
        result = []
        for item in rows:
            participants = (await session.execute(select(TournamentEntry.user_id).where(TournamentEntry.tournament_id == item.id))).scalars().all()
            result.append({"id": item.id, "name": item.name, "status": item.status, "prize_coins": item.prize_coins, "players": participants, "bracket": json.loads(item.bracket) if item.bracket else None})
        return {"tournaments": result}

@app.post("/api/admin/tournaments/{tournament_id}/start")
async def admin_start_tournament(tournament_id: int, uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    async with SessionLocal() as session:
        item = await session.get(Tournament, tournament_id)
        if not item or item.status != "open":
            raise HTTPException(400, "این تورنمنت در وضعیت ثبت‌نام نیست.")
        players = list((await session.execute(select(TournamentEntry.user_id).where(TournamentEntry.tournament_id == tournament_id))).scalars().all())
        if len(players) < 2:
            raise HTTPException(400, "برای شروع حداقل دو شرکت‌کننده لازم است.")
        random.shuffle(players)
        matches = []
        for idx in range(0, len(players), 2):
            p1 = players[idx]
            p2 = players[idx + 1] if idx + 1 < len(players) else None
            matches.append({"p1": p1, "p2": p2, "winner": p1 if p2 is None else None})
        item.bracket = json.dumps([matches])
        item.status = "running"
        await session.commit()
        return {"ok": True, "bracket": json.loads(item.bracket)}

@app.post("/api/admin/tournaments/{tournament_id}/match-result")
async def admin_tournament_match_result(tournament_id: int, body: TournamentMatchResult, uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    async with SessionLocal() as session:
        item = await session.get(Tournament, tournament_id)
        if not item or item.status != "running" or not item.bracket:
            raise HTTPException(400, "جدول حذفی فعال پیدا نشد.")
        bracket = json.loads(item.bracket)
        if body.round_index >= len(bracket) or body.match_index >= len(bracket[body.round_index]):
            raise HTTPException(404, "مسابقه پیدا نشد.")
        match = bracket[body.round_index][body.match_index]
        if match["winner"] is not None:
            raise HTTPException(400, "برنده این مسابقه قبلاً ثبت شده است.")
        if body.winner_id not in (match["p1"], match["p2"]):
            raise HTTPException(400, "برنده باید یکی از دو شرکت‌کننده همین مسابقه باشد.")
        match["winner"] = body.winner_id
        round_matches = bracket[body.round_index]
        if all(m["winner"] is not None for m in round_matches):
            winners = [m["winner"] for m in round_matches]
            if len(winners) == 1:
                champion = await session.get(User, winners[0])
                await add_coins(session, champion, item.prize_coins, f"قهرمانی تورنمنت {item.name}")
                item.status = "completed"
            else:
                next_round = []
                for idx in range(0, len(winners), 2):
                    p1 = winners[idx]
                    p2 = winners[idx + 1] if idx + 1 < len(winners) else None
                    next_round.append({"p1": p1, "p2": p2, "winner": p1 if p2 is None else None})
                bracket.append(next_round)
        item.bracket = json.dumps(bracket)
        await session.commit()
        return {"ok": True, "status": item.status, "bracket": bracket}

@app.post("/api/admin/tournaments")
async def admin_create_tournament(body: TournamentCreate, uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    async with SessionLocal() as session:
        item = Tournament(name=body.name, game=body.game, prize_coins=body.prize_coins, max_players=body.max_players)
        session.add(item)
        await session.commit()
        return {"ok": True, "id": item.id}

@app.get("/api/admin/leagues")
async def admin_get_leagues(uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    return {"leagues": [{"threshold": t, "title": title} for t, title in LEAGUES]}

@app.put("/api/admin/leagues")
async def admin_update_leagues(body: LeagueInput, uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    try:
        rows = sorted([(int(x["threshold"]), str(x["title"])[:50]) for x in body.leagues], key=lambda x: x[0])
        if not rows or rows[0][0] != 0 or any(rows[i][0] >= rows[i+1][0] for i in range(len(rows)-1)):
            raise ValueError()
    except Exception:
        raise HTTPException(400, "فهرست لیگ باید از امتیاز صفر شروع شود و آستانه‌ها صعودی باشند.")
    async with SessionLocal() as session:
        await session.execute(text("DELETE FROM league_config"))
        for threshold, title in rows:
            session.add(LeagueConfig(threshold=threshold, title=title))
        await session.commit()
    LEAGUES[:] = rows
    return {"ok": True, "leagues": [{"threshold": t, "title": title} for t, title in rows]}

@app.get("/api/admin/ttt-difficulty")
async def admin_get_ttt_difficulty(uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    return {"difficulty": TTT_DIFFICULTY}

@app.put("/api/admin/ttt-difficulty")
async def admin_set_ttt_difficulty(body: TTTHardnessInput, uid: int = Depends(require_user_id)):
    global TTT_DIFFICULTY
    await admin_guard(uid)
    async with SessionLocal() as session:
        row = await session.scalar(select(AppSetting).where(AppSetting.key == "ttt_difficulty"))
        if row is None:
            session.add(AppSetting(key="ttt_difficulty", value=body.difficulty))
        else:
            row.value = body.difficulty
        await session.commit()
    TTT_DIFFICULTY = body.difficulty
    return {"ok": True, "difficulty": TTT_DIFFICULTY}

@app.get("/api/admin/games")
async def admin_get_games(uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    return {"games": [{"id": key, "enabled": value} for key, value in GAME_STATUS.items() if key != "neon-runner"]}

@app.put("/api/admin/games")
async def admin_set_game(body: GameToggleInput, uid: int = Depends(require_user_id)):
    await admin_guard(uid)
    if body.game not in GAME_STATUS:
        raise HTTPException(404, "بازی ناشناخته است.")
    async with SessionLocal() as session:
        row = await session.scalar(select(GameConfig).where(GameConfig.game == body.game))
        if row is None:
            row = GameConfig(game=body.game, enabled=body.enabled)
            session.add(row)
        else:
            row.enabled = body.enabled
        await session.commit()
    GAME_STATUS[body.game] = body.enabled
    return {"ok": True, "game": body.game, "enabled": body.enabled}

# Telegram bot commands
async def start_keyboard():
    if WEBAPP_URL:
        return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🎮 ورود به GAME ARENA", web_app=WebAppInfo(url=WEBAPP_URL))], [KeyboardButton(text="👥 فهرست دوستان"), KeyboardButton(text="💬 ورود به چت کلن")], [KeyboardButton(text="⛔ خروج از چت کلن")]], resize_keyboard=True)
    return None

@dp.message(CommandStart())
async def start_command(message: Message):
    referrer = None
    dm_target = None
    if message.text:
        parts = message.text.split(maxsplit=1)
        if len(parts) > 1 and parts[1].startswith("ref_"):
            try: referrer = int(parts[1][4:])
            except ValueError: pass
        elif len(parts) > 1 and parts[1].startswith("dm_"):
            try: dm_target = int(parts[1][3:])
            except ValueError: pass
    async with SessionLocal() as session:
        user, created = await ensure_user(session, {
            "id": message.from_user.id,
            "first_name": message.from_user.first_name,
            "username": message.from_user.username,
        }, referrer)
    greeting = f"سلام {html.escape(message.from_user.first_name or 'قهرمان')}! ⚡\n\nبه <b>GAME ARENA 3.0</b> خوش اومدی؛ دنیای بازی، لیگ و رقابت."
    if created and referrer:
        greeting += "\n🎁 دعوتت ثبت شد؛ به بازی خوش اومدی!"
    if WEBAPP_URL:
        greeting += "\n\nبرای ورود به مینی‌اپ، دکمه زیر رو بزن."
    else:
        greeting += "\n\nمینی‌اپ هنوز به آدرس HTTPS متصل نشده است. مدیر باید WEBAPP_URL را در تنظیمات Railway ثبت کند."
    await message.answer(greeting, reply_markup=await start_keyboard(), parse_mode="HTML")
    if dm_target and dm_target != message.from_user.id:
        low, high = sorted((dm_target, message.from_user.id))
        async with SessionLocal() as session:
            link = await session.scalar(select(Friendship).where(Friendship.user_low == low, Friendship.user_high == high))
            target = await session.get(User, dm_target)
        async with SessionLocal() as session:
            blocked = await is_blocked_between(session, message.from_user.id, dm_target)
        if link and target and not target.is_banned and not blocked:
            PRIVATE_CHAT_TARGET[message.from_user.id] = dm_target
            await message.answer(f"💬 گفت‌وگو با {html.escape(target.first_name)} فعال شد. پیام بعدی‌ات را بنویس؛ برای پایان /enddm را بفرست.", parse_mode="HTML")
        else:
            await message.answer("برای شروع گفت‌وگو ابتدا باید درخواست دوستی پذیرفته شده باشد.")

@dp.message(Command("admin"))
async def admin_command(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ دسترسی نداری.")
        return
    async with SessionLocal() as session:
        users = await session.scalar(select(func.count()).select_from(User))
        xp = await session.scalar(select(func.coalesce(func.sum(User.xp), 0)))
        games = await session.scalar(select(func.coalesce(func.sum(User.games), 0)))
    await message.answer(f"👑 <b>پنل مدیر GAME ARENA</b>\n👥 کاربران: {users}\n🎮 مجموع بازی‌ها: {games}\n⭐ مجموع XP: {xp}", parse_mode="HTML")

@dp.message(Command("clanchat"))
async def clan_chat_start(message: Message):
    uid = message.from_user.id
    async with SessionLocal() as session:
        member = await session.scalar(select(ClanMember).where(ClanMember.user_id == uid))
        clan = await session.get(Clan, member.clan_id) if member else None
    if not member or not clan:
        await message.answer("برای استفاده از چت کلن، ابتدا عضو یک کلن شو.")
        return
    CLAN_CHAT_USERS.add(uid)
    async with SessionLocal() as session:
        recent = (await session.execute(select(ClanChatMessage).where(ClanChatMessage.clan_id == clan.id).order_by(ClanChatMessage.created_at.desc()).limit(3))).scalars().all()
    history = "\n\n".join(
        f"<b>{html.escape(row.sender_name)}</b> · <i>{row.created_at.strftime('%H:%M')}</i>\n{html.escape(row.message[:650])}"
        for row in reversed(recent)
    )
    body = f"💬 وارد چت کلن «{html.escape(clan.name)}» شدی. پیام‌هایت برای اعضای همین کلن ارسال می‌شود. برای خروج /exit را بفرست."
    if history:
        body += "\n\n<b>آخرین پیام‌ها:</b>\n" + history
    await message.answer(body, parse_mode="HTML")

@dp.message(Command("exit"))
async def clan_chat_exit(message: Message):
    CLAN_CHAT_USERS.discard(message.from_user.id)
    PRIVATE_CHAT_TARGET.pop(message.from_user.id, None)
    await message.answer("از چت فعال خارج شدی. برای چت کلن /clanchat یا برای پیام خصوصی /dm شناسه_دوست را بفرست.")

@dp.message(Command("friends"))
async def bot_friends(message: Message):
    uid = message.from_user.id
    async with SessionLocal() as session:
        links = (await session.execute(select(Friendship).where((Friendship.user_low == uid) | (Friendship.user_high == uid)))).scalars().all()
        friend_ids = [x.user_high if x.user_low == uid else x.user_low for x in links]
        people = (await session.execute(select(User).where(User.id.in_(friend_ids)))).scalars().all() if friend_ids else []
        requests = (await session.execute(select(FriendRequest).where(FriendRequest.target_id == uid, FriendRequest.status == "pending").order_by(FriendRequest.created_at.desc()).limit(20))).scalars().all()
        outgoing = (await session.execute(select(FriendRequest).where(FriendRequest.requester_id == uid, FriendRequest.status == "pending").limit(20))).scalars().all()
    body = "👥 <b>فهرست دوستان</b>\n" + ("\n".join(f"• {html.escape(u.first_name)} · <code>{u.id}</code>" for u in people) if people else "هنوز دوستی ثبت نشده است.")
    if requests:
        body += "\n\n<b>درخواست‌های ورودی:</b>\n" + "\n".join(f"• {html.escape((await _user_name(r.requester_id)))} · درخواست #{r.id} · <code>/friend_accept {r.id}</code>" for r in requests)
    if outgoing: body += f"\n\nدرخواست‌های در انتظار پاسخ: {len(outgoing)}"
    body += "\n\nافزودن دوست: <code>/friend شناسه</code>\nشروع گفت‌وگو: <code>/dm شناسه</code>"
    await message.answer(body, parse_mode="HTML")

async def _user_name(user_id: int) -> str:
    async with SessionLocal() as session:
        user = await session.get(User, user_id)
        return user.first_name if user else "بازیکن"

@dp.message(Command("friend"))
async def bot_friend_request(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("روش استفاده: /friend شناسه_عددی_کاربر")
        return
    target_id = int(parts[1]); uid = message.from_user.id
    if target_id == uid:
        await message.answer("نمی‌توانی برای خودت درخواست بفرستی."); return
    async with SessionLocal() as session:
        target = await session.get(User, target_id)
        if not target or target.is_banned:
            await message.answer("کاربر پیدا نشد یا فعال نیست."); return
        low, high = sorted((uid, target_id))
        linked = await session.scalar(select(Friendship).where(Friendship.user_low == low, Friendship.user_high == high))
        if linked:
            await message.answer("این کاربر از قبل دوست توست."); return
        existing = await session.scalar(select(FriendRequest).where(FriendRequest.requester_id == uid, FriendRequest.target_id == target_id, FriendRequest.status == "pending"))
        if existing:
            await message.answer("درخواست قبلاً ارسال شده است."); return
        reverse = await session.scalar(select(FriendRequest).where(FriendRequest.requester_id == target_id, FriendRequest.target_id == uid, FriendRequest.status == "pending"))
        if reverse:
            reverse.status = "accepted"; session.add(Friendship(user_low=low, user_high=high)); await session.commit()
            await message.answer("✅ درخواست دوطرفه بود؛ حالا دوست هستید."); return
        req = FriendRequest(requester_id=uid, target_id=target_id)
        session.add(req); await session.commit(); req_id = req.id
    if bot:
        try: await bot.send_message(target_id, f"👥 {html.escape(message.from_user.first_name)} برای دوستی دعوتت کرده. دستور /friends را بزن و درخواست #{req_id} را ببین.", parse_mode="HTML")
        except Exception: pass
    await message.answer(f"✅ درخواست دوستی ارسال شد. شناسه درخواست: {req_id}")

@dp.message(Command("friend_accept"))
async def bot_friend_accept(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].isdigit(): await message.answer("روش استفاده: /friend_accept شناسه_درخواست"); return
    req_id=int(parts[1]); uid=message.from_user.id
    async with SessionLocal() as session:
        req=await session.get(FriendRequest,req_id)
        if not req or req.target_id!=uid or req.status!="pending": await message.answer("درخواست معتبر پیدا نشد."); return
        req.status="accepted"; low,high=sorted((req.requester_id,req.target_id))
        exists=await session.scalar(select(Friendship).where(Friendship.user_low==low,Friendship.user_high==high))
        if not exists: session.add(Friendship(user_low=low,user_high=high))
        requester=req.requester_id; await session.commit()
    if bot:
        try: await bot.send_message(requester,"✅ درخواست دوستی‌ات پذیرفته شد. حالا می‌توانید با /dm شناسه همدیگر گفتگو کنید.")
        except Exception: pass
    await message.answer("✅ دوستی تأیید شد. برای گفتگو /dm شناسه_کاربر را بفرست.")

@dp.message(Command("friend_reject"))
async def bot_friend_reject(message: Message):
    parts=(message.text or "").split(maxsplit=1)
    if len(parts)<2 or not parts[1].isdigit(): await message.answer("روش استفاده: /friend_reject شناسه_درخواست"); return
    async with SessionLocal() as session:
        req=await session.get(FriendRequest,int(parts[1]))
        if not req or req.target_id!=message.from_user.id or req.status!="pending": await message.answer("درخواست معتبر پیدا نشد."); return
        req.status="rejected"; await session.commit()
    await message.answer("درخواست رد شد.")

@dp.message(Command("dm"))
async def bot_private_chat_start(message: Message):
    parts=(message.text or "").split(maxsplit=1)
    if len(parts)<2 or not parts[1].isdigit(): await message.answer("روش استفاده: /dm شناسه_دوست"); return
    uid=message.from_user.id; target_id=int(parts[1])
    if uid==target_id: await message.answer("نمی‌توانی با خودت گفت‌وگو کنی."); return
    low,high=sorted((uid,target_id))
    async with SessionLocal() as session:
        link=await session.scalar(select(Friendship).where(Friendship.user_low==low,Friendship.user_high==high))
        target=await session.get(User,target_id)
        blocked=await is_blocked_between(session,uid,target_id)
        if not link or not target or target.is_banned or blocked: await message.answer("گفت‌وگو فقط با دوستان تأییدشده و بدون مسدودسازی امکان‌پذیر است."); return
        history=(await session.execute(select(PrivateMessage).where(((PrivateMessage.sender_id==uid)&(PrivateMessage.recipient_id==target_id))|((PrivateMessage.sender_id==target_id)&(PrivateMessage.recipient_id==uid))).order_by(PrivateMessage.created_at.desc()).limit(5))).scalars().all()
    PRIVATE_CHAT_TARGET[uid]=target_id
    label=html.escape(target.first_name)
    await message.answer(f"💬 گفت‌وگو با <b>{label}</b> فعال شد. پیام‌هایت مستقیم برای دوستت ارسال می‌شود. برای پایان /enddm را بفرست.\n\n"+("\n\n".join(f"<b>{'تو' if x.sender_id==uid else 'دوستت'}:</b> {html.escape(x.message)}" for x in reversed(history)) if history else "هنوز پیامی ثبت نشده."),parse_mode="HTML")
    if bot:
        try:
            await bot.send_message(target_id, f"💬 {html.escape(message.from_user.first_name)} گفت‌وگو را شروع کرد. برای پاسخ‌دادن /dm {uid} را بفرست.",parse_mode="HTML")
        except Exception: pass

@dp.message(Command("enddm"))
async def bot_private_chat_end(message: Message):
    PRIVATE_CHAT_TARGET.pop(message.from_user.id,None)
    await message.answer("گفت‌وگوی خصوصی پایان یافت.")

@dp.message()
async def clan_chat_relay(message: Message):
    uid = message.from_user.id if message.from_user else 0
    if message.chat.type != "private" or not message.text:
        return
    if message.text.strip() == "💬 ورود به چت کلن":
        await clan_chat_start(message)
        return
    if message.text.strip() == "👥 فهرست دوستان":
        await bot_friends(message)
        return
    if message.text.strip() == "⛔ خروج از چت کلن":
        await clan_chat_exit(message)
        return
    if message.text.startswith("/"):
        return
    private_target = PRIVATE_CHAT_TARGET.get(uid)
    if private_target:
        clean_private = message.text.strip()
        if not clean_private: return
        if len(clean_private) > 900:
            await message.answer("پیام حداکثر ۹۰۰ نویسه است."); return
        now = time.monotonic()
        if now - CLAN_CHAT_LAST.get(uid, 0) < .8:
            await message.answer("کمی آهسته‌تر پیام بفرست."); return
        CLAN_CHAT_LAST[uid] = now
        low, high = sorted((uid, private_target))
        async with SessionLocal() as session:
            link = await session.scalar(select(Friendship).where(Friendship.user_low==low,Friendship.user_high==high))
            target = await session.get(User, private_target)
            blocked = await is_blocked_between(session, uid, private_target)
            if not link or not target or target.is_banned or blocked:
                PRIVATE_CHAT_TARGET.pop(uid,None)
                await message.answer("این ارتباط دیگر معتبر نیست یا مسدود شده؛ گفت‌وگو بسته شد."); return
            session.add(PrivateMessage(sender_id=uid,recipient_id=private_target,message=clean_private))
            await session.commit()
        try:
            if bot:
                await bot.send_message(private_target, f"💬 <b>{html.escape(message.from_user.first_name or 'دوست')}</b>:\n{html.escape(clean_private)}", parse_mode="HTML", disable_web_page_preview=True)
            await message.answer("✅ پیام ارسال شد.")
        except Exception:
            await message.answer("پیام ذخیره شد اما به دوستت تحویل نشد؛ او باید ربات را Start کرده باشد.")
        return
    if uid not in CLAN_CHAT_USERS:
        return
    clean = message.text.strip()
    if not clean:
        return
    if len(clean) > 900:
        await message.answer("پیام چت کلن حداکثر ۹۰۰ نویسه است.")
        return
    now = time.monotonic()
    if now - CLAN_CHAT_LAST.get(uid, 0) < 1.0:
        await message.answer("کمی آهسته‌تر پیام بفرست.")
        return
    CLAN_CHAT_LAST[uid] = now
    async with SessionLocal() as session:
        member = await session.scalar(select(ClanMember).where(ClanMember.user_id == uid))
        if not member:
            CLAN_CHAT_USERS.discard(uid)
            await message.answer("دیگر عضو کلنی نیستی؛ چت بسته شد.")
            return
        clan = await session.get(Clan, member.clan_id)
        peers = (await session.execute(select(ClanMember.user_id).where(ClanMember.clan_id == member.clan_id, ClanMember.user_id != uid))).scalars().all()
        session.add(ClanChatMessage(clan_id=member.clan_id, user_id=uid,
                                    sender_name=message.from_user.first_name or "بازیکن", message=clean))
        await session.commit()
    if not peers:
        await message.answer("پیامت ذخیره شد؛ وقتی عضو دیگری اضافه شود می‌تواند آن را در تاریخچه چت ببیند.")
        return
    sender = html.escape(message.from_user.first_name or "بازیکن")
    username = f" (@{html.escape(message.from_user.username)})" if message.from_user.username else ""
    text_body = html.escape(clean)
    sent = 0
    for peer_id in peers:
        try:
            if bot:
                await bot.send_message(peer_id, f"💬 <b>{sender}{username}</b> · <b>{html.escape(clan.name)}</b>\n{text_body}", parse_mode="HTML", disable_web_page_preview=True)
                sent += 1
        except Exception:
            continue
    if sent == 0:
        await message.answer("پیام ذخیره شد، اما به اعضا تحویل نشد؛ احتمالاً هنوز ربات را Start نکرده‌اند.")
    else:
        failed = max(0, len(peers) - sent)
        suffix = f" · تحویل‌نشده: {failed}" if failed else ""
        await message.answer(f"✅ پیام به {sent} عضو کلن تحویل شد{suffix}.")

async def run():
    global bot, bot_username
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN تنظیم نشده؛ در Railway آن را در Variables وارد کنید.")
    await init_db()
    bot = Bot(BOT_TOKEN)
    me = await bot.get_me()
    bot_username = me.username or ""
    if WEBAPP_URL:
        try:
            await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="🎮 GAME ARENA", web_app=WebAppInfo(url=WEBAPP_URL)))
        except Exception as exc:
            print(f"Could not set Telegram menu button: {exc}")
    config = uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="info", proxy_headers=True)
    server = uvicorn.Server(config)
    polling = asyncio.create_task(dp.start_polling(bot))
    try:
        await server.serve()
    finally:
        polling.cancel()
        try: await polling
        except asyncio.CancelledError: pass
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(run())
