import os
import shutil
import datetime
import json
import logging
import time
from pathlib import Path
import openai
from openai import OpenAI
import psutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import logging.handlers
import re

# Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # Replace with your key or use env variable
MODEL = "gpt-4o-mini"  # Cost-effective model
DRY_RUN = False  # Set to False to enable actual file operations
BACKUP_DIR = os.path.expanduser("~/SystemDataCleanupBackup")
MAIN_LOG_FILE = "system_data_cleanup.log"
MIN_FILE_SIZE_KB = 10  # Skip files smaller than 10 KB
MAX_FILES = 10000  # Limit to 1000 files for testing
NUM_THREADS = 4  # Number of threads for parallel processing
PROTECTED_PATHS = [
    "/Library/Caches/com.apple.",
    "/private/var/db/",
    "/private/var/protected/",
    "/private/var/folders/",
]
KNOWN_PROGRAMS = ["Android Studio", "Transporter"]  # Programs to identify

# Setup main logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(MAIN_LOG_FILE), logging.StreamHandler()]
)
main_logger = logging.getLogger()

# Thread-safe list and lock
to_delete = []
to_delete_lock = Lock()

def setup_thread_logger(thread_id):
    """Create a logger for a specific thread."""
    logger = logging.getLogger(f"Thread_{thread_id}")
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(f"system_data_cleanup_thread_{thread_id}.log")
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.handlers = [handler]
    return logger

def setup_backup_dir():
    """Create backup directory if it doesn't exist."""
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        main_logger.info(f"Backup directory created at {BACKUP_DIR}")
    except Exception as e:
        main_logger.error(f"Failed to create backup directory: {e}")
        raise

def is_protected_path(file_path):
    """Check if file path is in protected directories."""
    return any(file_path.startswith(p) for p in PROTECTED_PATHS)

def get_file_metadata(file_path):
    """Retrieve metadata for a file."""
    if is_protected_path(file_path):
        main_logger.debug(f"Skipping protected path: {file_path}")
        return None
    try:
        stat = os.stat(file_path)
        size_kb = stat.st_size / 1024  # Size in KB
        if size_kb < MIN_FILE_SIZE_KB:
            main_logger.debug(f"Skipping small file: {file_path} ({size_kb:.2f} KB)")
            return None
        return {
            "path": file_path,
            "size_mb": stat.st_size / (1024 * 1024),  # Size in MB
            "mtime": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "is_dir": os.path.isdir(file_path),
        }
    except (OSError, PermissionError) as e:
        main_logger.debug(f"Skipping {file_path}: {e}")
        return None

def scan_system_data():
    """Scan specified directories for system data files."""
    SCAN_DIRS = [
        os.path.expanduser("~/Library/Caches"),
        "/Library/Caches",
        os.path.expanduser("~/Library/Logs"),
        "/private/var/tmp",
        "/private/var/log",
    ]
    files = []
    total_items = 0
    start_time = time.time()
    
    for dir_path in SCAN_DIRS:
        if not os.path.exists(dir_path):
            main_logger.warning(f"Directory {dir_path} does not exist, skipping")
            continue
        try:
            for root, _, file_names in os.walk(dir_path):
                for name in file_names:
                    total_items += 1
                    if total_items % 1000 == 0:
                        elapsed = time.time() - start_time
                        items_per_sec = total_items / elapsed if elapsed > 0 else 1
                        eta_secs = (122625 - total_items) / items_per_sec
                        main_logger.info(f"Scanned {total_items} items, ETA: {int(eta_secs // 60)}m {int(eta_secs % 60)}s")
                    if len(files) >= MAX_FILES:
                        main_logger.info(f"Reached MAX_FILES limit ({MAX_FILES}), stopping scan")
                        return files
                    file_path = os.path.join(root, name)
                    metadata = get_file_metadata(file_path)
                    if metadata:
                        files.append(metadata)
        except Exception as e:
            main_logger.error(f"Error scanning {dir_path}: {e}")
    
    elapsed = time.time() - start_time
    main_logger.info(f"Found {len(files)} files after filtering (out of {total_items} total) in {elapsed:.2f}s")
    return files

def classify_file_with_openai(metadata, thread_id):
    """Use OpenAI API to classify file as important or non-important with importance level."""
    logger = setup_thread_logger(thread_id)
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    prompt = f"""
    You are an expert in macOS system management. Given the following file metadata, determine if the file is IMPORTANT (critical for system or app functionality) or NON-IMPORTANT (safe to delete, e.g., caches, old logs). For all files, assign an importance level: Low (e.g., caches), Medium (e.g., old configs), or High (e.g., critical system files). Provide a brief reason. Return *only* a valid JSON object.

    Metadata:
    - Path: {metadata['path']}
    - Size: {metadata['size_mb']:.2f} MB
    - Last Modified: {metadata['mtime']}
    - Is Directory: {metadata['is_dir']}

    Example JSON response:
    {{"important": false, "importance": "Low", "reason": "Browser cache, regenerates"}}
    or
    {{"important": true, "importance": "High", "reason": "Critical system file"}}

    Return a single JSON object.
    """
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "You are a macOS system data expert. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=150,
                temperature=0.5,
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            try:
                result = json.loads(content)
                if all(key in result for key in ["important", "importance", "reason"]):
                    if result["importance"] not in ["Low", "Medium", "High"]:
                        result["importance"] = "Medium"  # Default if invalid
                    logger.info(f"File: {metadata['path']}, Important: {result['important']}, Importance: {result['importance']}, Reason: {result['reason']}")
                    return metadata, result
                else:
                    logger.warning(f"Invalid JSON structure for {metadata['path']}: {content}")
                    return metadata, {"important": True, "importance": "High", "reason": "Invalid JSON structure"}
            except json.JSONDecodeError as e:
                logger.error(f"JSON parse error for {metadata['path']}: {content}, Error: {e}")
                return metadata, {"important": True, "importance": "High", "reason": f"JSON parse error: {str(e)}"}
        except openai.RateLimitError:
            logger.warning(f"Rate limit hit for {metadata['path']}, retrying in 5 seconds...")
            time.sleep(5)
        except Exception as e:
            logger.error(f"OpenAI API error for {metadata['path']}: {e}, Response: {content if 'content' in locals() else 'N/A'}")
            return metadata, {"important": True, "importance": "High", "reason": f"API error: {str(e)}"}
        time.sleep(0.1)
    logger.error(f"Failed after retries for {metadata['path']}")
    return metadata, {"important": True, "importance": "High", "reason": "Failed after retries"}

def get_program_name(file_path):
    """Extract program name from file path."""
    path_lower = file_path.lower()
    for program in KNOWN_PROGRAMS:
        if program.lower() in path_lower:
            return program
    return "Others"

def move_to_backup(file_path):
    """Move file to backup directory, preserving directory structure."""
    rel_path = os.path.relpath(file_path, os.path.expanduser("~"))
    backup_path = os.path.join(BACKUP_DIR, rel_path)
    backup_dir = os.path.dirname(backup_path)
    try:
        os.makedirs(backup_dir, exist_ok=True)
        if not DRY_RUN:
            shutil.move(file_path, backup_path)
        main_logger.info(f"Moved {file_path} to {backup_path}")
        return backup_path
    except Exception as e:
        main_logger.error(f"Failed to move {file_path}: {e}")
        return None

def display_and_filter_files(program_files):
    """Display non-important files by program and importance, allow user to select programs and importance levels to keep."""
    if not program_files:
        print("No non-important files found.")
        return []
    
    # Display summary
    print("\nNon-important files by program and importance level:")
    print("--------------------------------------------------")
    total_files = 0
    total_size = 0
    for program, files in program_files.items():
        if not files:
            continue
        low = sum(1 for f in files if f["importance"] == "Low")
        medium = sum(1 for f in files if f["importance"] == "Medium")
        high = sum(1 for f in files if f["importance"] == "High")
        size_mb = sum(f["size_mb"] for f in files)
        total_files += len(files)
        total_size += size_mb
        print(f"{program}: {len(files)} files (Low: {low}, Medium: {medium}, High: {high}), {size_mb:.2f} MB")
        for i, file in enumerate(files, 1):
            print(f"  {i}. Path: {file['path']}")
            print(f"     Size: {file['size_mb']:.2f} MB")
            print(f"     Last Modified: {file['mtime']}")
            print(f"     Importance: {file['importance']}")
            print(f"     Reason: {file['reason']}")
            print("  --------------------------------------------------")
    print(f"Total: {total_files} files, {total_size:.2f} MB")
    
    # Prompt for programs to keep
    valid_programs = [p for p in program_files if program_files[p]]
    if not valid_programs:
        return []
    print("\nAvailable programs:", ", ".join(valid_programs))
    while True:
        response = input("\nWhich programs' files to KEEP? (e.g., 'Transporter, Build', 'none', or 'all'): ").strip().lower()
        if response == "none":
            programs_to_keep = []
            break
        if response == "all":
            programs_to_keep = valid_programs
            break
        programs_to_keep = [p.strip() for p in response.split(",") if p.strip() in [vp.lower() for vp in valid_programs]]
        if programs_to_keep:
            programs_to_keep = [vp for vp in valid_programs if vp.lower() in programs_to_keep]
            break
        print(f"Please enter valid programs from {valid_programs}, 'none', or 'all'.")
    
    # Prompt for importance levels to delete for programs not kept
    to_move = []
    for program, files in program_files.items():
        if not files or program in programs_to_keep:
            continue
        print(f"\nFor {program} ({len(files)} files):")
        low = sum(1 for f in files if f["importance"] == "Low")
        medium = sum(1 for f in files if f["importance"] == "Medium")
        high = sum(1 for f in files if f["importance"] == "High")
        print(f"  Low: {low}, Medium: {medium}, High: {high}")
        while True:
            response = input("Which importance levels to DELETE? (e.g., 'Low, Medium', 'all', 'none'): ").strip().lower()
            if response == "none":
                levels_to_delete = []
                break
            if response == "all":
                levels_to_delete = ["Low", "Medium", "High"]
                break
            levels_to_delete = [l.strip().capitalize() for l in response.split(",") if l.strip().capitalize() in ["Low", "Medium", "High"]]
            if levels_to_delete:
                break
            print("Please enter 'Low', 'Medium', 'High', 'all', or 'none'.")
        for file in files:
            if file["importance"] in levels_to_delete:
                to_move.append(file)
    
    if programs_to_keep:
        print("\nPrograms you chose to keep:", ", ".join(programs_to_keep))
    if to_move:
        print("\nFiles selected for cleanup:")
        for file in to_move:
            print(f"- {file['path']} (Importance: {file['importance']})")
    
    return to_move

def cleanup_files(files):
    """Classify files, group by program, and clean up after user review."""
    global to_delete
    to_delete = []
    program_files = {program: [] for program in KNOWN_PROGRAMS + ["Others"]}
    total_size = 0
    start_time = time.time()
    
    main_logger.info(f"Starting classification with {NUM_THREADS} threads")
    with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
        future_to_file = {executor.submit(classify_file_with_openai, metadata, i % NUM_THREADS + 1): metadata 
                          for i, metadata in enumerate(files)}
        processed = 0
        for future in as_completed(future_to_file):
            metadata, classification = future.result()
            processed += 1
            if not classification["important"]:
                with to_delete_lock:
                    metadata["importance"] = classification["importance"]
                    metadata["reason"] = classification["reason"]
                    to_delete.append(metadata)
                    program = get_program_name(metadata["path"])
                    program_files[program].append(metadata)
                    total_size += metadata["size_mb"]
            
            if processed % 100 == 0:
                elapsed = time.time() - start_time
                files_per_sec = processed / elapsed if elapsed > 0 else 1
                eta_secs = (len(files) - processed) / files_per_sec
                main_logger.info(f"Processed {processed}/{len(files)} files, ETA: {int(eta_secs // 60)}m {int(eta_secs % 60)}s")
    
    elapsed = time.time() - start_time
    main_logger.info(f"Classification complete in {elapsed:.2f}s")
    
    if not to_delete:
        main_logger.info("No non-important files found to clean up")
        return
    
    to_move = display_and_filter_files(program_files)
    
    if not to_move:
        main_logger.info("No files selected for cleanup")
        return
    
    main_logger.info(f"Proceeding with {len(to_move)} files, total size: {sum(item['size_mb'] for item in to_move):.2f} MB")
    
    confirm = input(f"\nMove {len(to_move)} files ({sum(item['size_mb'] for item in to_move):.2f} MB) to backup? (y/n): ").lower()
    if confirm != "y":
        main_logger.info("Cleanup aborted by user")
        return
    
    for metadata in to_move:
        if DRY_RUN:
            main_logger.info(f"[DRY RUN] Would move {metadata['path']}")
        else:
            move_to_backup(metadata['path'])
    
    main_logger.info(f"Files moved to {BACKUP_DIR}. Review before permanent deletion.")
    if DRY_RUN:
        main_logger.info("Running in DRY_RUN mode. No files were actually moved.")

def main():
    """Main function to run the cleanup process."""
    main_logger.info("Starting system data cleanup")
    main_logger.info(f"DRY_RUN is {'enabled' if DRY_RUN else 'disabled'}")
    setup_backup_dir()
    files = scan_system_data()
    if not files:
        main_logger.info("No files found to process")
        return
    cleanup_files(files)
    main_logger.info("Cleanup complete")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        main_logger.info("Process interrupted by user")
    except Exception as e:
        main_logger.error(f"Unexpected error: {e}")