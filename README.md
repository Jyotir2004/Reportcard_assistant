# Report Card Assistant

An intelligent Student Report Card Management and Assistant System built with a Django REST Framework backend and a modern React (Vite) frontend.

----

## Features

- **Interactive AI Assistant**: Guided workflow to analyse student records, compare examinations, and generate performance insights.
- **Report Card Generation**: Automated calculation of totals, percentages, ranks, and letter grades.
- **PDF Export**: Download cleanly formatted PDF report cards generated using ReportLab.
- **Examination Management**: Multi-term/exam performance tracking and cross-examination comparisons.
- **Role-Based Authentication**: Secure JWT & session authentication for administrators and teachers.
- **Modern Responsive UI**: Fast React interface bundled with Vite.

---

## Tech Stack

### Backend
- **Python 3.10+ / 3.14**
- **Django 6.x** & **Django REST Framework**
- **ReportLab** (PDF generation)
- **python-dotenv**

### Frontend
- **React 19**
- **Vite 7**
- **Vanilla CSS**

---

## Project Structure

```text
student_reportcard/
├── report_card/
│   ├── manage.py
│   ├── report_card/           # Django project configuration (settings, urls, asgi, wsgi)
│   ├── student/               # Core application (models, views, APIs, assistant workflow)
│   ├── frontend/              # React + Vite frontend application
│   │   ├── src/
│   │   ├── package.json
│   │   └── vite.config.js
│   └── requirements.txt
├── .gitignore
└── README.md
```

---

## Getting Started

### 1. Prerequisites
- Python 3.10+
- Node.js (v18+) and npm
- Git

---

### 2. Backend Setup

1. Navigate to the `report_card` directory:
   ```bash
   cd report_card
   ```

2. Create and activate a virtual environment:
   ```bash
   # Windows
   python -m venv venv
   .\venv\Scripts\activate

   # macOS / Linux
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure environment variables:
   Copy `.env.example` to `.env` and fill in necessary keys:
   ```bash
   cp .env.example .env
   ```

5. Run migrations:
   ```bash
   python manage.py migrate
   ```

6. Start the development server:
   ```bash
   python manage.py runserver 127.0.0.1:8000
   ```
   Backend will be running at [http://127.0.0.1:8000](http://127.0.0.1:8000).

---

### 3. Frontend Setup

1. In a separate terminal, navigate to the frontend directory:
   ```bash
   cd report_card/frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Start the Vite development server:
   ```bash
   npm run dev
   ```
   Frontend will be running at [http://127.0.0.1:5173](http://127.0.0.1:5173).

---

## License

This project is licensed under the MIT License.
