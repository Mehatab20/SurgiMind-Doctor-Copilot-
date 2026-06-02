# =============================================================================
# database_manager.py
# SurgiMind – Persistent SQLite Database Manager
#
# WHAT THIS MODULE DOES:
#   1. Creates and manages two SQLite tables: Users and Reports
#   2. Handles doctor signup with secure password hashing (PBKDF2-SHA256)
#      Falls back to bcrypt automatically if installed
#   3. Handles login with constant-time password verification
#   4. Saves every completed AI assessment as a JSON blob linked to a user_id
#   5. Retrieves full report history per doctor
#   6. Provides a clean export function that fetches saved JSON from the DB
#
# ZERO EXTRA DEPENDENCIES:
#   Uses only Python standard library (sqlite3, hashlib, hmac, json, datetime)
#   Optional: pip install bcrypt  (automatically used if available, more secure)
#
# USAGE:
#   from database_manager import db
#
#   # Auth
#   result = db.signup("dr_smith", "Dr. Sarah Smith", "secure_pass123")
#   result = db.login("dr_smith", "secure_pass123")
#   user   = result["user"]
#
#   # Save report (call after every successful AI assessment)
#   db.save_report(user_id=1, patient_data=patient_data,
#                  ml_result=ml_result, full_report=report_dict)
#
#   # Fetch history
#   records = db.get_history(user_id=1, limit=20)
#
#   # Export single report JSON by record id
#   json_str = db.export_report_json(report_id=5, user_id=1)
# =============================================================================

import os
import sys
import json
import hmac
import sqlite3
import hashlib
import secrets
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

log = logging.getLogger("SurgiMind.DB")
logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")

# ── Database file location: stored next to this file ──────────────────────────
_HERE    = Path(__file__).resolve().parent
DB_PATH  = _HERE / "surgimind.db"

# ── PBKDF2 configuration (standard library – always available) ────────────────
PBKDF2_ITERATIONS = 390_000   # OWASP 2023 recommendation for SHA-256
PBKDF2_ALGORITHM  = "sha256"
SALT_BYTES        = 32


# =============================================================================
# PASSWORD HASHING  (auto-upgrades to bcrypt if installed)
# =============================================================================

def _hash_password(plain: str) -> str:
    """
    Hashes a plain-text password.
    Uses bcrypt if available (preferred), otherwise PBKDF2-SHA256.

    Returns a self-describing string like:
        pbkdf2$<hex_salt>$<hex_hash>
        bcrypt$<bcrypt_hash>
    """
    try:
        import bcrypt
        hashed = bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12))
        return "bcrypt$" + hashed.decode("utf-8")
    except ImportError:
        pass

    # PBKDF2-SHA256 fallback
    salt  = secrets.token_bytes(SALT_BYTES)
    key   = hashlib.pbkdf2_hmac(PBKDF2_ALGORITHM, plain.encode("utf-8"),
                                 salt, PBKDF2_ITERATIONS)
    return f"pbkdf2${salt.hex()}${key.hex()}"


def _verify_password(plain: str, stored: str) -> bool:
    """
    Verifies a plain-text password against a stored hash string.
    Handles both bcrypt and PBKDF2 formats transparently.
    Uses constant-time comparison to prevent timing attacks.
    """
    if not plain or not stored:
        return False

    try:
        if stored.startswith("bcrypt$"):
            import bcrypt
            hashed = stored[len("bcrypt$"):].encode("utf-8")
            return bcrypt.checkpw(plain.encode("utf-8"), hashed)
    except ImportError:
        pass

    if stored.startswith("pbkdf2$"):
        try:
            _, salt_hex, key_hex = stored.split("$")
            salt      = bytes.fromhex(salt_hex)
            known_key = bytes.fromhex(key_hex)
            candidate = hashlib.pbkdf2_hmac(PBKDF2_ALGORITHM,
                                            plain.encode("utf-8"),
                                            salt, PBKDF2_ITERATIONS)
            return hmac.compare_digest(candidate, known_key)
        except Exception:
            return False

    return False


# =============================================================================
# SESSION TOKEN  (lightweight, stateless, no JWT dependency)
# =============================================================================

_TOKEN_SECRET = os.environ.get("SURGIMIND_SECRET",
                                secrets.token_hex(32))   # random each process start

def _make_token(user_id: int, username: str) -> str:
    """
    Creates a signed session token: <user_id>:<username>:<hmac_signature>
    The HMAC prevents forgery without needing a JWT library.
    """
    payload   = f"{user_id}:{username}"
    sig       = hmac.new(_TOKEN_SECRET.encode(), payload.encode(), "sha256").hexdigest()
    return f"{payload}:{sig}"


def _verify_token(token: str) -> Optional[dict]:
    """
    Verifies a session token and returns {"user_id": int, "username": str} or None.
    """
    try:
        parts = token.split(":")
        if len(parts) != 3:
            return None
        user_id_str, username, sig = parts
        payload   = f"{user_id_str}:{username}"
        expected  = hmac.new(_TOKEN_SECRET.encode(), payload.encode(), "sha256").hexdigest()
        if hmac.compare_digest(sig, expected):
            return {"user_id": int(user_id_str), "username": username}
    except Exception:
        pass
    return None


# =============================================================================
# DATABASE CLASS
# =============================================================================

class SurgiMindDB:
    """
    Single-instance database manager for SurgiMind.
    Thread-safe for Streamlit's multi-session model via check_same_thread=False.

    All public methods return a result dict:
        {"ok": True,  ...data...}
        {"ok": False, "error": "message"}
    """

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()
        log.info(f"SurgiMind DB ready: {self.db_path}")

    # =========================================================================
    # SCHEMA INITIALISATION
    # =========================================================================

    def _connect(self) -> sqlite3.Connection:
        """Opens a connection with foreign keys and row-factory enabled."""
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory   = sqlite3.Row   # column access by name
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")   # safe concurrent reads
        return conn

    def _init_db(self) -> None:
        """
        Creates all tables if they don't already exist.
        Schema is forward-compatible: new columns can be added via ALTER TABLE.
        """
        with self._connect() as conn:
            conn.executescript("""
            -- ── Users table ──────────────────────────────────────────────────
            CREATE TABLE IF NOT EXISTS users (
                id              INTEGER  PRIMARY KEY AUTOINCREMENT,
                username        TEXT     NOT NULL UNIQUE COLLATE NOCASE,
                full_name       TEXT     NOT NULL DEFAULT '',
                password_hash   TEXT     NOT NULL,
                speciality      TEXT     NOT NULL DEFAULT 'General Surgery',
                hospital        TEXT     NOT NULL DEFAULT '',
                created_at      TEXT     NOT NULL
                                DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                last_login      TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

            -- ── Reports table ─────────────────────────────────────────────────
            CREATE TABLE IF NOT EXISTS reports (
                id              INTEGER  PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER  NOT NULL REFERENCES users(id) ON DELETE CASCADE,

                -- Patient demographics (indexed for fast history queries)
                patient_name    TEXT     NOT NULL DEFAULT 'Unknown',
                age             REAL,
                gender          TEXT,
                admission_type  TEXT,
                diagnosis       TEXT,
                surgery_type    TEXT,

                -- ML output (denormalised for quick dashboard display)
                risk_level      TEXT     NOT NULL DEFAULT 'UNKNOWN',
                confidence      TEXT     NOT NULL DEFAULT 'N/A',
                concerns        TEXT,           -- JSON array string

                -- Full JSON blobs
                patient_json    TEXT     NOT NULL DEFAULT '{}',  -- full patient_data dict
                report_json     TEXT     NOT NULL DEFAULT '{}',  -- full AI report dict
                ml_json         TEXT     NOT NULL DEFAULT '{}',  -- ML prediction dict

                -- Metadata
                llm_backend     TEXT     NOT NULL DEFAULT 'unknown',
                created_at      TEXT     NOT NULL
                                DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            );
            CREATE INDEX IF NOT EXISTS idx_reports_user    ON reports(user_id);
            CREATE INDEX IF NOT EXISTS idx_reports_created ON reports(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_reports_risk    ON reports(risk_level);
            """)
        log.info("DB schema initialised (Users + Reports tables ready)")

    # =========================================================================
    # AUTHENTICATION
    # =========================================================================

    def signup(
        self,
        username    : str,
        full_name   : str,
        password    : str,
        speciality  : str = "General Surgery",
        hospital    : str = "",
    ) -> dict:
        """
        Registers a new doctor account.

        Args:
            username   : Unique login handle (case-insensitive)
            full_name  : Display name shown in dashboard
            password   : Plain-text password (hashed before storage)
            speciality : Medical specialty (optional, for display)
            hospital   : Hospital/institution (optional)

        Returns:
            {"ok": True, "user_id": int, "token": str, "user": dict}
            {"ok": False, "error": str}
        """
        if not username or len(username.strip()) < 3:
            return {"ok": False, "error": "Username must be at least 3 characters."}
        if not password or len(password) < 6:
            return {"ok": False, "error": "Password must be at least 6 characters."}
        if not full_name.strip():
            return {"ok": False, "error": "Full name is required."}

        username = username.strip().lower()
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """INSERT INTO users (username, full_name, password_hash,
                                         speciality, hospital)
                       VALUES (?, ?, ?, ?, ?)""",
                    (username, full_name.strip(), _hash_password(password),
                     speciality, hospital),
                )
                user_id = cur.lastrowid
                token   = _make_token(user_id, username)
                user    = self._get_user_by_id(conn, user_id)
                log.info(f"New account created: {username} (id={user_id})")
                return {"ok": True, "user_id": user_id, "token": token, "user": user}

        except sqlite3.IntegrityError:
            return {"ok": False, "error": f"Username '{username}' is already taken."}
        except Exception as e:
            log.error(f"Signup error: {e}")
            return {"ok": False, "error": "Account creation failed. Please try again."}

    def login(self, username: str, password: str) -> dict:
        """
        Authenticates a doctor.

        Returns:
            {"ok": True, "user_id": int, "token": str, "user": dict}
            {"ok": False, "error": str}
        """
        if not username or not password:
            return {"ok": False, "error": "Username and password are required."}

        username = username.strip().lower()
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT id, password_hash FROM users WHERE username = ?",
                    (username,)
                ).fetchone()

                if not row or not _verify_password(password, row["password_hash"]):
                    return {"ok": False, "error": "Invalid username or password."}

                user_id = row["id"]
                # Update last_login timestamp
                conn.execute(
                    "UPDATE users SET last_login = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id = ?",
                    (user_id,)
                )
                token = _make_token(user_id, username)
                user  = self._get_user_by_id(conn, user_id)
                log.info(f"Login successful: {username} (id={user_id})")
                return {"ok": True, "user_id": user_id, "token": token, "user": user}

        except Exception as e:
            log.error(f"Login error: {e}")
            return {"ok": False, "error": "Login failed. Please try again."}

    def verify_session_token(self, token: str) -> Optional[dict]:
        """
        Validates a session token and returns the user record, or None.
        Used to restore sessions on browser refresh.
        """
        payload = _verify_token(token)
        if not payload:
            return None
        try:
            with self._connect() as conn:
                return self._get_user_by_id(conn, payload["user_id"])
        except Exception:
            return None

    def _get_user_by_id(self, conn: sqlite3.Connection, user_id: int) -> dict:
        """Returns a clean user dict (no password_hash) for a given user_id."""
        row = conn.execute(
            "SELECT id, username, full_name, speciality, hospital, created_at, last_login "
            "FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()
        if row:
            return dict(row)
        return {}

    # =========================================================================
    # REPORT PERSISTENCE
    # =========================================================================

    def save_report(
        self,
        user_id      : int,
        patient_data : dict,
        ml_result    : dict,
        full_report  : dict,
    ) -> dict:
        """
        Saves a complete AI assessment to the Reports table.

        Called automatically after every successful assessment in app.py.

        Args:
            user_id      : The logged-in doctor's user_id
            patient_data : The full patient form dict (demographics + vitals + labs)
            ml_result    : Output from predict_risk() (risk_level, confidence, etc.)
            full_report  : Output from generate_report() (the complete AI report dict)

        Returns:
            {"ok": True, "report_id": int}
            {"ok": False, "error": str}
        """
        try:
            # ── Extract denormalised fields for fast querying ─────────────────
            patient_name  = str(patient_data.get("patient_name", "Unknown"))[:200]
            age           = patient_data.get("age")
            gender        = str(patient_data.get("gender", ""))[:20]
            admission_type= str(patient_data.get("admission_type", ""))[:50]
            diagnosis     = str(patient_data.get("diagnosis", ""))[:500]
            surgery_type  = str(patient_data.get("surgery_type", ""))[:200]

            risk_level    = str(ml_result.get("risk_level", "UNKNOWN"))[:10]
            confidence    = str(ml_result.get("confidence", "N/A"))[:15]
            concerns      = json.dumps(ml_result.get("possible_concerns", []))
            llm_backend   = str(full_report.get("llm_backend_used", "unknown"))[:50]

            # ── Serialise full blobs ──────────────────────────────────────────
            patient_json  = json.dumps(patient_data, default=str)
            ml_json       = json.dumps(ml_result,    default=str)
            report_json   = json.dumps(full_report,  default=str)

            with self._connect() as conn:
                cur = conn.execute(
                    """INSERT INTO reports
                       (user_id, patient_name, age, gender, admission_type,
                        diagnosis, surgery_type, risk_level, confidence,
                        concerns, patient_json, report_json, ml_json, llm_backend)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (user_id, patient_name, age, gender, admission_type,
                     diagnosis, surgery_type, risk_level, confidence,
                     concerns, patient_json, report_json, ml_json, llm_backend)
                )
                report_id = cur.lastrowid
                log.info(f"Report saved: id={report_id} user={user_id} "
                         f"patient='{patient_name}' risk={risk_level}")
                return {"ok": True, "report_id": report_id}

        except Exception as e:
            log.error(f"save_report error: {e}")
            return {"ok": False, "error": f"Failed to save report: {e}"}

    # =========================================================================
    # HISTORY RETRIEVAL
    # =========================================================================

    def get_history(
        self,
        user_id : int,
        limit   : int  = 50,
        offset  : int  = 0,
        risk_filter : Optional[str] = None,   # "HIGH" | "MEDIUM" | "LOW" | None
    ) -> dict:
        """
        Fetches all assessments for a doctor (summary rows, no full JSON blobs).
        Used to populate the Recent Activity panel on the dashboard.

        Args:
            user_id     : Logged-in doctor's id
            limit       : Max rows to return (default 50)
            offset      : Pagination offset
            risk_filter : If set, only returns records matching that risk level

        Returns:
            {"ok": True, "records": [list of dicts], "total": int}
        """
        try:
            with self._connect() as conn:
                # Total count query
                count_sql  = "SELECT COUNT(*) FROM reports WHERE user_id = ?"
                count_args = [user_id]
                if risk_filter:
                    count_sql += " AND risk_level = ?"
                    count_args.append(risk_filter.upper())
                total = conn.execute(count_sql, count_args).fetchone()[0]

                # Summary rows (no full JSON blobs – fast)
                select_sql = """
                    SELECT id, patient_name, age, gender, admission_type,
                           diagnosis, surgery_type, risk_level, confidence,
                           concerns, llm_backend,
                           strftime('%d %b %Y %H:%M', created_at) as formatted_date,
                           created_at
                    FROM   reports
                    WHERE  user_id = ?
                """
                args = [user_id]
                if risk_filter:
                    select_sql += " AND risk_level = ?"
                    args.append(risk_filter.upper())
                select_sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
                args += [limit, offset]

                rows    = conn.execute(select_sql, args).fetchall()
                records = []
                for row in rows:
                    d = dict(row)
                    # Parse concerns back from JSON string
                    try:
                        d["concerns"] = json.loads(d.get("concerns") or "[]")
                    except Exception:
                        d["concerns"] = []
                    records.append(d)

                return {"ok": True, "records": records, "total": total}

        except Exception as e:
            log.error(f"get_history error: {e}")
            return {"ok": False, "error": str(e), "records": [], "total": 0}

    def get_report_by_id(self, report_id: int, user_id: int) -> dict:
        """
        Fetches a single complete report including full JSON blobs.
        Used to reload a past assessment into the dashboard.

        Enforces ownership: user_id must match (prevents cross-user access).

        Returns:
            {"ok": True, "report": dict, "patient_data": dict,
                          "ml_result": dict, "full_report": dict}
            {"ok": False, "error": str}
        """
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT * FROM reports WHERE id = ? AND user_id = ?",
                    (report_id, user_id)
                ).fetchone()

                if not row:
                    return {"ok": False,
                            "error": "Report not found or access denied."}

                d = dict(row)
                # Deserialise JSON blobs
                patient_data = json.loads(d.get("patient_json") or "{}")
                ml_result    = json.loads(d.get("ml_json")      or "{}")
                full_report  = json.loads(d.get("report_json")  or "{}")
                try:
                    d["concerns"] = json.loads(d.get("concerns") or "[]")
                except Exception:
                    d["concerns"] = []

                return {
                    "ok"          : True,
                    "report"      : d,
                    "patient_data": patient_data,
                    "ml_result"   : ml_result,
                    "full_report" : full_report,
                }

        except Exception as e:
            log.error(f"get_report_by_id error: {e}")
            return {"ok": False, "error": str(e)}

    # =========================================================================
    # EXPORT
    # =========================================================================

    def export_report_json(self, report_id: int, user_id: int) -> Optional[str]:
        """
        Returns the raw report_json string for download.
        Fetches directly from DB so it is always the authoritative saved copy.

        Used by the 'Export JSON' download button in app.py.

        Returns:
            Pretty-printed JSON string, or None if not found / access denied.
        """
        result = self.get_report_by_id(report_id, user_id)
        if not result["ok"]:
            return None
        # Return the full_report dict pretty-printed
        return json.dumps(result["full_report"], indent=2, default=str)

    def export_all_history_csv(self, user_id: int) -> str:
        """
        Exports a summary CSV of all assessments for a doctor.
        Returns a CSV string (header + rows).
        """
        result = self.get_history(user_id, limit=10_000)
        if not result["ok"] or not result["records"]:
            return "No records found."

        import csv, io
        fieldnames = ["id", "patient_name", "age", "gender", "admission_type",
                      "diagnosis", "surgery_type", "risk_level", "confidence",
                      "llm_backend", "formatted_date"]
        buf = io.StringIO()
        w   = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(result["records"])
        return buf.getvalue()

    # =========================================================================
    # ANALYTICS  (for dashboard stats cards)
    # =========================================================================

    def get_stats(self, user_id: int) -> dict:
        """
        Returns aggregate statistics for a doctor's dashboard:
            total_reports, high_count, medium_count, low_count,
            latest_report_date, most_common_diagnosis

        Returns:
            {"ok": True, "stats": dict}
        """
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """SELECT
                           COUNT(*)                                              AS total,
                           SUM(CASE WHEN risk_level='HIGH'   THEN 1 ELSE 0 END) AS high,
                           SUM(CASE WHEN risk_level='MEDIUM' THEN 1 ELSE 0 END) AS medium,
                           SUM(CASE WHEN risk_level='LOW'    THEN 1 ELSE 0 END) AS low,
                           MAX(created_at)                                       AS latest
                       FROM reports WHERE user_id = ?""",
                    (user_id,)
                ).fetchone()

                stats = {
                    "total_reports"     : row["total"]  or 0,
                    "high_count"        : row["high"]   or 0,
                    "medium_count"      : row["medium"] or 0,
                    "low_count"         : row["low"]    or 0,
                    "latest_report_date": row["latest"] or "Never",
                }
                return {"ok": True, "stats": stats}

        except Exception as e:
            log.error(f"get_stats error: {e}")
            return {"ok": False, "stats": {}, "error": str(e)}

    # =========================================================================
    # ACCOUNT MANAGEMENT
    # =========================================================================

    def update_profile(
        self,
        user_id   : int,
        full_name : Optional[str] = None,
        speciality: Optional[str] = None,
        hospital  : Optional[str] = None,
    ) -> dict:
        """Updates display fields for a doctor's profile."""
        try:
            fields, values = [], []
            if full_name  is not None: fields.append("full_name = ?");  values.append(full_name.strip())
            if speciality is not None: fields.append("speciality = ?"); values.append(speciality.strip())
            if hospital   is not None: fields.append("hospital = ?");   values.append(hospital.strip())
            if not fields:
                return {"ok": False, "error": "No fields to update."}
            values.append(user_id)
            with self._connect() as conn:
                conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", values)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def change_password(
        self,
        user_id     : int,
        old_password: str,
        new_password: str,
    ) -> dict:
        """Verifies old password and replaces it with a new hash."""
        if len(new_password) < 6:
            return {"ok": False, "error": "New password must be at least 6 characters."}
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT password_hash FROM users WHERE id = ?", (user_id,)
                ).fetchone()
                if not row or not _verify_password(old_password, row["password_hash"]):
                    return {"ok": False, "error": "Current password is incorrect."}
                conn.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (_hash_password(new_password), user_id)
                )
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def delete_report(self, report_id: int, user_id: int) -> dict:
        """Deletes a single report. Enforces ownership check."""
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    "DELETE FROM reports WHERE id = ? AND user_id = ?",
                    (report_id, user_id)
                )
                if cur.rowcount == 0:
                    return {"ok": False, "error": "Report not found or access denied."}
            log.info(f"Report {report_id} deleted by user {user_id}")
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}


# =============================================================================
# MODULE-LEVEL SINGLETON
# =============================================================================

#: The single database instance – import this everywhere:
#:   from database_manager import db
db = SurgiMindDB()


# =============================================================================
# STREAMLIT SESSION HELPERS
# =============================================================================
#
# These functions wrap the db calls with Streamlit session_state management.
# Import them directly into app.py to keep the UI code clean.
#

def st_is_logged_in() -> bool:
    """Returns True if there is a valid session in Streamlit session_state."""
    try:
        import streamlit as st
        return bool(st.session_state.get("user"))
    except ImportError:
        return False


def st_login(username: str, password: str) -> dict:
    """
    Authenticates and stores the session in Streamlit session_state.
    Returns the db.login() result dict.
    """
    import streamlit as st
    result = db.login(username, password)
    if result["ok"]:
        st.session_state["user"]  = result["user"]
        st.session_state["token"] = result["token"]
        st.session_state["user_id"] = result["user_id"]
        # Clear any stale report state from previous session
        for key in ["report", "ml_result", "checks"]:
            st.session_state.pop(key, None)
    return result


def st_signup(username: str, full_name: str, password: str,
              speciality: str = "General Surgery", hospital: str = "") -> dict:
    """Signs up and auto-logs-in via Streamlit session_state."""
    import streamlit as st
    result = db.signup(username, full_name, password, speciality, hospital)
    if result["ok"]:
        st.session_state["user"]    = result["user"]
        st.session_state["token"]   = result["token"]
        st.session_state["user_id"] = result["user_id"]
    return result


def st_logout() -> None:
    """Clears all session state to log out."""
    import streamlit as st
    for key in ["user", "token", "user_id", "report", "ml_result", "checks", "n_preds"]:
        st.session_state.pop(key, None)


def st_restore_session() -> bool:
    """
    Called at the top of app.py to restore session from token after page refresh.
    Returns True if a valid session was restored.
    """
    import streamlit as st
    if st.session_state.get("user"):
        return True   # already logged in
    token = st.session_state.get("token")
    if token:
        user = db.verify_session_token(token)
        if user:
            st.session_state["user"]    = user
            st.session_state["user_id"] = user["id"]
            return True
    return False


def st_save_report_after_assessment(patient_data: dict,
                                    ml_result: dict,
                                    full_report: dict) -> Optional[int]:
    """
    Saves the assessment and returns the new report_id.
    Stores report_id in session_state for the Export button.
    Called immediately after generate_report() in app.py.

    Returns:
        int report_id on success, None on failure
    """
    import streamlit as st
    user_id = st.session_state.get("user_id")
    if not user_id:
        log.warning("st_save_report_after_assessment: no user_id in session")
        return None

    result = db.save_report(user_id, patient_data, ml_result, full_report)
    if result["ok"]:
        st.session_state["last_report_id"] = result["report_id"]
        return result["report_id"]
    else:
        log.error(f"Could not save report: {result['error']}")
        return None


def st_export_report_json() -> Optional[str]:
    """
    Called by the 'Export JSON' download button.
    Fetches from DB using the saved report_id (not from session_state report dict).
    Returns pretty-printed JSON string or None.
    """
    import streamlit as st
    report_id = st.session_state.get("last_report_id")
    user_id   = st.session_state.get("user_id")
    if not report_id or not user_id:
        # Fallback: export from session_state report if available
        report = st.session_state.get("report")
        if report:
            return json.dumps(report, indent=2, default=str)
        return None
    return db.export_report_json(report_id, user_id)


# =============================================================================
# SELF-TEST  –  python database_manager.py
# =============================================================================

if __name__ == "__main__":

    if os.path.exists("surgimind_test.db"):
        os.remove("surgimind_test.db")

    db = SurgiMindDB("surgimind_test.db")

    print("\n" + "="*60)
    print("  SurgiMind Database Manager – Self-Test")
    print("="*60)

    # Use a temporary test DB to avoid polluting the real one
    test_db = SurgiMindDB(db_path=Path("surgimind_test.db"))

    # ── Test signup ───────────────────────────────────────────────────────────
    print("\n[1] Signup")
    r = test_db.signup("dr.smith", "Dr. Sarah Smith", "securePass123",
                       "Cardiac Surgery", "City General Hospital")
    assert r["ok"], f"Signup failed: {r}"
    user_id = r["user_id"]
    token   = r["token"]
    print(f"    ✓ user_id={user_id}  token={token[:30]}…")

    # Duplicate signup
    r2 = test_db.signup("dr.smith", "Duplicate", "pass123")
    assert not r2["ok"], "Should reject duplicate username"
    print(f"    ✓ Duplicate rejected: {r2['error']}")

    # ── Test login ────────────────────────────────────────────────────────────
    print("\n[2] Login")
    r = test_db.login("dr.smith", "securePass123")
    assert r["ok"], f"Login failed: {r}"
    print(f"    ✓ Welcome back: {r['user']['full_name']}")

    r = test_db.login("dr.smith", "wrongPassword")
    assert not r["ok"]
    print(f"    ✓ Wrong password rejected: {r['error']}")

    # ── Test token verification ───────────────────────────────────────────────
    print("\n[3] Session Token")
    user = test_db.verify_session_token(token)
    assert user and user["username"] == "dr.smith"
    print(f"    ✓ Token verified for: {user['full_name']}")
    assert test_db.verify_session_token("bad:token:12345") is None
    print("    ✓ Invalid token correctly rejected")

    # ── Test save_report ──────────────────────────────────────────────────────
    print("\n[4] Save Report")
    patient_data = {
        "patient_name": "John Smith",  "age": 74, "gender": "Male",
        "admission_type": "Emergency", "diagnosis": "sepsis",
        "symptoms": "fever hypotension altered mental status",
        "surgery_type": "exploratory laparotomy",
        "blood_pressure": "82/50",     "heart_rate": 118,
        "glucose": 245.0, "creatinine": 3.2, "wbc": 18.4,
        "lactate": 4.8,   "sodium": 132.0,   "potassium": 5.8, "troponin": 0.09,
    }
    ml_result = {
        "risk_level": "HIGH", "confidence": "91%",
        "possible_concerns": ["Sepsis", "Advanced Age (>70)"],
        "clinical_text": "sepsis emergency male elderly high_severity_diagnosis",
    }
    full_report = {
        "probable_diagnosis"  : "High-acuity sepsis with multi-organ involvement.",
        "surgical_options"    : ["RECOMMENDATION 1: Damage control surgery"],
        "red_flags"           : [{"lab":"LACTATE","reason":"Severe hypoperfusion","severity":"CRITICAL"}],
        "contraindications"   : ["Elective surgery contraindicated"],
        "preop_checklist"     : ["Blood cultures x2", "IV antibiotics within 1 hour"],
        "ai_summary"          : "This patient presents with HIGH surgical risk.",
        "llm_backend_used"    : "rule-based",
        "retrieved_guidelines": [],
    }
    r = test_db.save_report(user_id, patient_data, ml_result, full_report)
    assert r["ok"], f"Save failed: {r}"
    report_id = r["report_id"]
    print(f"    ✓ Report saved: id={report_id}")

    # Save a second report (MEDIUM)
    ml_result2 = {**ml_result, "risk_level": "MEDIUM", "confidence": "72%",
                  "possible_concerns": ["Pneumonia"]}
    patient_data2 = {**patient_data, "patient_name": "Jane Doe",
                     "diagnosis": "pneumonia", "age": 55}
    test_db.save_report(user_id, patient_data2, ml_result2,
                        {**full_report, "risk_level": "MEDIUM"})
    print("    ✓ Second report (MEDIUM) saved")

    # ── Test get_history ──────────────────────────────────────────────────────
    print("\n[5] History Retrieval")
    r = test_db.get_history(user_id)
    assert r["ok"] and r["total"] == 2, f"Expected 2 records, got {r['total']}"
    print(f"    ✓ Total records: {r['total']}")
    for rec in r["records"]:
        print(f"      [{rec['risk_level']:6}] {rec['patient_name']}  |  {rec['formatted_date']}")

    # Filtered
    r = test_db.get_history(user_id, risk_filter="HIGH")
    assert r["total"] == 1
    print(f"    ✓ HIGH-only filter: {r['total']} record")

    # ── Test get_report_by_id ─────────────────────────────────────────────────
    print("\n[6] Load Report by ID")
    r = test_db.get_report_by_id(report_id, user_id)
    assert r["ok"]
    assert r["patient_data"]["patient_name"] == "John Smith"
    assert r["ml_result"]["risk_level"] == "HIGH"
    print(f"    ✓ Loaded: {r['patient_data']['patient_name']} | {r['ml_result']['risk_level']}")

    # Cross-user access denied
    r = test_db.get_report_by_id(report_id, user_id=9999)
    assert not r["ok"]
    print(f"    ✓ Cross-user access denied: {r['error']}")

    # ── Test export ───────────────────────────────────────────────────────────
    print("\n[7] Export JSON")
    json_str = test_db.export_report_json(report_id, user_id)
    assert json_str, "Export returned None"
    parsed = json.loads(json_str)
    assert "preop_checklist" in parsed
    print(f"    ✓ Exported {len(json_str)} chars of valid JSON")

    csv_str = test_db.export_all_history_csv(user_id)
    assert "sepsis" in csv_str.lower()
    print(f"    ✓ CSV export: {len(csv_str.splitlines())} lines")

    # ── Test stats ────────────────────────────────────────────────────────────
    print("\n[8] Dashboard Stats")
    r = test_db.get_stats(user_id)
    assert r["ok"]
    s = r["stats"]
    print(f"    ✓ Total={s['total_reports']}  HIGH={s['high_count']}  "
          f"MEDIUM={s['medium_count']}  LOW={s['low_count']}")

    # ── Test delete ───────────────────────────────────────────────────────────
    print("\n[9] Delete Report")
    r = test_db.delete_report(report_id, user_id)
    assert r["ok"]
    r2 = test_db.get_history(user_id)
    assert r2["total"] == 1
    print(f"    ✓ Report deleted. Remaining: {r2['total']}")

    # =========================================================================
    # FINAL CORRECTED CLEANUP FOR WINDOWS
    # =========================================================================
    test_file = "surgimind_test.db"
    
    try:
        import gc
        import time
        
        log.info("Cleaning up test environment...")
        
        # 1. Force the SQLite connection to close by deleting the object
        del test_db 
        
        # 2. Trigger garbage collection to ensure the file handle is released
        gc.collect() 
        
        # 3. Short pause to allow Windows to register the file is free
        time.sleep(0.5) 
        
        # 4. Attempt to delete the test file
        if os.path.exists(test_file):
            os.unlink(test_file)
            log.info(f"✓ Test database {test_file} cleaned up successfully.")
            
    except Exception as e:
        log.warning(f"⚠️ Could not auto-delete test file: {e}")
        log.info(f"You may need to delete '{test_file}' manually.")
    print("\n" + "="*60)
    print("  ✅  All tests passed. Database Manager is production-ready.")
    print("="*60 + "\n")