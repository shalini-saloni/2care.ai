import sqlite3
import json
import logging
from datetime import datetime
from app.core.config import settings

logger = logging.getLogger(__name__)

class DatabaseDAL:
    def __init__(self, db_path="./2care.db"):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            # Patients Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS patients (
                    id TEXT PRIMARY KEY,
                    phone TEXT UNIQUE,
                    name TEXT,
                    language_pref TEXT,
                    history TEXT
                )
            ''')
            # Doctors Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS doctors (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    specialization TEXT
                )
            ''')
            # Appointments Table
            # Unique constraint enforces conflict resolution at DB level
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS appointments (
                    id TEXT PRIMARY KEY,
                    patient_id TEXT,
                    doctor_id TEXT,
                    date TEXT,
                    time TEXT,
                    status TEXT,
                    UNIQUE(doctor_id, date, time),
                    FOREIGN KEY(patient_id) REFERENCES patients(id),
                    FOREIGN KEY(doctor_id) REFERENCES doctors(id)
                )
            ''')
            
            # Seed Doctors if none exist
            cursor.execute('SELECT count(*) FROM doctors')
            if cursor.fetchone()[0] == 0:
                self._seed_doctors(cursor)
                
            conn.commit()
    
    def _seed_doctors(self, cursor):
        doctors = [
            ("doc_1", "Dr. Sharma", "General Physician"),
            ("doc_2", "Dr. Iyer", "Cardiologist"),
            ("doc_3", "Dr. Khan", "Pediatrician")
        ]
        cursor.executemany('INSERT INTO doctors (id, name, specialization) VALUES (?, ?, ?)', doctors)
        logger.info("Seeded initial doctors.")

    def get_patient_by_phone(self, phone: str):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM patients WHERE phone = ?', (phone,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
            
    def create_patient(self, patient_id: str, phone: str, name: str, language_pref: str = "English"):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT INTO patients (id, phone, name, language_pref, history) VALUES (?, ?, ?, ?, ?)',
                           (patient_id, phone, name, language_pref, "[]"))
            conn.commit()

    def get_doctor_availability(self, doctor_id: str, date: str):
        # Very simplified wrapper: return standard slots minus booked ones.
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT time FROM appointments WHERE doctor_id = ? AND date = ? AND status != "cancelled"', (doctor_id, date))
            booked_slots = [row['time'] for row in cursor.fetchall()]
            
            all_slots = ["09:00", "10:00", "11:00", "14:00", "15:00", "16:00"]
            available = [slot for slot in all_slots if slot not in booked_slots]
            return available

    def book_appointment(self, appointment_id: str, patient_id: str, doctor_id: str, date: str, time: str):
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO appointments (id, patient_id, doctor_id, date, time, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (appointment_id, patient_id, doctor_id, date, time, "booked"))
                conn.commit()
                return True, "Successfully booked"
        except sqlite3.IntegrityError:
            # Conflict detected by UNIQUE constraint
            return False, "Conflict: Slot already booked or invalid."

    def cancel_appointment(self, appointment_id: str):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE appointments SET status = "cancelled" WHERE id = ?', (appointment_id,))
            conn.commit()
            return True

db = DatabaseDAL()
