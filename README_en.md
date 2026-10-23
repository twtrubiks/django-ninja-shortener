# Django Ninja Shortener - A Bitly-like URL Shortener Service

[中文版](README.md)

[![Python](https://img.shields.io/badge/Python-3.13+-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-6.0-092E20.svg)](https://www.djangoproject.com/)
[![Django Ninja](https://img.shields.io/badge/Django%20Ninja-1.6-green.svg)](https://django-ninja.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-18-blue.svg)](https://www.postgresql.org/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind%20CSS-4-38BDF8.svg)](https://tailwindcss.com/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)](https://www.docker.com/)
[![JWT](https://img.shields.io/badge/Auth-JWT-orange.svg)](https://github.com/eadwinCode/django-ninja-jwt)
[![Sqids](https://img.shields.io/badge/Sqids-short%20codes-blueviolet.svg)](https://sqids.org/)
[![Django-Q2](https://img.shields.io/badge/Django--Q2-async%20tasks-44B78B.svg)](https://django-q2.readthedocs.io/)
[![gunicorn](https://img.shields.io/badge/gunicorn-WSGI-499848.svg)](https://gunicorn.org/)
[![Caddy](https://img.shields.io/badge/Caddy-auto%20HTTPS-1F88C0.svg)](https://caddyserver.com/)

A modern URL shortener service built with Django, Django Ninja, and Tailwind CSS, inspired by Bitly.

Users can register and log in to shorten URLs and track the click count for each short link.

~~This project was completed with assistance from [Cline](https://github.com/twtrubiks/mcp-vscode-cline?tab=readme-ov-file#cline). For reference, see [.clinerules/01_doc.md](.clinerules/01_doc.md)~~ Currently developed with [Claude Code](https://docs.anthropic.com/en/docs/claude-code)

## Screenshots

URL Shortener Page (Usable without registration)

![alt tag](https://cdn.imgpile.com/f/g7TBHCO_md.png)

With registration, you get more features like click tracking, expiration dates, custom URLs, and QR codes

![alt tag](https://cdn.imgpile.com/f/KFN4HFX_xl.png)

![alt tag](https://cdn.imgpile.com/f/igyvV2b_xl.png)

Click Analytics Dashboard (daily click trend over the last 30 days, top referrers, device breakdown)

![alt tag](https://cdn.imgpile.com/f/hJcKXKc_xl.png)

Chrome Extension

![alt tag](https://cdn.imgpile.com/f/XVTnqjC_xl.png)

## ✨ Key Features

* **User Authentication**: Supports user registration, login, and logout, using JWT for API authentication.
* **Create Short URLs**: Anonymous users can create short URLs, logged-in users enjoy more features.
* **Custom Short URL Slug**: Logged-in users can customize the URL suffix (3-50 characters), with format validation and reserved word filtering.
* **Short URL Expiration**: Set expiration time for short URLs (1 hour, 1 day, 7 days, 30 days, or permanent).
* **Short URL Redirection**: Clicking a short URL redirects the user to the original long URL, using atomic updates to prevent race conditions.
* **Click Tracking**: The system automatically counts the number of clicks for each short URL.
* **Click Analytics**: Each link has a dedicated stats page with a daily click line chart over the last 30 days (day boundaries in the Taipei timezone), top referrer domains, and a device breakdown (bots are categorized separately and excluded from the chart). Privacy-friendly design: **no IP addresses or raw User-Agent strings are stored**, referrers keep only the domain; events are retained for 90 days and cleaned up daily by a Django-Q schedule, while the all-time total click count is still kept in `click_count`.
* **Open Graph Preview**: Fetches OG data (title, description, image) from target pages **asynchronously** via a Django-Q background worker, so creating a short URL is never blocked by a slow target site; the dashboard shows a skeleton loader and auto-polls for updates, with manual re-fetch support.
* **QR Code Generation**: Generate QR codes for each short URL, supporting multiple sizes (128/256/512px) and custom colors.
* **Personal Dashboard**: Paginated display of all user's short URLs and statistics, with link deletion support.
* **Link Limit**: Each logged-in user can create up to 1000 links.
* **RESTful API**: Complete API endpoints with JWT or long-lived API Key authentication.
* **API Key (Personal Access Token)**: Long-lived keys are ideal for programmatic integration and browser extensions (no JWT expiry/refresh); the database stores only a SHA-256 hash, and the plaintext is shown only once at creation. Create and revoke them on the web "API Keys" page (up to 10 per user).
* **Chrome Browser Extension**: Manifest V3, one-click shorten the current tab and auto-copy to clipboard, with custom slug support and a recent links list. See the "Chrome Extension" section below.
* **Security Protection**: SSRF protection (resolves the actual IP and performs object-level checks via `ipaddress`, covering decimal / hex / octal / IPv6-mapped encoding bypasses, blocking every non-public address (including cloud metadata inside CGNAT `100.64.0.0/10`), and re-validates every redirect target; DNS rebinding is a known limitation), OG fetch response size limit (streamed read that caps decompressed bytes to guard against decompression bombs / oversized bodies exhausting the background worker), URL protocol and format validation, CSRF protection, TOCTOU race condition prevention, production HTTPS hardening (HSTS, HTTPS redirect, and `Secure` cookies auto-enabled when `DEBUG=False`), API rate limiting (throttling to prevent abuse / DoS).
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
* **Click Charts**: Uses [Chart.js](https://www.chartjs.org/) to render the daily click line chart (bundled locally with the project, no CDN dependency)
* **UA Parsing**: Uses [ua-parser](https://github.com/ua-parser/uap-python) to parse device / browser / OS and detect bots
* **Testing**: [Pytest](https://github.com/twtrubiks/django_pytest_tutorial) (445 test cases, 99% coverage, 93.3% mutation score — see [MUTATION_TESTING.md](MUTATION_TESTING.md), in Chinese)
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
| `DJANGO_SECURE_SSL_REDIRECT` | (when `DEBUG=False`) Redirect HTTP to HTTPS | `True` |
| `DJANGO_SECURE_HSTS_SECONDS` | (when `DEBUG=False`) HSTS max-age in seconds | `31536000` |
| `DJANGO_TRUST_PROXY_SSL_HEADER` | (when `DEBUG=False`) Trust reverse-proxy `X-Forwarded-Proto` to detect HTTPS | `False` |
| `DJANGO_ANON_THROTTLE_RATE` | Rate limit for public API endpoints (per IP, format "count/period") | `30/min` |
| `DJANGO_USER_THROTTLE_RATE` | Rate limit for authenticated API endpoints (per user) | `60/min` |
| `DJANGO_SHORTEN_THROTTLE_RATE` | Rate limit for creating short URLs via the web form (per account when logged in, per IP when anonymous) | `10/min` |
| `SITE_ADDRESS` | (`docker-compose.prod.yml`) Caddy's public address; set a domain to enable automatic HTTPS | `:80` |
| `WEB_CONCURRENCY` | (`docker-compose.prod.yml`) Number of gunicorn workers | `3` |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | Database name / user / password | `postgres` / `myuser` / `password123` |
| `POSTGRES_HOST` / `POSTGRES_PORT` | Database host / port | `django-postgres` / `5432` |

**Before going to production, be sure to:**

* Replace `DJANGO_SECRET_KEY` with a long random string (generate one with `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`). This key also signs JWTs — leaking it is equivalent to being able to forge any user's token.
* Set `DJANGO_DEBUG=False`. As a safeguard, the app refuses to start when `DEBUG=False` while the built-in default key is still in use.
* Set `DJANGO_ALLOWED_HOSTS` to your real domains (e.g. `example.com,www.example.com`).
* Use a strong database password, and never commit your actual `.env` (it is already ignored by `.gitignore`; only `.env.example` is tracked).
* **HTTPS sites**: keeping `DJANGO_DEBUG=False` automatically enables HSTS, `SECURE_SSL_REDIRECT`, and `Secure` cookies for sessions / CSRF. If TLS is terminated by nginx / Cloudflare, adjust `DJANGO_SECURE_SSL_REDIRECT` and `DJANGO_TRUST_PROXY_SSL_HEADER` accordingly. Verify with `python manage.py check --deploy`.

## 🚢 Production Deployment (gunicorn + Caddy)

The development `docker compose up` uses `runserver` (with hot reload) — convenient for development but **not suitable for production**. For real deployments use `docker-compose.prod.yml`, which boots a production-grade stack:

* **gunicorn** (WSGI) instead of `runserver`.
* **Caddy** as the front layer: automatic HTTPS (Let's Encrypt), reverse proxy to gunicorn, and serving static files directly.
* `migrate` / `createcachetable` / `collectstatic` run once in a dedicated **one-shot `migrate` service**; web / qcluster start only after it finishes (`depends_on: service_completed_successfully`), structurally preventing the concurrent-`migrate` race of multiple containers each migrating on boot.
* Static files use `ManifestStaticFilesStorage` for content-hashed filenames (cache busting), served by Caddy with long-lived caching.
* Tailwind CSS is pre-built during the image build, so the production image ships with its static assets.

Steps:

```bash
cp .env.example .env
# Edit .env and be sure to set (do not reuse the dev defaults):
#   DJANGO_SECRET_KEY=<long random string>
#   DJANGO_DEBUG=False
#   DJANGO_ALLOWED_HOSTS=example.com,www.example.com
#   SITE_ADDRESS=example.com        # Caddy auto-obtains/renews TLS (needs 80/443 exposed, DNS pointing here)
#   POSTGRES_PASSWORD=<strong password>

docker compose -p ninja-prod -f docker-compose.prod.yml up -d --build
```

* **`-p ninja-prod` is the project name** (`--project-name`), used as a prefix for containers / networks / volumes (e.g. `ninja-prod_db-data`). Without `-p`, the project name defaults to the **directory name**, which shares the same `db-data` volume as the development `docker compose up` and causes cross-contamination (e.g. the Postgres password is fixed by whichever stack starts first, making the other fail authentication). `-p ninja-prod` keeps the production and development volumes **fully separate**.
  * ⚠️ Once you use `-p ninja-prod`, **every subsequent prod command must include it** (`down` / `logs` / `ps` / `exec` …), otherwise you'll act on a different project.
* **Local smoke test** (no certificate): keep `SITE_ADDRESS=:80` and use plain HTTP at `http://localhost`.
* `WEB_CONCURRENCY` tunes the number of gunicorn workers (recommended `2 * CPU + 1`).
* Since TLS is terminated at Caddy and proxied over HTTP, production defaults to `DJANGO_SECURE_SSL_REDIRECT=False` (http→https redirect handled by Caddy to avoid loops) and `DJANGO_TRUST_PROXY_SSL_HEADER=True` (trust Caddy's `X-Forwarded-Proto`).
* Verify with `docker compose -p ninja-prod -f docker-compose.prod.yml exec web python manage.py check --deploy`.
* To use a different front layer (e.g. nginx), or to have Django serve static files itself (no front layer), you can serve `/static/` via WhiteNoise instead.

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

* **Mutation testing (checks that the tests actually catch bugs):**

    ```bash
    pip install mutmut==3.8.0
    python scripts/mutation/mutation_test.py run --workers 4
    ```

    See [MUTATION_TESTING.md](MUTATION_TESTING.md) for results and analysis (in Chinese), and [scripts/mutation/README.md](scripts/mutation/README.md) for the tool.

![alt tag](https://cdn.imgpile.com/f/UZnApNQ_xl.png)

## 📄 API Endpoints

The API provides a programmatic way to interact with the URL shortener service. All API endpoints are under the `/api/` path.

> All API endpoints are rate-limited (throttled): the public QR endpoint is throttled per source IP, authenticated endpoints per user, and exceeding the limit returns `429 Too Many Requests`. Rates are configurable via `DJANGO_ANON_THROTTLE_RATE` / `DJANGO_USER_THROTTLE_RATE`.

For the best experience, please visit the **API Documentation (Swagger UI)** at [http://localhost:8000/api/docs](http://localhost:8000/api/docs).

![alt tag](https://cdn.imgpile.com/f/Foa4p5C_md.png)

For programmatic integration (scripts, extensions), prefer a long-lived API Key: after logging in, create a key on the "API Keys" page in the navbar, then call with `Authorization: Bearer sk_...` — no need to handle JWT expiry/refresh.

This project uses [Ninja JWT](https://github.com/twtrubiks/django_ninja_tutorial/tree/main?tab=readme-ov-file#ninja-jwt). First, call `/api/token/pair` with your username and password to get your token.

![alt tag](https://cdn.imgpile.com/f/84ABFA4_xl.png)

Then, paste the token into the top right corner to authorize your API calls.

![alt tag](https://cdn.imgpile.com/f/aCbUddW_md.png)

## 🧩 Chrome Extension

The `extension/` directory provides a Chrome extension (Manifest V3, popup-only MVP):

* One-click shorten the "current tab" URL, with the result auto-copied to the clipboard
* Enter any URL to generate a short link (including a custom slug)
* Show the 5 most recent links with click counts, one-click copy, and mark expired links
* Authentication uses a long-lived API Key: after logging in, create a key on the "API Keys" page, then paste it once into the extension's settings page

For installation (load the unpacked extension via developer mode at `chrome://extensions/`) and technical notes, see [extension/README.md](extension/README.md).

## 📂 Project Structure

```cmd
django-ninja-shortener/
├── Dockerfile
├── docker-compose.yml        # Development (runserver + hot reload)
├── docker-compose.prod.yml   # Production (gunicorn + Caddy)
├── Caddyfile                 # Caddy front layer (auto HTTPS / reverse proxy / static)
├── entrypoint.sh             # Only exec "$@"; migrate/collectstatic handled by the one-shot migrate service
├── manage.py
├── requirements.txt
├── pytest.ini                # Pytest configuration
├── extension/                # Chrome extension (Manifest V3, see extension/README.md)
├── ninja_shortener/          # Django project configuration
│   ├── settings.py           # Django settings (JWT, database, app registration)
│   ├── urls.py               # URL routing configuration
│   └── api.py                # API integration point (NinjaExtraAPI)
├── shortener/                # Core shortener application
│   ├── models.py             # Database models (Link, LinkPreview, ApiKey, ClickEvent)
│   ├── api.py                # Django Ninja API endpoints
│   ├── auth.py               # Long-lived API Key authentication (used alongside JWT)
│   ├── ownership.py          # Owner permission checks (shared by views and API)
│   ├── views.py              # Page views, redirection, preview-status endpoint
│   ├── services.py           # Shared business logic (link creation, OG fetch & background task)
│   ├── analytics.py          # Click event recording & stats aggregation (trend / referrers / devices)
│   ├── utils.py              # Short code generation utility (Sqids)
│   ├── validators.py         # Validators (URL, custom slug)
│   ├── og_parser.py          # Open Graph data fetching (with SSRF protection, response size cap)
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
    │   ├── stats.html        # Link stats page (click trend / referrers / device breakdown)
    │   ├── api_keys.html     # API Key management page (create / revoke long-lived keys)
    │   ├── partials/         # Shared partial templates (OG preview card)
    │   └── expired.html      # Expired link page
    ├── static_src/           # Tailwind CSS source files
    └── tests/                # UI flow tests (test_ui_flows.py)
```

## 💡 Future Roadmap

* **Switch to PostgreSQL**: Prepare a more robust database for production. ✅ Completed
* **Detailed Analytics Dashboard**: Provide more click data, such as time, source, geolocation, etc. ✅ Completed (daily trend over the last 30 days, top referrers, device breakdown; geolocation not yet implemented)
* **Custom Short URLs**: Allow users to customize the short code for their URLs. ✅ Completed
* **QR Code Generation**: Generate a QR code for each short URL. ✅ Completed
* **Asynchronous OG Fetching**: Make Open Graph data fetching asynchronous (Django-Q2, with PostgreSQL as the broker) to avoid blocking API requests. ✅ Completed
* **Rate Limiting**: Prevent abuse via django-ninja's built-in throttling — public API endpoints throttled by IP, authenticated API endpoints by user; creating short URLs via the web form is throttled separately (per account when logged in, per IP when anonymous), stopping anonymous DB flooding and background-request amplification. Counters stored in DatabaseCache by default (no extra service), with rates configurable via environment variables. ✅ Completed
* **Production Deployment**: gunicorn instead of runserver, a Caddy front layer (auto HTTPS + reverse proxy + static serving), removal of boot-time `makemigrations`, and automatic `collectstatic` when `DEBUG=False`; see `docker-compose.prod.yml`. ✅ Completed
* **Caching Layer**: Move throttling counters and popular link / OG preview data to Redis for better performance and cross-process consistency.

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
