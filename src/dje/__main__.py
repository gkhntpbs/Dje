from .bot import main
from .logging_config import setup_logging

if __name__ == "__main__":
    setup_logging()
    main()
