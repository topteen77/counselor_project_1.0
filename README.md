# Counselor Project 
  
A Django-based e-learning platform for counselor training courses across multiple countries. The system provides structured courses with chapters, parts, and quizzes, with comprehensive progress tracking and certification features.

## Project Overview 

Project location on system-> D:\Projects\Counselor Git Project\counselor_project

This project is designed for **ten countries**, each with its own specialized course. The course structure follows a hierarchical model:
- **Countries** → **Courses** → **Chapters** → **Parts** → **Quizzes**

### Key Features

- Multi-country course support (10 countries)
- Hierarchical course structure (Courses → Chapters → Parts → Quizzes)
- Quiz-based assessment system with attempt tracking
- Progress tracking for users
- Certificate generation based on performance
- Admin panel for course management
- User authentication 

### Quiz Attempt System

The quiz system implements a sophisticated attempt tracking mechanism:

- **First Attempt**: Users can take the quiz immediately
- **Second Failure**: After 2 failed attempts, the quiz is locked for **5 minutes**
- **Third Failure**: After 3 failed attempts, users can proceed but the score **will not be counted** in the final assessment
- **Passing Score**: Minimum 60% required to pass a quiz

## Prerequisites

- Python 3.8 or higher
- MySQL database server
- pip (Python package manager)

## Setup Instructions

### 1. Clone the Repository

```bash
git clone topteen77/counselor_project
cd counselor_project
```

### 2. Create Virtual Environment

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**Linux/Mac:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Requirements

```bash
pip install -r requirement.txt
```

### 4. Database Configuration

The project uses MySQL database. You need to:

### 5. Run Migrations

```bash
python manage.py migrate
```

### 6. Create Superuser (Optional)

```bash
python manage.py createsuperuser
```

## Local Development Setup

To run the project locally, you need to rename the local configuration files:

### Step 1: Rename Settings File

**Windows:**
```bash
cd counselor_project
ren settings_local.py settings.py
```

**Linux/Mac:**
```bash
cd counselor_project
mv settings_local.py settings.py
```

**Note:** If `settings.py` already exists, you may want to backup it first or directly edit `settings.py`
### Step 2: Rename URLs File

**Windows:**
```bash
cd counselor_project
ren urls_local.py urls.py
```

**Linux/Mac:**
```bash
cd counselor_project
mv urls_local.py urls.py
```

**Note:** If `urls.py` already exists, backup it first or merge the configurations.

### Step 3: Run the Development Server

```bash
python manage.py runserver
```

The application will be available at `http://127.0.0.1:8000/`

## Admin Panel

### Access URL

- **Production**: https://test.topteen.in/counselor_project/admin/
- **Local**: http://127.0.0.1:8000/admin/

### Default Credentials

- **Username**: `admin`
- **Password**: `admin@123`



## Key Models

- **CounselorUser**: User accounts for counselors
- **CounselorCourse**: Course definitions (one per country)
- **Chapter**: Course chapters with index ordering
- **Part**: Chapter parts with content and quizzes
- **Quiz**: Quiz definitions linked to parts
- **Question**: Quiz questions
- **QuizAnswers**: Answer options for questions
- **QuizResults**: User quiz scores and results
- **CourseContentProgress**: Tracks user progress through parts
- **UserProgressTrack**: Tracks where users left off
- **UserQuizAttemptTrack**: Tracks quiz attempts and lockout periods
- **CounselorCertification**: Generated certificates with grades

## Main Features

### Course Navigation

- Users can navigate through courses, chapters, and parts
- Progress is automatically saved
- Resume functionality to continue from last position

### Quiz System

- Real-time scoring
- Attempt tracking with lockout mechanism
- Score calculation and grade assignment

### Certification

Certificates are automatically generated when:
- All course parts are completed
- Minimum passing score (60%) is achieved

Grades are assigned based on overall performance:
- **A+**: > 90%
- **A**: > 80%
- **B+**: > 70%
- **B**: > 60%
- **C**: ≤ 60%


## Dependencies

Key packages used in this project:

- Django 5.1.5
- mysqlclient 2.2.7
- django-ckeditor 6.7.2
- django-nested-admin 4.1.1
- Pillow 11.2.1
- WhiteNoise 6.8.2

See `requirement.txt` for the complete list.

## Development Notes

- The project uses session-based authentication (not Django's built-in auth)
- Quiz results are stored in JSON format
- The system tracks quiz attempts to prevent abuse
- Static files are served using WhiteNoise in production
- CKEditor is used for rich text editing in admin panel

## Troubleshooting

### Database Connection Issues

If you encounter MySQL connection errors:
1. Ensure MySQL server is running
2. Verify database credentials in settings
3. Check if the database `counselor_course` exists
4. Ensure MySQL user has proper permissions

### Migration Issues

If migrations fail:
```bash
python manage.py makemigrations
python manage.py migrate
```

### Static Files Not Loading

Collect static files:
```bash
python manage.py collectstatic
```





## Autocomplete Features

The system provides two types of autocomplete functionality for testing and development purposes:

### 1. Quiz Autocomplete (Single Quiz)

Allows automatic completion of quizzes for a specific course. This feature enables autocomplete mode for all quizzes in the course, which automatically selects the correct answers when taking quizzes.

**Access URL:**
```
http://127.0.0.1:8000/counselor_enrolled_course/<course_name>/autocomplete/
```

**Example:**
```
http://127.0.0.1:8000/counselor_enrolled_course/UK/autocomplete/
http://127.0.0.1:8000/counselor_enrolled_course/Germany/autocomplete/
```

**Features:**
- Requires master password authentication
- Activates autocomplete mode for all quizzes in the course
- Shows autocomplete buttons on quiz pages
- Automatically selects correct answers when enabled
- Session-based activation (persists for the current session)

**Usage:**
1. Navigate to the autocomplete URL for your desired course
2. Enter the master password (configured in Django settings)
3. Click "Activate Autocomplete"
4. Return to the course and take quizzes - correct answers will be automatically selected

### 2. Full Course Autocomplete

Completes the entire course automatically by:
- Marking all course parts as complete
- Completing all quizzes with 100% scores
- Marking all quizzes as passed
- Creating proper quiz result records

**Access URL:**
```
http://127.0.0.1:8000/counselor_enrolled_course/<course_name>/autocomplete-full/
```

**Example:**
```
http://127.0.0.1:8000/counselor_enrolled_course/UK/autocomplete-full/
http://127.0.0.1:8000/counselor_enrolled_course/Germany/autocomplete-full/
```

**Features:**
- Requires master password authentication
- Marks all parts as complete (`CourseContentProgress`)
- Completes all quizzes with perfect scores (100%)
- Creates quiz results in the same format as regular submissions
- Deletes quiz attempt tracking records (marks quizzes as passed)
- Generates proper quiz result data with correct/incorrect answer mappings
- Transaction-based (all-or-nothing operation)

**Usage:**
1. Navigate to the full autocomplete URL for your desired course
2. Enter the master password (configured in Django settings)
3. Click "Autocomplete Full Course"
4. The system will automatically complete all parts and quizzes
5. You'll be redirected to the course page with all content completed

**Master Password Configuration:**

The master password is configured in Django settings:
```python
MASTER_PASSWORD = 'your_master_password_here'
```

**Security Notes:**
- Both features require master password authentication
- These features are intended for testing and development
- In production, consider restricting access to admin users only
- The master password should be kept secure and not exposed in version control

**Link in Course View:**

A link to the full course autocomplete feature is available in the course header for easy access during development and testing.# counselor_project_1.0
