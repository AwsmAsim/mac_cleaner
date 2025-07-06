
# Mac Cleaner

**An intelligent Mac cleaner that uses AI to identify and remove unnecessary system data.**

---

## Table of Contents

- [Mac Cleaner](#mac-cleaner)
  - [Table of Contents](#table-of-contents)
  - [Features](#features)
  - [Requirements](#requirements)
  - [Installation](#installation)
  - [Usage](#usage)
  - [Configuration](#configuration)
  - [Logging](#logging)
  - [Backup](#backup)
  - [Disclaimer](#disclaimer)
  - [Contributing](#contributing)
  - [License](#license)

---

## Features

- **AI-Powered Classification**: Uses OpenAI's GPT-4o-mini to classify files as important or non-important, ensuring that critical system files are not accidentally deleted.
- **Intelligent Scanning**: Scans common system data locations for caches, logs, and temporary files.
- **Interactive Filtering**: Allows you to review the files before deletion and choose which programs and importance levels to keep or remove.
- **Safe Backup**: Moves deleted files to a backup directory instead of permanently deleting them, giving you a chance to restore them if needed.
- **Parallel Processing**: Utilizes multiple threads to speed up the file classification process.
- **Configurable**: Easily customize settings like the backup directory, minimum file size, and protected paths.

---

## Requirements

- Python 3.7+
- An OpenAI API key

---

## Installation

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/your-username/mac-cleaner.git
    cd mac-cleaner
    ```

2.  **Install the required packages:**

    ```bash
    pip install -r requirements.txt
    ```

3.  **Set up your OpenAI API key:**

    Create a `.env` file in the project directory and add your OpenAI API key:

    ```
    OPENAI_API_KEY=your-api-key
    ```

---

## Usage

1.  **Run the script in Dry Run mode (default):**

    ```bash
    python main.py
    ```

    This will scan your system and show you which files can be deleted without actually moving them.

2.  **Run the script in Cleanup mode:**

    To enable actual file operations, set `DRY_RUN` to `False` in `main.py`:

    ```python
    DRY_RUN = False
    ```

    Then, run the script again:

    ```bash
    python main.py
    ```

    The script will prompt you to confirm before moving any files to the backup directory.

---

## Configuration

You can customize the script's behavior by modifying the following variables in `main.py`:

- `OPENAI_API_KEY`: Your OpenAI API key.
- `MODEL`: The OpenAI model to use for classification (default: `gpt-4o-mini`).
- `DRY_RUN`: Set to `True` to simulate the cleanup process without moving any files.
- `BACKUP_DIR`: The directory where deleted files will be backed up.
- `MAIN_LOG_FILE`: The main log file for the script.
- `MIN_FILE_SIZE_KB`: The minimum file size to consider for cleanup.
- `MAX_FILES`: The maximum number of files to scan.
- `NUM_THREADS`: The number of threads to use for parallel processing. 
- `PROTECTED_PATHS`: A list of paths to exclude from scanning.
- `KNOWN_PROGRAMS`: A list of programs to identify for better filtering.

---

## Logging

The script generates the following log files:

- `system_data_cleanup.log`: The main log file for the entire process.
- `system_data_cleanup_thread_*.log`: Individual log files for each thread, which can be useful for debugging.

---

## Backup

All deleted files are moved to the backup directory specified in the configuration. You can review the files in this directory and restore them if needed.

---

## Disclaimer

This script is designed to be safe, but it's always a good idea to back up your system before running any cleanup tools. The author is not responsible for any data loss that may occur.
OpenAI API rate limits are lower for individuals having less than 50 USD credits I guess, so in case you fall in this creteria run in a single thread.

---

## Contributing

Contributions are welcome! Please open an issue or submit a pull request if you have any ideas for improvement.

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
