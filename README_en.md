# Django Ninja Shortener - A Bitly-like URL Shortener Service

[中文版](README.md)

A modern URL shortener service built with Django, Django Ninja, and Tailwind CSS, inspired by Bitly.

Users can register and log in to shorten URLs and track the click count for each short link.

~~This project was completed with assistance from [Cline](https://github.com/twtrubiks/mcp-vscode-cline?tab=readme-ov-file#cline). For reference, see [.clinerules/01_doc.md](.clinerules/01_doc.md)~~ Currently developed with [Claude Code](https://docs.anthropic.com/en/docs/claude-code)

## Screenshots

URL Shortener Page (Usable without registration)

![alt tag](https://cdn.imgpile.com/f/qPDKjsy_xl.png)

With registration, you get more features like click tracking, expiration dates, custom URLs, and QR codes

![alt tag](https://cdn.imgpile.com/f/0oOzE2J_xl.png)

![alt tag](https://cdn.imgpile.com/f/NdaNWkE_xl.png)

## ✨ Key Features

* **User Authentication**: Supports user registration, login, and logout, using JWT for API authentication.
* **Create Short URLs**: Anonymous users can create short URLs, logged-in users enjoy more features.
* **Custom Short URL Slug**: Logged-in users can customize the URL suffix (3-50 characters), with format validation and reserved word filtering.
* **Short URL Expiration**: Set expiration time for short URLs (1 hour, 1 day, 7 days, 30 days, or permanent).
* **Short URL Redirection**: Clicking a short URL redirects the user to the original long URL, using atomic updates to prevent race conditions.
* **Click Tracking**: The system automatically counts the number of clicks for each short URL.
* **Open Graph Preview**: Fetches OG data (title, description, image) from target pages **asynchronously** via a Django-Q background worker, so creating a short URL is never blocked by a slow target site; the dashboard shows a skeleton loader and auto-polls for updates, with manual re-fetch support.
* **QR Code Generation**: Generate QR codes for each short URL, supporting multiple sizes (128/256/512px) and custom colors.
* **Personal Dashboard**: Paginated display of all user's short URLs and statistics, with link deletion support.
* **Link Limit**: Each logged-in user can create up to 1000 links.
* **RESTful API**: Complete API endpoints with JWT authentication.
* **Security Protection**: SSRF protection (resolves the actual IP and performs object-level checks via `ipaddress`, covering decimal / hex / octal / IPv6-mapped encoding bypasses, and re-validates every redirect target; DNS rebinding is a known limitation), URL protocol validation, CSRF protection, TOCTOU race condition prevention.
* **Environment-based Configuration**: `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, and database credentials can all be injected via environment variables; in production (`DEBUG=False`) the app refuses to start if the built-in default key is still in use. See the "Environment Variables & Production Setup" section below.
* **Docker Support**: Includes Dockerfile and Docker Compose setup to simplify development and deployment.

## 🛠️ Tech Stack

* **Backend Framework**: [Django](https://github.com/twtrubiks/django-tutorial)
* **API Framework**: [Django Ninja](https://github.com/twtrubiks/django_ninja_tutorial)
* **Frontend Styling**: [Tailwind CSS](https://tailwindcss.com/) (integrated via `django-tailwind`)
* **Database**:
  * Default: PostgreSQL (via Docker Compose)
  * Alternative: SQLite (configuration provided in `settings.py`)
* **Short Code Generation**: Uses [Sqids](https://sqids.org/) to generate from database ID (zero collision design)
* **QR Code**: Uses [Segno](https://segno.readthedocs.io/) for QR code generation
* **OG Parsing**: Uses [metadata_parser](https://github.com/jvanasco/metadata_parser) for Open Graph data parsing
* **Async Tasks**: Uses [Django-Q2](https://django-q2.readthedocs.io/) to fetch OG data in the background (with PostgreSQL ORM as the broker, no extra Redis required)
* **Testing**: [Pytest](https://github.com/twtrubiks/django_pytest_tutorial) (118 test cases, 94% coverage)
* **Containerization**: [Docker](https://github.com/twtrubiks/docker-tutorial)

## 🚀 Quick Start (Using Docker, Recommended)

This is the recommended way to get started, as it ensures a consistent development environment.

**Setup Steps:**

1. **Start the services:**

    Use Docker Compose to start all services with a single command.

    ```bash
    docker compose up --build
    ```

    This command will build the Docker image, install dependencies, run database migrations, and start all services: the Django development server, PostgreSQL, the Tailwind compiler, and `qcluster` (the Django-Q background worker that fetches OG previews asynchronously).

2. **Create a superuser (Optional):**

    To access the Django Admin, run the following command in a separate terminal:

    ```bash
    docker compose exec django-ninja python manage.py createsuperuser
    ```

3. **Access the application:**

    * **Website Homepage**: [http://localhost:8000](http://localhost:8000)

    * **API Documentation (Swagger UI)**: [http://localhost:8000/api/docs](http://localhost:8000/api/docs)

## 🔧 Local Development (Without Docker)

If you prefer to set up the environment directly on your local machine.

**Prerequisites:**

* Python 3.13
* Node.js and npm (for Tailwind CSS)

**Setup Steps:**

1. **Create and activate a virtual environment:**

    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```

2. **Install Python dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

3. **Install and configure Tailwind CSS:**

    `django-tailwind` handles most of the setup.

    ```bash
    python manage.py tailwind install
    ```

    For more details, see [https://django-tailwind.readthedocs.io/en/latest/installation.html](https://django-tailwind.readthedocs.io/en/latest/installation.html)

4. **Run database migrations:**

    ```bash
    python manage.py migrate
    ```

5. **Create a superuser (Optional):**

    ```bash
    python manage.py createsuperuser
    ```

6. **Start the development servers:**

    You need to start both the Django server and the Tailwind CSS compiler.

    ```bash
    python manage.py runserver
    ```

    In another terminal:

    ```bash
    python manage.py tailwind start
    ```

    In a third terminal, start the Django-Q background worker (which fetches OG previews asynchronously):

    ```bash
    python manage.py qcluster
    ```

    > Without the worker running, OG previews will stay in the "pending" state.

7. **Access the application:**

    * **Website Homepage**: [http://localhost:8000](http://localhost:8000)

    * **API Documentation (Swagger UI)**: [http://localhost:8000/api/docs](http://localhost:8000/api/docs)

## 🔐 Environment Variables & Production Setup

Sensitive settings are no longer hard-coded in `settings.py`; they are injected via environment variables. A `.env.example` template is provided at the project root. **When no environment variables are set, the built-in development defaults are used**, so both Docker and local setups run out of the box (`docker compose` automatically reads the root `.env`).

```bash
cp .env.example .env   # then adjust .env for your environment
```

| Variable | Purpose | Default |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | Django secret key, also used for JWT signing | built-in insecure dev key |
| `DJANGO_DEBUG` | Enable debug mode | `True` |
| `DJANGO_ALLOWED_HOSTS` | Allowed hostnames (comma-separated) | `*` |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | Database name / user / password | `postgres` / `myuser` / `password123` |
| `POSTGRES_HOST` / `POSTGRES_PORT` | Database host / port | `django-postgres` / `5432` |

**Before going to production, be sure to:**

* Replace `DJANGO_SECRET_KEY` with a long random string (generate one with `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`). This key also signs JWTs — leaking it is equivalent to being able to forge any user's token.
* Set `DJANGO_DEBUG=False`. As a safeguard, the app refuses to start when `DEBUG=False` while the built-in default key is still in use.
* Set `DJANGO_ALLOWED_HOSTS` to your real domains (e.g. `example.com,www.example.com`).
* Use a strong database password, and never commit your actual `.env` (it is already ignored by `.gitignore`; only `.env.example` is tracked).

## 🧪 Running Tests

This project uses `pytest` for testing and measures test coverage.

The testing plan can be found in [TESTING_PLAN.md](TESTING_PLAN.md).

* **Run tests using Docker:**

    ```bash
    docker compose --profile testing up
    ```

    A test coverage report will be generated at `htmlcov/index.html`.

* **Run tests locally:**

    ```bash
    # Ensure development dependencies are installed
    pytest --cov=. --cov-report=html
    ```

![alt tag](https://cdn.imgpile.com/f/UZnApNQ_xl.png)

## 📄 API Endpoints

The API provides a programmatic way to interact with the URL shortener service. All API endpoints are under the `/api/` path.

For the best experience, please visit the **API Documentation (Swagger UI)** at [http://localhost:8000/api/docs](http://localhost:8000/api/docs).

![alt tag](https://cdn.imgpile.com/f/Foa4p5C_md.png)

This project uses [Ninja JWT](https://github.com/twtrubiks/django_ninja_tutorial/tree/main?tab=readme-ov-file#ninja-jwt). First, call `/api/token/pair` with your username and password to get your token.

![alt tag](https://cdn.imgpile.com/f/84ABFA4_xl.png)

Then, paste the token into the top right corner to authorize your API calls.

![alt tag](https://cdn.imgpile.com/f/aCbUddW_md.png)

## 📂 Project Structure

```cmd
ninja_shortener/
├── Dockerfile
├── docker-compose.yml
├── manage.py
├── requirements.txt
├── pytest.ini                # Pytest configuration
├── ninja_shortener/          # Django project configuration
│   ├── settings.py           # Django settings (JWT, database, app registration)
│   ├── urls.py               # URL routing configuration
│   └── api.py                # API integration point (NinjaExtraAPI)
├── shortener/                # Core shortener application
│   ├── models.py             # Database models (Link, LinkPreview)
│   ├── api.py                # Django Ninja API endpoints
│   ├── views.py              # Page views, redirection, preview-status endpoint
│   ├── services.py           # Shared business logic (link creation, OG fetch & background task)
│   ├── utils.py              # Short code generation utility (Sqids)
│   ├── validators.py         # Validators (URL, custom slug)
│   ├── og_parser.py          # Open Graph data fetching (with SSRF protection)
│   ├── qr_utils.py           # QR code generation utility
│   └── tests/                # Test suite
│       ├── conftest.py       # Centralized pytest fixtures
│       ├── test_api.py       # API endpoint tests
│       ├── test_models.py    # Data model tests
│       ├── test_views.py     # View tests
│       └── ...               # Other test files
└── theme/                    # Django theme and templates
    ├── templates/            # HTML templates
    │   ├── home.html         # Homepage (short URL creation)
    │   ├── dashboard.html    # Dashboard (user link management, OG preview polling)
    │   ├── partials/         # Shared partial templates (OG preview card)
    │   └── expired.html      # Expired link page
    └── static_src/           # Tailwind CSS source files
```

## 💡 Future Roadmap

* **Switch to PostgreSQL**: Prepare a more robust database for production. ✅ Completed
* **Detailed Analytics Dashboard**: Provide more click data, such as time, source, geolocation, etc.
* **Custom Short URLs**: Allow users to customize the short code for their URLs. ✅ Completed
* **QR Code Generation**: Generate a QR code for each short URL. ✅ Completed
* **Asynchronous OG Fetching**: Make Open Graph data fetching asynchronous (Django-Q2, with PostgreSQL as the broker) to avoid blocking API requests. ✅ Completed
* **Caching Layer**: Use Redis to cache popular links and OG preview data.
* **API Rate Limiting**: Implement rate limiting to prevent abuse.

## Donation

All articles are original creations resulting from my own research and internalizing the concepts. If you find them helpful and wish to encourage me, you are welcome to buy me a coffee :laughing:

ECPay (No membership required)

![alt tag](https://payment.ecpay.com.tw/Upload/QRCode/201906/QRCode_672351b8-5ab3-42dd-9c7c-c24c3e6a10a0.png)

[Sponsor Link](http://bit.ly/2F7Jrha)

O'Pay (Membership required)

![alt tag](https://i.imgur.com/LRct9xa.png)

[Sponsor Link](https://payment.opay.tw/Broadcaster/Donate/9E47FDEF85ABE383A0F5FC6A218606F8)

## List of Sponsors

[List of Sponsors](https://github.com/twtrubiks/Thank-you-for-donate)

## License

MIT license
