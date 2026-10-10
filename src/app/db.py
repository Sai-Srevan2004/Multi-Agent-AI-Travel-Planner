"""
db.py — Local MySQL connection and the LangGraph checkpointer.

.env:
    MYSQL_HOST=localhost
    MYSQL_PORT=3306
    MYSQL_USER=root
    MYSQL_PASSWORD=your_password
    MYSQL_DATABASE=travel_planner      (create it first: CREATE DATABASE travel_planner;)
"""
import os

import pymysql
from dotenv import load_dotenv
from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver

load_dotenv()


def get_mysql_connection():
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("MYSQL_DATABASE", "travel_planner"),
        charset="utf8mb4",
        autocommit=True,  # required by the checkpointer
    )


def get_checkpointer() -> PyMySQLSaver:
    checkpointer = PyMySQLSaver(get_mysql_connection())
    checkpointer.setup()  # creates the checkpoint tables if they don't exist
    return checkpointer