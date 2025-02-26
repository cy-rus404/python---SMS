import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import hashlib
from datetime import datetime
import re
import csv
from pathlib import Path

class SchoolManagementSystem:
    def __init__(self):
        self.conn = sqlite3.connect('school_management.db')
        self.drop_tables()  # Remove in production
        self.create_tables()
        self.logged_in_user = None
        self.initialize_admin()

    def drop_tables(self):
        cursor = self.conn.cursor()
        cursor.executescript('''
            DROP TABLE IF EXISTS timetable;
            DROP TABLE IF EXISTS attendance;
            DROP TABLE IF EXISTS enrollments;
            DROP TABLE IF EXISTS courses;
            DROP TABLE IF EXISTS students;
            DROP TABLE IF EXISTS users;
        ''')
        self.conn.commit()

    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'teacher', 'student')),
                name TEXT NOT NULL,
                email TEXT UNIQUE,
                phone TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS students (
                student_id TEXT PRIMARY KEY,
                username TEXT UNIQUE,
                grade_level INTEGER CHECK(grade_level BETWEEN 1 AND 12),
                assigned_teacher TEXT,
                FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE,
                FOREIGN KEY (assigned_teacher) REFERENCES users(username) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS courses (
                course_id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_name TEXT NOT NULL,
                teacher_username TEXT,
                credits INTEGER DEFAULT 3,
                FOREIGN KEY (teacher_username) REFERENCES users(username) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS enrollments (
                enrollment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_username TEXT,
                course_id INTEGER,
                grade REAL CHECK(grade BETWEEN 0 AND 100),
                FOREIGN KEY (student_username) REFERENCES users(username),
                FOREIGN KEY (course_id) REFERENCES courses(course_id)
            );
            CREATE TABLE IF NOT EXISTS attendance (
                attendance_id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_username TEXT,
                course_id INTEGER,
                date TEXT,
                status TEXT CHECK(status IN ('Present', 'Absent', 'Late')),
                FOREIGN KEY (student_username) REFERENCES users(username),
                FOREIGN KEY (course_id) REFERENCES courses(course_id)
            );
            CREATE TABLE IF NOT EXISTS timetable (
                timetable_id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id INTEGER,
                day TEXT CHECK(day IN ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday')),
                start_time TEXT,
                end_time TEXT,
                FOREIGN KEY (course_id) REFERENCES courses(course_id)
            );
        ''')
        self.conn.commit()

    def hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()

    def initialize_admin(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                "INSERT INTO users (username, password, role, name, email) VALUES (?, ?, ?, ?, ?)",
                ("admin", self.hash_password("admin123"), "admin", "System Administrator", "admin@school.edu")
            )
            self.conn.commit()

    def validate_email(self, email):
        return re.match(r"[^@]+@[^@]+\.[^@]+", email) is not None

    def validate_phone(self, phone):
        return re.match(r"^\+?\d{10,15}$", phone) is not None if phone else True

    def login(self, username, password):
        cursor = self.conn.cursor()
        cursor.execute("SELECT username, role, name FROM users WHERE username = ? AND password = ?",
                      (username, self.hash_password(password)))
        user = cursor.fetchone()
        if user:
            self.logged_in_user = {"username": user[0], "role": user[1], "name": user[2]}
            return True
        return False

    def add_user(self, username, password, role, name, email, phone=None, grade_level=None, assigned_teacher=None, courses=None):
        if not self.logged_in_user or self.logged_in_user["role"] != "admin":
            raise PermissionError("Admin access required")
        if not all([username, password, role, name, email]):
            raise ValueError("Missing required fields")
        if not self.validate_email(email):
            raise ValueError("Invalid email format")
        if phone and not self.validate_phone(phone):
            raise ValueError("Invalid phone format")
        
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO users (username, password, role, name, email, phone) VALUES (?, ?, ?, ?, ?, ?)",
                (username, self.hash_password(password), role, name, email, phone)
            )
            if role == "student" and grade_level:
                student_id = f"STU{username[-4:].zfill(4)}{grade_level:02d}"
                cursor.execute(
                    "INSERT INTO students (student_id, username, grade_level, assigned_teacher) VALUES (?, ?, ?, ?)",
                    (student_id, username, grade_level, assigned_teacher)
                )
                if assigned_teacher:
                    cursor.execute("SELECT course_id FROM courses WHERE teacher_username = ?", (assigned_teacher,))
                    for course in cursor.fetchall():
                        cursor.execute("INSERT INTO enrollments (student_username, course_id) VALUES (?, ?)",
                                      (username, course[0]))
            elif role == "teacher" and courses:
                for course_name in courses.split(","):
                    course_name = course_name.strip()
                    if course_name:
                        cursor.execute(
                            "INSERT INTO courses (course_name, teacher_username, credits) VALUES (?, ?, 3)",
                            (course_name, username)
                        )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError as e:
            raise ValueError(f"User creation failed: {str(e)}")

    def enroll_student(self, student_username, course_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT username FROM users WHERE username = ? AND role = 'student'", (student_username,))
        if not cursor.fetchone():
            raise ValueError("Invalid student username")
        cursor.execute("SELECT course_id FROM courses WHERE course_id = ?", (course_id,))
        if not cursor.fetchone():
            raise ValueError("Invalid course ID")
        cursor.execute(
            "INSERT INTO enrollments (student_username, course_id) VALUES (?, ?)",
            (student_username, course_id)
        )
        self.conn.commit()
        return True

    def assign_grade(self, student_username, course_id, grade):
        if not self.logged_in_user or self.logged_in_user["role"] != "teacher":
            raise PermissionError("Permission denied")
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE enrollments SET grade = ? WHERE student_username = ? AND course_id = ?",
            (grade, student_username, course_id)
        )
        self.conn.commit()
        return True

    def mark_attendance(self, student_username, course_id, status):
        if not self.logged_in_user or self.logged_in_user["role"] != "teacher":
            raise PermissionError("Permission denied")
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO attendance (student_username, course_id, date, status) VALUES (?, ?, ?, ?)",
            (student_username, course_id, datetime.now().date(), status)
        )
        self.conn.commit()
        return True

    def add_timetable(self, course_id, day, start_time, end_time):
        if not self.logged_in_user or self.logged_in_user["role"] != "admin":
            raise PermissionError("Admin access required")
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO timetable (course_id, day, start_time, end_time) VALUES (?, ?, ?, ?)",
            (course_id, day, start_time, end_time)
        )
        self.conn.commit()
        return True

    def export_report(self, student_username, filename):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM students WHERE username = ?", (student_username,))
        student = cursor.fetchone()
        if not student:
            return False
        
        cursor.execute("""
            SELECT c.course_name, e.grade, a.status, a.date, t.day, t.start_time, t.end_time
            FROM enrollments e 
            JOIN courses c ON e.course_id = c.course_id
            LEFT JOIN attendance a ON a.student_username = e.student_username AND a.course_id = e.course_id
            LEFT JOIN timetable t ON t.course_id = e.course_id
            WHERE e.student_username = ?
        """, (student_username,))
        records = cursor.fetchall()
        
        report = f"Report for {student_username} (ID: {student[0]})\nGrade Level: {student[2]}\nAssigned Teacher: {student[3] or 'None'}\n\n"
        for record in records:
            report += f"Course: {record[0]}\nGrade: {record[1] if record[1] else 'N/A'}\n"
            if record[2]:
                report += f"Attendance: {record[2]} on {record[3]}\n"
            if record[4]:
                report += f"Schedule: {record[4]} {record[5]}-{record[6]}\n"
            report += "\n"
        
        with open(filename, 'w', newline='') as f:
            f.write(report)
        return True

class SchoolGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Professional School Management System")
        self.root.geometry("1000x700")
        self.sms = SchoolManagementSystem()
        
        style = ttk.Style()
        style.configure("TButton", font=("Helvetica", 10))
        style.configure("TLabel", font=("Helvetica", 11))
        
        self.show_login()

    def clear_window(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    def show_login(self):
        self.clear_window()
        frame = ttk.Frame(self.root, padding=20, relief="raised", borderwidth=2)
        frame.place(relx=0.5, rely=0.5, anchor="center")
        
        ttk.Label(frame, text="School Management System", font=("Helvetica", 20, "bold")).grid(row=0, column=0, columnspan=2, pady=20)
        
        ttk.Label(frame, text="Username").grid(row=1, column=0, pady=10, sticky="e")
        username_entry = ttk.Entry(frame)
        username_entry.grid(row=1, column=1, pady=10)
        
        ttk.Label(frame, text="Password").grid(row=2, column=0, pady=10, sticky="e")
        password_entry = ttk.Entry(frame, show="*")
        password_entry.grid(row=2, column=1, pady=10)
        
        ttk.Button(frame, text="Login", 
                  command=lambda: self.handle_login(username_entry.get(), password_entry.get())).grid(row=3, column=0, columnspan=2, pady=20)

    def handle_login(self, username, password):
        try:
            if self.sms.login(username, password):
                role = self.sms.logged_in_user["role"]
                if role == "admin":
                    self.show_admin_dashboard()
                elif role == "teacher":
                    self.show_teacher_dashboard()
                else:
                    self.show_student_dashboard()
            else:
                messagebox.showerror("Login Failed", "Invalid credentials")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def show_admin_dashboard(self):
        self.clear_window()
        header = ttk.Frame(self.root, padding=10, relief="raised")
        header.pack(fill="x")
        ttk.Label(header, text=f"Welcome, {self.sms.logged_in_user['name']} (Admin)", 
                 font=("Helvetica", 16, "bold")).pack(side="left")
        ttk.Button(header, text="Logout", command=self.show_login).pack(side="right")

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        tabs = {
            "Users": self.create_user_tab,
            "Courses": self.create_course_tab,
            "Timetable": self.create_timetable_tab,
            "Reports": self.create_reports_tab
        }
        for name, func in tabs.items():
            frame = ttk.Frame(notebook)
            notebook.add(frame, text=name)
            func(frame)

    def create_user_tab(self, frame):
        ttk.Button(frame, text="Add New User", command=self.add_user_window).pack(pady=10)
        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        tree = ttk.Treeview(tree_frame, columns=("Username", "Name", "Role", "Email"), show="headings", height=20)
        for col in tree["columns"]:
            tree.heading(col, text=col)
            tree.column(col, width=200, anchor="center")
        tree.pack(side="left", fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        scrollbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scrollbar.set)
        
        cursor = self.sms.conn.cursor()
        cursor.execute("SELECT username, name, role, email FROM users")
        for row in cursor.fetchall():
            tree.insert("", "end", values=row)

    def create_course_tab(self, frame):
        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        tree = ttk.Treeview(tree_frame, columns=("ID", "Name", "Teacher", "Credits"), show="headings", height=20)
        for col in tree["columns"]:
            tree.heading(col, text=col)
            tree.column(col, width=200, anchor="center")
        tree.pack(side="left", fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        scrollbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scrollbar.set)
        
        cursor = self.sms.conn.cursor()
        cursor.execute("SELECT course_id, course_name, teacher_username, credits FROM courses")
        for row in cursor.fetchall():
            tree.insert("", "end", values=row)

    def create_timetable_tab(self, frame):
        ttk.Button(frame, text="Add Timetable Entry", command=self.add_timetable_window).pack(pady=10)
        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        tree = ttk.Treeview(tree_frame, columns=("Course ID", "Day", "Start", "End"), show="headings", height=20)
        for col in tree["columns"]:
            tree.heading(col, text=col)
            tree.column(col, width=200, anchor="center")
        tree.pack(side="left", fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        scrollbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scrollbar.set)
        
        cursor = self.sms.conn.cursor()
        cursor.execute("SELECT course_id, day, start_time, end_time FROM timetable")
        for row in cursor.fetchall():
            tree.insert("", "end", values=row)

    def create_reports_tab(self, frame):
        ttk.Button(frame, text="Generate Report", command=self.generate_report_window).pack(pady=10)

    def add_user_window(self):
        window = tk.Toplevel(self.root)
        window.title("Add New User")
        window.geometry("500x600")
        window.transient(self.root)
        window.grab_set()
        
        frame = ttk.Frame(window, padding=20)
        frame.pack(fill="both", expand=True)
        
        fields = [
            ("Username", ttk.Entry),
            ("Password", lambda w: ttk.Entry(w, show="*")),
            ("Role", lambda w: ttk.Combobox(w, values=["teacher", "student"], state="readonly")),
            ("Full Name", ttk.Entry),
            ("Email", ttk.Entry),
            ("Phone (optional)", ttk.Entry),
            ("Grade Level (if student)", lambda w: ttk.Spinbox(w, from_=1, to=12)),
            ("Assigned Teacher (if student)", lambda w: ttk.Combobox(w, values=self.get_teachers(), state="readonly")),
            ("Courses (if teacher, comma-separated)", ttk.Entry)
        ]
        
        entries = {}
        for i, (label, widget_type) in enumerate(fields):
            ttk.Label(frame, text=label).grid(row=i, column=0, padx=5, pady=5, sticky="e")
            widget = widget_type(frame)
            widget.grid(row=i, column=1, padx=5, pady=5, sticky="w")
            entries[label.split()[0]] = widget
        
        ttk.Button(frame, text="Add User",
                  command=lambda: self.handle_add_user(
                      {k: v.get() for k, v in entries.items()}
                  )).grid(row=len(fields), column=0, columnspan=2, pady=20)

    def get_teachers(self):
        cursor = self.sms.conn.cursor()
        cursor.execute("SELECT username FROM users WHERE role = 'teacher'")
        return [row[0] for row in cursor.fetchall()]

    def handle_add_user(self, data):
        try:
            grade = int(data["Grade"]) if data["Grade"] and data["Role"] == "student" else None
            assigned_teacher = data["Assigned"] if data["Role"] == "student" and data["Assigned"] else None
            courses = data["Courses"] if data["Role"] == "teacher" and data["Courses"] else None
            self.sms.add_user(data["Username"], data["Password"], data["Role"],
                            data["Full"], data["Email"], data["Phone"] or None, grade, assigned_teacher, courses)
            messagebox.showinfo("Success", "User added successfully")
            self.show_admin_dashboard()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def add_timetable_window(self):
        window = tk.Toplevel(self.root)
        window.title("Add Timetable Entry")
        window.geometry("400x400")
        window.transient(self.root)
        window.grab_set()
        
        frame = ttk.Frame(window, padding=20)
        frame.pack(fill="both", expand=True)
        
        fields = [
            ("Course ID", ttk.Entry),
            ("Day", lambda w: ttk.Combobox(w, values=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"], state="readonly")),
            ("Start Time (HH:MM)", ttk.Entry),
            ("End Time (HH:MM)", ttk.Entry)
        ]
        
        entries = {}
        for i, (label, widget_type) in enumerate(fields):
            ttk.Label(frame, text=label).grid(row=i, column=0, padx=5, pady=5, sticky="e")
            widget = widget_type(frame)
            widget.grid(row=i, column=1, padx=5, pady=5, sticky="w")
            entries[label.split()[0]] = widget
        
        ttk.Button(frame, text="Add Entry",
                  command=lambda: self.handle_add_timetable(
                      {k: v.get() for k, v in entries.items()}
                  )).grid(row=len(fields), column=0, columnspan=2, pady=20)

    def handle_add_timetable(self, data):
        try:
            course_id = int(data["Course"])
            self.sms.add_timetable(course_id, data["Day"], data["Start"], data["End"])
            messagebox.showinfo("Success", "Timetable entry added successfully")
            self.show_admin_dashboard()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def generate_report_window(self):
        window = tk.Toplevel(self.root)
        window.title("Generate Report")
        window.geometry("400x200")
        window.transient(self.root)
        window.grab_set()
        
        frame = ttk.Frame(window, padding=20)
        frame.pack(fill="both", expand=True)
        
        ttk.Label(frame, text="Student Username").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        username_entry = ttk.Entry(frame)
        username_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        
        ttk.Button(frame, text="Generate",
                  command=lambda: self.handle_generate_report(username_entry.get())).grid(row=1, column=0, columnspan=2, pady=20)

    def handle_generate_report(self, username):
        try:
            filename = f"report_{username}_{datetime.now().strftime('%Y%m%d')}.txt"
            if self.sms.export_report(username, filename):
                messagebox.showinfo("Success", f"Report generated as {filename}")
            else:
                messagebox.showerror("Error", "Student not found")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def show_teacher_dashboard(self):
        self.clear_window()
        header = ttk.Frame(self.root, padding=10, relief="raised")
        header.pack(fill="x")
        ttk.Label(header, text=f"Welcome, {self.sms.logged_in_user['name']} (Teacher)", 
                 font=("Helvetica", 16, "bold")).pack(side="left")
        ttk.Button(header, text="Logout", command=self.show_login).pack(side="right")
        
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        tabs = {
            "Courses": self.create_teacher_courses_tab,
            "Students": self.create_teacher_students_tab,
            "Enrollments": self.create_enrollment_tab,
            "Grades": self.create_grades_tab,
            "Attendance": self.create_attendance_tab
        }
        for name, func in tabs.items():
            frame = ttk.Frame(notebook)
            notebook.add(frame, text=name)
            func(frame)

    def create_teacher_courses_tab(self, frame):
        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        tree = ttk.Treeview(tree_frame, columns=("ID", "Name", "Credits"), show="headings", height=20)
        for col in tree["columns"]:
            tree.heading(col, text=col)
            tree.column(col, width=200, anchor="center")
        tree.pack(side="left", fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        scrollbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scrollbar.set)
        
        cursor = self.sms.conn.cursor()
        cursor.execute("SELECT course_id, course_name, credits FROM courses WHERE teacher_username = ?",
                      (self.sms.logged_in_user["username"],))
        for row in cursor.fetchall():
            tree.insert("", "end", values=row)

    def create_teacher_students_tab(self, frame):
        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        tree = ttk.Treeview(tree_frame, columns=("Student ID", "Username", "Name", "Grade Level"), show="headings", height=20)
        for col in tree["columns"]:
            tree.heading(col, text=col)
            tree.column(col, width=200, anchor="center")
        tree.pack(side="left", fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        scrollbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scrollbar.set)
        
        cursor = self.sms.conn.cursor()
        cursor.execute("""
            SELECT s.student_id, s.username, u.name, s.grade_level 
            FROM students s 
            JOIN users u ON s.username = u.username 
            WHERE s.assigned_teacher = ?
        """, (self.sms.logged_in_user["username"],))
        for row in cursor.fetchall():
            tree.insert("", "end", values=row)

    def create_enrollment_tab(self, frame):
        ttk.Button(frame, text="Enroll Student", command=self.enroll_student_window).pack(pady=10)
        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        tree = ttk.Treeview(tree_frame, columns=("Student", "Course ID", "Course Name"), show="headings", height=20)
        for col in tree["columns"]:
            tree.heading(col, text=col)
            tree.column(col, width=200, anchor="center")
        tree.pack(side="left", fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        scrollbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scrollbar.set)
        
        cursor = self.sms.conn.cursor()
        cursor.execute("""
            SELECT e.student_username, e.course_id, c.course_name 
            FROM enrollments e 
            JOIN courses c ON e.course_id = c.course_id 
            WHERE c.teacher_username = ?
        """, (self.sms.logged_in_user["username"],))
        for row in cursor.fetchall():
            tree.insert("", "end", values=row)

    def create_grades_tab(self, frame):
        ttk.Button(frame, text="Assign Grade", command=self.assign_grade_window).pack(pady=10)
        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        tree = ttk.Treeview(tree_frame, columns=("Student", "Course ID", "Course Name", "Grade"), show="headings", height=20)
        for col in tree["columns"]:
            tree.heading(col, text=col)
            tree.column(col, width=200, anchor="center")
        tree.pack(side="left", fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        scrollbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scrollbar.set)
        
        cursor = self.sms.conn.cursor()
        cursor.execute("""
            SELECT e.student_username, e.course_id, c.course_name, e.grade 
            FROM enrollments e 
            JOIN courses c ON e.course_id = c.course_id 
            WHERE c.teacher_username = ?
        """, (self.sms.logged_in_user["username"],))
        for row in cursor.fetchall():
            tree.insert("", "end", values=row)

    def create_attendance_tab(self, frame):
        ttk.Button(frame, text="Mark Attendance", command=self.mark_attendance_window).pack(pady=10)
        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        tree = ttk.Treeview(tree_frame, columns=("Student", "Course ID", "Date", "Status"), show="headings", height=20)
        for col in tree["columns"]:
            tree.heading(col, text=col)
            tree.column(col, width=200, anchor="center")
        tree.pack(side="left", fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        scrollbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scrollbar.set)
        
        cursor = self.sms.conn.cursor()
        cursor.execute("""
            SELECT a.student_username, a.course_id, a.date, a.status 
            FROM attendance a 
            JOIN courses c ON a.course_id = c.course_id 
            WHERE c.teacher_username = ?
        """, (self.sms.logged_in_user["username"],))
        for row in cursor.fetchall():
            tree.insert("", "end", values=row)

    def enroll_student_window(self):
        window = tk.Toplevel(self.root)
        window.title("Enroll Student")
        window.geometry("400x200")
        window.transient(self.root)
        window.grab_set()
        
        frame = ttk.Frame(window, padding=20)
        frame.pack(fill="both", expand=True)
        
        ttk.Label(frame, text="Student Username").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        student_entry = ttk.Entry(frame)
        student_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        
        ttk.Label(frame, text="Course ID").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        course_entry = ttk.Entry(frame)
        course_entry.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        
        ttk.Button(frame, text="Enroll",
                  command=lambda: self.handle_enroll_student(student_entry.get(), course_entry.get())).grid(row=2, column=0, columnspan=2, pady=20)

    def handle_enroll_student(self, student_username, course_id):
        try:
            course_id = int(course_id)
            self.sms.enroll_student(student_username, course_id)
            messagebox.showinfo("Success", "Student enrolled successfully")
            self.show_teacher_dashboard()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def assign_grade_window(self):
        window = tk.Toplevel(self.root)
        window.title("Assign Grade")
        window.geometry("400x300")
        window.transient(self.root)
        window.grab_set()
        
        frame = ttk.Frame(window, padding=20)
        frame.pack(fill="both", expand=True)
        
        ttk.Label(frame, text="Student Username").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        student_entry = ttk.Entry(frame)
        student_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        
        ttk.Label(frame, text="Course ID").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        course_entry = ttk.Entry(frame)
        course_entry.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        
        ttk.Label(frame, text="Grade (0-100)").grid(row=2, column=0, padx=5, pady=5, sticky="e")
        grade_entry = ttk.Spinbox(frame, from_=0, to=100)
        grade_entry.grid(row=2, column=1, padx=5, pady=5, sticky="w")
        
        ttk.Button(frame, text="Assign",
                  command=lambda: self.handle_assign_grade(student_entry.get(), course_entry.get(), grade_entry.get())).grid(row=3, column=0, columnspan=2, pady=20)

    def handle_assign_grade(self, student_username, course_id, grade):
        try:
            course_id = int(course_id)
            grade = float(grade)
            self.sms.assign_grade(student_username, course_id, grade)
            messagebox.showinfo("Success", "Grade assigned successfully")
            self.show_teacher_dashboard()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def mark_attendance_window(self):
        window = tk.Toplevel(self.root)
        window.title("Mark Attendance")
        window.geometry("400x300")
        window.transient(self.root)
        window.grab_set()
        
        frame = ttk.Frame(window, padding=20)
        frame.pack(fill="both", expand=True)
        
        ttk.Label(frame, text="Student Username").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        student_entry = ttk.Entry(frame)
        student_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        
        ttk.Label(frame, text="Course ID").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        course_entry = ttk.Entry(frame)
        course_entry.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        
        ttk.Label(frame, text="Status").grid(row=2, column=0, padx=5, pady=5, sticky="e")
        status_entry = ttk.Combobox(frame, values=["Present", "Absent", "Late"], state="readonly")
        status_entry.grid(row=2, column=1, padx=5, pady=5, sticky="w")
        
        ttk.Button(frame, text="Mark",
                  command=lambda: self.handle_mark_attendance(student_entry.get(), course_entry.get(), status_entry.get())).grid(row=3, column=0, columnspan=2, pady=20)

    def handle_mark_attendance(self, student_username, course_id, status):
        try:
            course_id = int(course_id)
            self.sms.mark_attendance(student_username, course_id, status)
            messagebox.showinfo("Success", "Attendance marked successfully")
            self.show_teacher_dashboard()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def show_student_dashboard(self):
        self.clear_window()
        header = ttk.Frame(self.root, padding=10, relief="raised")
        header.pack(fill="x")
        ttk.Label(header, text=f"Welcome, {self.sms.logged_in_user['name']} (Student)", 
                 font=("Helvetica", 16, "bold")).pack(side="left")
        ttk.Button(header, text="Logout", command=self.show_login).pack(side="right")
        
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        tabs = {
            "Courses": self.create_student_courses_tab,
            "Grades": self.create_student_grades_tab,
            "Attendance": self.create_student_attendance_tab,
            "Timetable": self.create_student_timetable_tab
        }
        for name, func in tabs.items():
            frame = ttk.Frame(notebook)
            notebook.add(frame, text=name)
            func(frame)
        
        ttk.Button(self.root, text="Export My Report",
                  command=lambda: self.handle_generate_report(self.sms.logged_in_user["username"])).pack(pady=10)

    def create_student_courses_tab(self, frame):
        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        tree = ttk.Treeview(tree_frame, columns=("ID", "Name", "Teacher", "Credits"), show="headings", height=20)
        for col in tree["columns"]:
            tree.heading(col, text=col)
            tree.column(col, width=200, anchor="center")
        tree.pack(side="left", fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        scrollbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scrollbar.set)
        
        cursor = self.sms.conn.cursor()
        cursor.execute("""
            SELECT c.course_id, c.course_name, c.teacher_username, c.credits 
            FROM enrollments e 
            JOIN courses c ON e.course_id = c.course_id 
            WHERE e.student_username = ?
        """, (self.sms.logged_in_user["username"],))
        for row in cursor.fetchall():
            tree.insert("", "end", values=row)

    def create_student_grades_tab(self, frame):
        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        tree = ttk.Treeview(tree_frame, columns=("Course ID", "Course Name", "Grade"), show="headings", height=20)
        for col in tree["columns"]:
            tree.heading(col, text=col)
            tree.column(col, width=200, anchor="center")
        tree.pack(side="left", fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        scrollbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scrollbar.set)
        
        cursor = self.sms.conn.cursor()
        cursor.execute("""
            SELECT e.course_id, c.course_name, e.grade 
            FROM enrollments e 
            JOIN courses c ON e.course_id = c.course_id 
            WHERE e.student_username = ?
        """, (self.sms.logged_in_user["username"],))
        for row in cursor.fetchall():
            tree.insert("", "end", values=row)

    def create_student_attendance_tab(self, frame):
        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        tree = ttk.Treeview(tree_frame, columns=("Course ID", "Course Name", "Date", "Status"), show="headings", height=20)
        for col in tree["columns"]:
            tree.heading(col, text=col)
            tree.column(col, width=200, anchor="center")
        tree.pack(side="left", fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        scrollbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scrollbar.set)
        
        cursor = self.sms.conn.cursor()
        cursor.execute("""
            SELECT a.course_id, c.course_name, a.date, a.status 
            FROM attendance a 
            JOIN courses c ON a.course_id = c.course_id 
            WHERE a.student_username = ?
        """, (self.sms.logged_in_user["username"],))
        for row in cursor.fetchall():
            tree.insert("", "end", values=row)

    def create_student_timetable_tab(self, frame):
        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        tree = ttk.Treeview(tree_frame, columns=("Course ID", "Course Name", "Day", "Time"), show="headings", height=20)
        for col in tree["columns"]:
            tree.heading(col, text=col)
            tree.column(col, width=200, anchor="center")
        tree.pack(side="left", fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        scrollbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scrollbar.set)
        
        cursor = self.sms.conn.cursor()
        cursor.execute("""
            SELECT t.course_id, c.course_name, t.day, t.start_time || '-' || t.end_time 
            FROM timetable t 
            JOIN courses c ON t.course_id = c.course_id 
            JOIN enrollments e ON e.course_id = t.course_id 
            WHERE e.student_username = ?
        """, (self.sms.logged_in_user["username"],))
        for row in cursor.fetchall():
            tree.insert("", "end", values=row)

if __name__ == "__main__":
    root = tk.Tk()
    app = SchoolGUI(root)
    root.mainloop()

### Key Changes:

