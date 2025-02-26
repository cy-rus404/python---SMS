1.	Schema Update:
	•	Removed assigned_teacher from students table, as student-teacher relationships are now managed through enrollments.
	2.	Add User Logic:
	•	Teachers: The “Courses” field still accepts comma-separated course names (e.g., “Math, Science”).
	•	Students: The “Courses” field now accepts comma-separated course IDs (e.g., “1, 2, 3”) to enroll the student in multiple courses, each potentially taught by different teachers. This replaces the single teacher assignment.
	3.	Teacher Dashboard:
	•	Students Tab: Updated to show all students enrolled in the teacher’s courses, reflecting the many-to-many relationship.
	4.	UI Adjustments:
	•	Simplified add_user_window by removing the “Assigned Teacher” field and repurposing the “Courses” field for both roles (names for teachers, IDs for students).
	•	Updated the label to clarify usage: “Courses (comma-separated, teacher: names, student: IDs)”.
	5.	Report Enhancement:
	•	Added teacher names to the report to show which teacher is associated with each course.

How to Use:

	1.	Run the code.
	2.	Log in as admin/admin123.
	3.	Add Teachers:
	•	Teacher 1: Username: teacher1, Password: pass123, Role: teacher, Name: Teacher One, Email: teacher1@school.edu, Courses: Math, Physics
	•	Teacher 2: Username: teacher2, Password: pass123, Role: teacher, Name: Teacher Two, Email: teacher2@school.edu, Courses: English, History
	•	Note the course IDs created (e.g., Math=1, Physics=2, English=3, History=4).
	4.	Add a Student:
	•	Username: student1, Password: pass123, Role: student, Name: Student One, Email: student1@school.edu, Grade Level: 10, Courses: 1, 3
	•	This enrolls student1 in Math (Teacher 1) and English (Teacher 2).
	5.	Log in as teacher1/pass123 to see students enrolled in Math and Physics.
	6.	Log in as teacher2/pass123 to see students enrolled in English and History.
	7.	Log in as student1/pass123 to see courses from both teachers.
