"""
db.py — Async MySQL connection pool (used by the LangGraph checkpointer).

.env:
    MYSQL_HOST=localhost
    MYSQL_PORT=3306
    MYSQL_USER=root
    MYSQL_PASSWORD=your_password
    MYSQL_DATABASE=travel_planner      (create it first: CREATE DATABASE travel_planner;)
"""
import os

import aiomysql
from dotenv import load_dotenv

load_dotenv()


async def create_pool() -> aiomysql.Pool:
    return await aiomysql.create_pool(
        host=os.getenv("MYSQL_HOST", "localhost"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        db=os.getenv("MYSQL_DATABASE", "travel_planner"),
        charset="utf8mb4",
        autocommit=True,  # required by the checkpointer
        minsize=1,
        maxsize=10,       # up to 10 requests can use MySQL at the same time
    )