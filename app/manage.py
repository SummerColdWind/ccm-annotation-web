"""Offline administrator provisioning: python -m app.manage create-admin USERNAME"""
import argparse
import getpass
from .db import connect, default_db, initialize, password_hash


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["create-admin", "reset-password"])
    parser.add_argument("username")
    args = parser.parse_args()
    if not 2 <= len(args.username) <= 40:
        parser.error("用户名长度须为 2–40 个字符")
    first = getpass.getpass("Password (10–128 characters): ")
    if first != getpass.getpass("Confirm password: "):
        parser.error("Passwords do not match")
    hashed = password_hash(first)
    path = default_db()
    initialize(path)
    with connect(path) as db:
        if args.command == "create-admin":
            db.execute("INSERT INTO users(username,display_name,password_hash,role) VALUES(?,?,?,'admin')", (args.username,args.username,hashed))
        else:
            row = db.execute("SELECT id FROM users WHERE username=?", (args.username,)).fetchone()
            if not row:
                parser.error("User not found")
            db.execute("UPDATE users SET password_hash=? WHERE id=?", (hashed,row["id"]))
            db.execute("DELETE FROM sessions WHERE user_id=?", (row["id"],))
    print("Account updated.")


if __name__ == "__main__":
    main()
