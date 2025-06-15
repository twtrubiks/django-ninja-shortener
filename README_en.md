# Django Ninja Shortener - A Bitly-like URL Shortener Service

A modern URL shortener service built with Django, Django Ninja, and Tailwind CSS, inspired by Bitly.

Users can register and log in to shorten URLs and track the click count for each short link.

This project was completed with assistance from [Cline](https://github.com/twtrubiks/mcp-vscode-cline?tab=readme-ov-file#cline). For reference, see [.clinerules/01\_doc.md](https://www.google.com/search?q=.clinerules/01_doc.md).

## Screenshots

URL Shortener Page (Usable without registration)

Track clicks after registration

## ✨ Key Features

  * **User Authentication**: Supports user registration, login, and logout.
  * **Create Short URLs**: Logged-in users can generate a unique short URL for a long URL.
  * **Short URL Redirection**: Clicking a short URL redirects the user to the original long URL.
  * **Click Tracking**: The system automatically counts the number of clicks for each short URL.
  * **Personal Dashboard**: Users can view all the short URLs they have created and their click statistics.
  * **RESTful API**: Provides API endpoints to create short URLs programmatically.
  * **Docker Support**: Includes a Dockerfile and Docker Compose setup to simplify development and deployment.

## 🛠️ Tech Stack

  * **Backend Framework**: [Django](https://github.com/twtrubiks/django-tutorial)
  * **API Framework**: [Django Ninja](https://github.com/twtrubiks/django_ninja_tutorial)
  * **Frontend Styling**: [Tailwind CSS](https://tailwindcss.com/) (integrated via `django-tailwind`)
  * **Database**:
      * Development: SQLite (default)
      * Production: Easily switchable to PostgreSQL (configuration provided in `settings.py`)
  * **Short Code Generation**: Uses `shortuuid`
  * **Testing**: [Pytest](https://github.com/twtrubiks/django_pytest_tutorial)
  * **Containerization**: [Docker](https://github.com/twtrubiks/docker-tutorial)

## 🚀 Quick Start (Using Docker, Recommended)

This is the recommended way to get started, as it ensures a consistent development environment.

**Setup Steps:**

1.  **Start the services:**
    Use Docker Compose to start all services with a single command.

    ```bash
    docker compose up --build
    ```

    This command will build the Docker image, install dependencies, run database migrations, and start the development server.

2.  **Create a superuser (Optional):**
    To access the Django Admin, run the following command in a separate terminal:

    ```bash
    docker compose exec django-ninja python manage.py createsuperuser
    ```

3.  **Access the application:**

      * **Website Homepage**: [http://localhost:8000](https://www.google.com/search?q=http://localhost:8000)
      * **API Documentation (Swagger UI)**: [http://localhost:8000/api/docs](https://www.google.com/search?q=http://localhost:8000/api/docs)

## 🔧 Local Development (Without Docker)

If you prefer to set up the environment directly on your local machine.

**Prerequisites:**

  * Python 3.12
  * Node.js and npm (for Tailwind CSS)

**Setup Steps:**

1.  **Create and activate a virtual environment:**

    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```

2.  **Install Python dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

3.  **Install and configure Tailwind CSS:**
    `django-tailwind` handles most of the setup.

    ```bash
    python manage.py tailwind install
    ```

    For more details, see [https://django-tailwind.readthedocs.io/en/latest/installation.html](https://django-tailwind.readthedocs.io/en/latest/installation.html)

4.  **Run database migrations:**

    ```bash
    python manage.py migrate
    ```

5.  **Create a superuser (Optional):**

    ```bash
    python manage.py createsuperuser
    ```

6.  **Start the development servers:**
    You need to start both the Django server and the Tailwind CSS compiler.

    In one terminal:

    ```bash
    python manage.py runserver
    ```

    In another terminal:

    ```bash
    python manage.py tailwind start
    ```

7.  **Access the application:**

      * **Website Homepage**: [http://localhost:8000](https://www.google.com/search?q=http://localhost:8000)
      * **API Documentation (Swagger UI)**: [http://localhost:8000/api/docs](https://www.google.com/search?q=http://localhost:8000/api/docs)

## 🧪 Running Tests

This project uses `pytest` for testing and measures test coverage.

The testing plan can be found in [TESTING\_PLAN.md](https://www.google.com/search?q=TESTING_PLAN.md).

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

## 📄 API Endpoints

The API provides a programmatic way to interact with the URL shortener service. All API endpoints are under the `/api/` path.

For the best experience, please visit the **API Documentation (Swagger UI)** at [http://localhost:8000/api/docs](https://www.google.com/search?q=http://localhost:8000/api/docs).

This project uses [Ninja JWT](https://github.com/twtrubiks/django_ninja_tutorial/tree/main?tab=readme-ov-file#ninja-jwt). First, call `/api/token/pair` with your username and password to get your token.

Then, paste the token into the top right corner to authorize your API calls.

## 📂 Project Structure

```plaintext
ninja_shortener/
├── Dockerfile
├── docker-compose.yml
├── manage.py
├── requirements.txt
├── ninja_shortener/      # Django project configuration
│   ├── settings.py
│   └── urls.py
├── shortener/            # Core shortener application
│   ├── models.py         # Database models (Link)
│   ├── api.py            # Django Ninja API endpoints
│   ├── views.py          # Page views and redirection logic
│   └── utils.py          # Short code generation utility
└── theme/                # Django theme and templates
    ├── templates/        # HTML templates
    └── static_src/       # Tailwind CSS source files
```

## 💡 Future Roadmap

  * **Switch to PostgreSQL**: Prepare a more robust database for production. (Completed)
  * **Detailed Analytics Dashboard**: Provide more click data, such as time, source, geolocation, etc.
  * **Custom Short URLs**: Allow users to customize the short code for their URLs.
  * **QR Code Generation**: Generate a QR code for each short URL.
  * **Asynchronous Tasks**: Use Celery to handle time-consuming tasks like data analysis.

## Donation

All articles are original creations resulting from my own research and internalizing the concepts. If you find them helpful and wish to encourage me, you are welcome to buy me a coffee :laughing:

ECPay (No membership required)
[Sponsor Link](http://bit.ly/2F7Jrha)

O'Pay (Membership required)
[Sponsor Link](https://payment.opay.tw/Broadcaster/Donate/9E47FDEF85ABE383A0F5FC6A218606F8)

## List of Sponsors

[List of Sponsors](https://github.com/twtrubiks/Thank-you-for-donate)

## License

[MIT license](https://www.google.com/search?q=LICENSE)