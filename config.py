import os

class Config:
    """
    Application configuration for Figurella integration.
    """

    # Secret key for sessions
    SECRET_KEY = os.getenv('SECRET_KEY', 'Figurella2025')

    # Base URL of the Figurella platform
    FIGURELLA_BASE_URL = os.getenv(
        'FIGURELLA_BASE_URL',
        'https://newton.hosting.memetic.it'
    )

    # FullCalendar/agenda edit page
    FIGURELLA_CALENDAR_URL = os.getenv(
        'FIGURELLA_CALENDAR_URL',
        'https://newton.hosting.memetic.it/assist/agenda_edit'
    )

    # Scraping credentials (override via env)
    FIGURELLA_USERNAME = os.getenv('FIGURELLA_USERNAME', 'Tutor')
    FIGURELLA_PASSWORD = os.getenv('FIGURELLA_PASSWORD', 'FiguMass2025$')

    # OpenAI API key for GPT-4 integration (must be set in environment)
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
