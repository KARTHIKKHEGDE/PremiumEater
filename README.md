# Web Scraper

A simple web scraping application built with FastAPI, BeautifulSoup, and a modern frontend.

## Features

- Scrape website content including title, description, images, and links
- Clean and responsive UI built with Tailwind CSS
- Asynchronous backend for better performance
- Error handling and loading states

## Prerequisites

- Python 3.8+
- pip (Python package manager)
- Node.js (for frontend development, optional)

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd website-for-scraping
   ```

2. Create and activate a virtual environment (recommended):
   ```bash
   python -m venv venv
   .\venv\Scripts\activate  # On Windows
   source venv/bin/activate  # On macOS/Linux
   ```

3. Install the required packages:
   ```bash
   pip install -r requirements.txt
   ```

## Running the Application

1. Start the FastAPI development server:
   ```bash
   uvicorn main:app --reload
   ```

2. Open your browser and navigate to:
   ```
   http://localhost:8000
   ```

## Project Structure

```
.
├── backend/               # Backend code
│   └── scraper.py        # Web scraping logic
├── frontend/             # Frontend code
│   ├── static/           # Static files (CSS, JS, images)
│   │   ├── css/
│   │   └── js/
│   └── templates/        # HTML templates
│       └── index.html
├── main.py               # FastAPI application
└── requirements.txt      # Python dependencies
```

## API Endpoints

- `GET /`: Main web interface
- `POST /api/scrape`: Scrape a website (expects JSON with 'url' field)

## License

MIT
