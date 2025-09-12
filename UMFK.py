import requests
import yaml
import sys
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import OrderedDict, defaultdict
from copy import deepcopy

IS_DOCKER = os.getenv("DOCKER", "false").lower() == "true"
VERSION = "beta2509121700"

# ANSI color codes
GREEN = '\033[32m'
ORANGE = '\033[33m'
BLUE = '\033[34m'
RED = '\033[31m'
RESET = '\033[0m'
BOLD = '\033[1m'

def check_for_updates():
    print(f"Checking for updates to UMFK {VERSION}...")
    
    try:
        response = requests.get(
            "https://api.github.com/repos/netplexflix/Upcoming-Movies-for-Kometa/releases/latest",
            timeout=10
        )
        response.raise_for_status()
        
        latest_release = response.json()
        latest_version = latest_release.get("tag_name", "").lstrip("v")
        
        def parse_version(version_str):
            return tuple(map(int, version_str.split('.')))
        
        current_version_tuple = parse_version(VERSION)
        latest_version_tuple = parse_version(latest_version)
        
        if latest_version and latest_version_tuple > current_version_tuple:
            print(f"{ORANGE}A newer version of UMFK is available: {latest_version}{RESET}")
            print(f"{ORANGE}Download: {latest_release.get('html_url', '')}{RESET}")
            print(f"{ORANGE}Release notes: {latest_release.get('body', 'No release notes available')}{RESET}\n")
        else:
            print(f"{GREEN}You are running the latest version of UMFK.{RESET}\n")
    except Exception as e:
        print(f"{ORANGE}Could not check for updates: {str(e)}{RESET}\n")

def load_config(file_path=None):
    """Load configuration from YAML file"""
    if file_path is None:
        file_path = Path(__file__).parent / 'config' / 'config.yml'
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return yaml.safe_load(file)
    except FileNotFoundError:
        print(f"Config file '{file_path}' not found.")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error parsing YAML config file: {e}")
        sys.exit(1)

def process_radarr_url(base_url, api_key):
    """Process and validate Radarr URL"""
    base_url = base_url.rstrip('/')
    
    if base_url.startswith('http'):
        protocol_end = base_url.find('://') + 3
        next_slash = base_url.find('/', protocol_end)
        if next_slash != -1:
            base_url = base_url[:next_slash]
    
    api_paths = [
        '/api/v3',
        '/radarr/api/v3'
    ]
    
    for path in api_paths:
        test_url = f"{base_url}{path}"
        try:
            headers = {"X-Api-Key": api_key}
            response = requests.get(f"{test_url}/health", headers=headers, timeout=10)
            if response.status_code == 200:
                print(f"Successfully connected to Radarr at: {test_url}")
                return test_url
        except requests.exceptions.RequestException as e:
            print(f"{ORANGE}Testing URL {test_url} - Failed: {str(e)}{RESET}")
            continue
    
    raise ConnectionError(f"{RED}Unable to establish connection to Radarr. Tried the following URLs:\n" + 
                        "\n".join([f"- {base_url}{path}" for path in api_paths]) + 
                        f"\nPlease verify your URL and API key and ensure Radarr is running.{RESET}")

def get_radarr_movies(radarr_url, api_key):
    """Get all movies from Radarr"""
    try:
        url = f"{radarr_url}/movie"
        headers = {"X-Api-Key": api_key}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"{RED}Error connecting to Radarr: {str(e)}{RESET}")
        sys.exit(1)

def convert_utc_to_local(utc_date_str, utc_offset):
    """Convert UTC datetime to local time with offset"""
    if not utc_date_str:
        return None
        
    # Remove 'Z' if present and parse the datetime
    clean_date_str = utc_date_str.replace('Z', '')
    utc_date = datetime.fromisoformat(clean_date_str).replace(tzinfo=timezone.utc)
    
    # Apply the UTC offset
    local_date = utc_date + timedelta(hours=utc_offset)
    return local_date

def map_path(original_path, path_mappings):
    """Map Radarr path to actual filesystem path"""
    if not path_mappings:
        return original_path
    
    # Convert to string if it's a Path object
    path_str = str(original_path)
    
    # Try each mapping (longest first to handle nested paths)
    for radarr_path, actual_path in sorted(path_mappings.items(), key=lambda x: len(x[0]), reverse=True):
        if path_str.startswith(radarr_path):
            mapped_path = path_str.replace(radarr_path, actual_path, 1)
            print(f"{BLUE}[PATH MAPPING] {path_str} -> {mapped_path}{RESET}")
            return mapped_path
    
    return original_path

def sanitize_filename(filename):
    """Sanitize filename/folder name for Windows compatibility, especially UNC paths"""
    # Dictionary of invalid characters and their replacements
    replacements = {
        ':': ' -',      # Colon to dash
        '/': '-',       # Forward slash to dash  
        '\\': '-',      # Backslash to dash
        '?': '',        # Question mark removed
        '*': '',        # Asterisk removed
        '"': "'",       # Double quote to single quote
        '<': '(',       # Less than to parenthesis
        '>': ')',       # Greater than to parenthesis
        '|': '-',       # Pipe to dash
    }
    
    sanitized = filename
    for invalid_char, replacement in replacements.items():
        sanitized = sanitized.replace(invalid_char, replacement)
    
    # Remove any trailing dots or spaces (Windows restriction)
    sanitized = sanitized.rstrip('. ')
    
    return sanitized

def find_upcoming_movies(radarr_url, api_key, future_days_upcoming_movies, utc_offset=0, future_only=False, include_inCinemas=False, debug=False):
    """Find movies that are monitored and meet release date criteria"""
    future_movies = []
    released_movies = []
    
    cutoff_date = datetime.now(timezone.utc) + timedelta(days=future_days_upcoming_movies)
    now_local = datetime.now(timezone.utc) + timedelta(hours=utc_offset)
    
    if debug:
        print(f"{BLUE}[DEBUG] Cutoff date: {cutoff_date}, Now local: {now_local}{RESET}")
        print(f"{BLUE}[DEBUG] Future only mode: {future_only}{RESET}")
        print(f"{BLUE}[DEBUG] Include inCinemas: {include_inCinemas}{RESET}")
    
    all_movies = get_radarr_movies(radarr_url, api_key)
    
    if debug:
        print(f"{BLUE}[DEBUG] Found {len(all_movies)} total movies in Radarr{RESET}")
    
    for movie in all_movies:
        # Skip unmonitored movies
        if not movie.get('monitored', False):
            if debug:
                print(f"{ORANGE}[DEBUG] Skipping unmonitored movie: {movie['title']}{RESET}")
            continue
        
        # Skip movies that have already been downloaded
        if movie.get('hasFile', False):
            if debug:
                print(f"{ORANGE}[DEBUG] Skipping downloaded movie: {movie['title']}{RESET}")
            continue
        
        # Get release date based on include_inCinemas setting
        release_date_str = None
        release_type = None
        
        if include_inCinemas:
            # Check all three dates and use the earliest one
            dates_to_check = [
                (movie.get('digitalRelease'), 'Digital'),
                (movie.get('physicalRelease'), 'Physical'),
                (movie.get('inCinemas'), 'Cinema')
            ]
            
            valid_dates = [(date_str, rel_type) for date_str, rel_type in dates_to_check if date_str]
            
            if valid_dates:
                # Sort by date and pick the earliest
                valid_dates.sort(key=lambda x: x[0])
                release_date_str, release_type = valid_dates[0]
        else:
            # Only check digital and physical releases
            if movie.get('digitalRelease'):
                release_date_str = movie['digitalRelease']
                release_type = 'Digital'
            elif movie.get('physicalRelease'):
                release_date_str = movie['physicalRelease']
                release_type = 'Physical'
        
        if not release_date_str:
            if debug:
                print(f"{ORANGE}[DEBUG] No suitable release date found for {movie['title']}{RESET}")
            continue
        
        release_date = convert_utc_to_local(release_date_str, utc_offset)
        release_date_str_yyyy_mm_dd = release_date.date().isoformat()
        
        if debug:
            print(f"{BLUE}[DEBUG] {movie['title']} release date: {release_date} ({release_type}){RESET}")
        
        movie_dict = {
            'title': movie['title'],
            'tmdbId': movie.get('tmdbId'),
            'imdbId': movie.get('imdbId'),
            'path': movie.get('path', ''),
            'folderName': movie.get('folderName', ''),
            'year': movie.get('year', None),
            'releaseDate': release_date_str_yyyy_mm_dd,
            'releaseType': release_type
        }
        
        # Categorize based on release date
        if release_date > now_local and release_date <= cutoff_date:
            # Future release within range
            future_movies.append(movie_dict)
            if debug:
                print(f"{GREEN}[DEBUG] Added to future movies: {movie['title']}{RESET}")
        elif release_date <= now_local and not future_only:
            # Already released but not downloaded
            released_movies.append(movie_dict)
            if debug:
                print(f"{GREEN}[DEBUG] Added to released movies: {movie['title']}{RESET}")
    
    return future_movies, released_movies

def create_placeholder_video(movie, config, debug=False):
    """Create a copy of UMFK video in the Coming Soon folder"""
    # Get the source video file
    video_folder = Path(__file__).parent / 'video'
    source_files = list(video_folder.glob('UMFK.*'))
    
    if not source_files:
        print(f"{RED}No UMFK video file found in video folder{RESET}")
        return False
    
    source_file = source_files[0]
    video_extension = source_file.suffix
    
    movie_path = movie.get('path')
    if not movie_path:
        print(f"{RED}No path found for movie: {movie.get('title')}{RESET}")
        return False
    
    # Apply path mapping
    path_mappings = config.get('path_mapping', {})
    mapped_path = map_path(movie_path, path_mappings)
    
    # Create proper folder and file names
    movie_title = movie.get('title', 'Unknown')
    movie_year = movie.get('year', '')
    tmdb_id = movie.get('tmdbId', '')
    
    # Folder name: "Movie title (yyyy) {edition-Coming Soon}" - sanitized for Windows
    folder_name = sanitize_filename(f"{movie_title} ({movie_year}) {{edition-Coming Soon}}")

    # File name: "Movie title (yyyy) {tmdb-xxx} {edition-Coming Soon}" - sanitized for Windows  
    file_name = sanitize_filename(f"{movie_title} ({movie_year}) {{tmdb-{tmdb_id}}} {{edition-Coming Soon}}")
    
    # Create the Coming Soon folder
    base_path = Path(mapped_path)
    parent_dir = base_path.parent
    coming_soon_path = parent_dir / folder_name
    
    if debug:
        print(f"{BLUE}[DEBUG] Movie path: {movie_path}{RESET}")
        print(f"{BLUE}[DEBUG] Mapped path: {mapped_path}{RESET}")
        print(f"{BLUE}[DEBUG] Coming Soon path: {coming_soon_path}{RESET}")
        print(f"{BLUE}[DEBUG] Folder name: {folder_name}{RESET}")
        print(f"{BLUE}[DEBUG] File name: {file_name}{RESET}")
    
    # Check if Coming Soon folder already exists
    if coming_soon_path.exists():
        if debug:
            print(f"{ORANGE}[DEBUG] Coming Soon folder already exists for {movie['title']}{RESET}")
        return True
    
    try:
        # Create the folder
        coming_soon_path.mkdir(parents=True, exist_ok=True)
        
        # Copy the video file with the proper name
        dest_file = coming_soon_path / f"{file_name}{video_extension}"
        shutil.copy2(source_file, dest_file)
        
        size_mb = dest_file.stat().st_size / (1024 * 1024)
        print(f"{GREEN}Created placeholder for {movie['title']}: {dest_file.name} ({size_mb:.1f} MB){RESET}")
        return True
        
    except Exception as e:
        print(f"{RED}Error creating placeholder for {movie['title']}: {e}{RESET}")
        return False

def cleanup_placeholder_videos(radarr_url, api_key, config, future_movies, released_movies, debug=False):
    if debug:
        print(f"{BLUE}[DEBUG] Starting placeholder cleanup process{RESET}")
    
    removed_count = 0
    checked_count = 0
    path_mappings = config.get('path_mapping', {})
    
    # Get all movies from Radarr
    all_movies = get_radarr_movies(radarr_url, api_key)
    
    # Create a set of paths that should have Coming Soon folders
    valid_coming_soon_paths = set()
    for movie in future_movies + released_movies:
        if movie.get('path'):
            mapped_path = map_path(movie['path'], path_mappings)
            base_path = Path(mapped_path)
            parent_dir = base_path.parent
            
            # Use new naming convention with sanitization
            movie_title = movie.get('title', 'Unknown')
            movie_year = movie.get('year', '')
            folder_name = sanitize_filename(f"{movie_title} ({movie_year}) {{edition-Coming Soon}}")
            coming_soon_path = parent_dir / folder_name
            valid_coming_soon_paths.add(str(coming_soon_path))
    
    # Create a dictionary to map Coming Soon folder paths to their corresponding movies (if they exist in Radarr)
    radarr_movie_lookup = {}
    for movie in all_movies:
        movie_path = movie.get('path')
        if not movie_path:
            continue
        
        mapped_path = map_path(movie_path, path_mappings)
        base_path = Path(mapped_path)
        parent_dir = base_path.parent
        
        # Use new naming convention with sanitization
        movie_title = movie.get('title', 'Unknown')
        movie_year = movie.get('year', '')
        folder_name = sanitize_filename(f"{movie_title} ({movie_year}) {{edition-Coming Soon}}")
        coming_soon_path = parent_dir / folder_name
        radarr_movie_lookup[str(coming_soon_path)] = movie
    
    # Collect all unique parent directories from both current movies and valid paths
    parent_dirs_to_scan = set()
    
    # Add parent dirs from current Radarr movies
    for movie in all_movies:
        movie_path = movie.get('path')
        if movie_path:
            mapped_path = map_path(movie_path, path_mappings)
            base_path = Path(mapped_path)
            parent_dirs_to_scan.add(base_path.parent)
    
    # Add parent dirs from valid coming soon paths
    for valid_path in valid_coming_soon_paths:
        parent_dirs_to_scan.add(Path(valid_path).parent)
    
    if debug:
        print(f"{BLUE}[DEBUG] Scanning {len(parent_dirs_to_scan)} parent directories for Coming Soon folders{RESET}")
    
    # Scan all parent directories for Coming Soon folders
    for parent_dir in parent_dirs_to_scan:
        if not parent_dir.exists():
            continue
            
        # Look for folders matching the Coming Soon pattern
        try:
            for folder in parent_dir.iterdir():
                if folder.is_dir() and "{edition-Coming Soon}" in folder.name:
                    checked_count += 1
                    folder_path_str = str(folder)
                    
                    if debug:
                        print(f"{BLUE}[DEBUG] Found Coming Soon folder: {folder.name}{RESET}")
                    
                    should_remove = False
                    reason = ""
                    movie_title = "Unknown Movie"
                    
                    # Check if this folder corresponds to a movie in Radarr
                    if folder_path_str in radarr_movie_lookup:
                        movie = radarr_movie_lookup[folder_path_str]
                        movie_title = movie.get('title', 'Unknown Movie')
                        
                        # Check if movie has been downloaded
                        if movie.get('hasFile', False):
                            should_remove = True
                            reason = "movie has been downloaded"
                        # Check if folder is no longer in valid list
                        elif folder_path_str not in valid_coming_soon_paths:
                            should_remove = True
                            reason = "movie no longer meets criteria"
                        elif debug:
                            print(f"{BLUE}[DEBUG] Keeping placeholder for {movie_title} - still upcoming{RESET}")
                    else:
                        # Folder exists but no corresponding movie in Radarr
                        should_remove = True
                        reason = "movie no longer exists in Radarr"
                        # Try to extract movie title from folder name for better logging
                        try:
                            # Extract title from "Movie Title (Year) {edition-Coming Soon}" format
                            folder_name = folder.name
                            if " {edition-Coming Soon}" in folder_name:
                                movie_title = folder_name.replace(" {edition-Coming Soon}", "")
                        except:
                            movie_title = folder.name
                    
                    if should_remove:
                        try:
                            # Calculate size before deletion
                            total_size = sum(f.stat().st_size for f in folder.rglob('*') if f.is_file())
                            size_mb = total_size / (1024 * 1024)
                            
                            # Remove the folder and its contents
                            shutil.rmtree(folder)
                            removed_count += 1
                            print(f"{GREEN}Removed placeholder for {movie_title} - {reason} ({size_mb:.1f} MB freed){RESET}")
                            if debug:
                                print(f"{BLUE}[DEBUG] Deleted: {folder}{RESET}")
                        except Exception as e:
                            print(f"{RED}Error removing placeholder for {movie_title}: {e}{RESET}")
        except Exception as e:
            if debug:
                print(f"{ORANGE}[DEBUG] Error scanning directory {parent_dir}: {e}{RESET}")
            continue
    
    if removed_count > 0:
        print(f"{GREEN}Cleanup complete: Removed {removed_count} placeholder(s) from {checked_count} checked{RESET}")
    elif checked_count > 0:
        print(f"{GREEN}Cleanup complete: No placeholders needed removal ({checked_count} checked){RESET}")
    elif debug:
        print(f"{BLUE}[DEBUG] No Coming Soon folders found to check{RESET}")

def format_date(yyyy_mm_dd, date_format, capitalize=False):
    """Format date according to specified format"""
    dt_obj = datetime.strptime(yyyy_mm_dd, "%Y-%m-%d")
    
    format_mapping = {
        'mmm': '%b',    # Abbreviated month name
        'mmmm': '%B',   # Full month name
        'mm': '%m',     # 2-digit month
        'm': '%-m',     # 1-digit month
        'dddd': '%A',   # Full weekday name
        'ddd': '%a',    # Abbreviated weekday name
        'dd': '%d',     # 2-digit day
        'd': str(dt_obj.day),  # 1-digit day - direct integer conversion
        'yyyy': '%Y',   # 4-digit year
        'yyy': '%Y',    # 3+ digit year
        'yy': '%y',     # 2-digit year
        'y': '%y'       # Year without century
    }
    
    # Sort format patterns by length (longest first) to avoid partial matches
    patterns = sorted(format_mapping.keys(), key=len, reverse=True)
    
    # First, replace format patterns with temporary markers
    temp_format = date_format
    replacements = {}
    for i, pattern in enumerate(patterns):
        marker = f"@@{i}@@"
        if pattern in temp_format:
            replacements[marker] = format_mapping[pattern]
            temp_format = temp_format.replace(pattern, marker)
    
    # Now replace the markers with strftime formats
    strftime_format = temp_format
    for marker, replacement in replacements.items():
        strftime_format = strftime_format.replace(marker, replacement)
    
    try:
        result = dt_obj.strftime(strftime_format)
        if capitalize:
            result = result.upper()
        return result
    except ValueError as e:
        print(f"{RED}Error: Invalid date format '{date_format}'. Using default format.{RESET}")
        return yyyy_mm_dd  # Return original format as fallback

def create_overlay_yaml(output_file, future_movies, released_movies, config_sections):
    """Create overlay YAML file with movies grouped by release status and date"""
    # Ensure the directory exists
    output_dir = "/config/kometa/umfk/" if IS_DOCKER else "kometa/"
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, output_file)
    
    import yaml

    if not future_movies and not released_movies:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("#No matching movies found")
        return
    
    overlays_dict = {}
    
    # Process future movies
    if future_movies:
        # Group future movies by date
        date_to_tmdb_ids = defaultdict(list)
        all_future_tmdb_ids = set()
        
        for m in future_movies:
            if m.get("tmdbId"):
                all_future_tmdb_ids.add(m['tmdbId'])
                if m.get("releaseDate"):
                    date_to_tmdb_ids[m['releaseDate']].append(m.get('tmdbId'))
        
        # Future movies backdrop
        backdrop_config = deepcopy(config_sections.get("backdrop_future", {}))
        enable_backdrop = backdrop_config.pop("enable", True)
        
        if enable_backdrop and all_future_tmdb_ids:
            # Set default name if not provided in config
            if "name" not in backdrop_config:
                backdrop_config["name"] = "backdrop"
            
            all_tmdb_ids_str = ", ".join(str(i) for i in sorted(all_future_tmdb_ids) if i)
            
            overlays_dict["backdrop_future"] = {
                "overlay": backdrop_config,
                "tmdb_movie": all_tmdb_ids_str
            }
        
        # Future movies text overlays (with dates)
        text_config = deepcopy(config_sections.get("text_future", {}))
        enable_text = text_config.pop("enable", True)
        
        if enable_text and all_future_tmdb_ids:
            date_format = text_config.pop("date_format", "yyyy-mm-dd")
            use_text = text_config.pop("use_text", "Coming Soon")
            capitalize_dates = text_config.pop("capitalize_dates", True)
            
            for date_str in sorted(date_to_tmdb_ids):
                formatted_date = format_date(date_str, date_format, capitalize_dates)
                sub_overlay_config = deepcopy(text_config)
                
                # Set default name if not provided in config
                if "name" not in sub_overlay_config:
                    sub_overlay_config["name"] = f"text({use_text} {formatted_date})"
                else:
                    # If name is provided in config, append the formatted date
                    base_name = sub_overlay_config["name"]
                    sub_overlay_config["name"] = f"{base_name}({use_text} {formatted_date})"
                
                tmdb_ids_for_date = sorted(tmdb_id for tmdb_id in date_to_tmdb_ids[date_str] if tmdb_id)
                tmdb_ids_str = ", ".join(str(i) for i in tmdb_ids_for_date)
                
                block_key = f"UMFK_future_{formatted_date}"
                overlays_dict[block_key] = {
                    "overlay": sub_overlay_config,
                    "tmdb_movie": tmdb_ids_str
                }
    
    # Process released movies
    if released_movies:
        all_released_tmdb_ids = set()
        
        for m in released_movies:
            if m.get("tmdbId"):
                all_released_tmdb_ids.add(m['tmdbId'])
        
        # Released movies backdrop
        backdrop_config = deepcopy(config_sections.get("backdrop_released", {}))
        enable_backdrop = backdrop_config.pop("enable", True)
        
        if enable_backdrop and all_released_tmdb_ids:
            # Set default name if not provided in config
            if "name" not in backdrop_config:
                backdrop_config["name"] = "backdrop"
            
            all_tmdb_ids_str = ", ".join(str(i) for i in sorted(all_released_tmdb_ids) if i)
            
            overlays_dict["backdrop_released"] = {
                "overlay": backdrop_config,
                "tmdb_movie": all_tmdb_ids_str
            }
        
        # Released movies text overlay (single overlay for all)
        text_config = deepcopy(config_sections.get("text_released", {}))
        enable_text = text_config.pop("enable", True)
        
        if enable_text and all_released_tmdb_ids:
            use_text = text_config.pop("use_text", "Available Now")
            # Remove date-related configs as they're not needed
            text_config.pop("date_format", None)
            text_config.pop("capitalize_dates", None)
            
            sub_overlay_config = deepcopy(text_config)
            
            # Set default name if not provided in config
            if "name" not in sub_overlay_config:
                sub_overlay_config["name"] = f"text({use_text})"
            else:
                # If name is provided in config, append the use_text
                base_name = sub_overlay_config["name"]
                sub_overlay_config["name"] = f"{base_name}({use_text})"
            
            tmdb_ids_str = ", ".join(str(i) for i in sorted(all_released_tmdb_ids) if i)
            
            overlays_dict["UMFK_released"] = {
                "overlay": sub_overlay_config,
                "tmdb_movie": tmdb_ids_str
            }
    
    final_output = {"overlays": overlays_dict}
    
    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(final_output, f, sort_keys=False)

def create_collection_yaml(output_file, future_movies, released_movies, config):
    # Ensure the directory exists
    output_dir = "/config/kometa/umfk/" if IS_DOCKER else "kometa/"
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, output_file)
    
    """Create collection YAML file"""
    import yaml
    from yaml.representer import SafeRepresenter
    from collections import OrderedDict

    # Add representer for OrderedDict
    def represent_ordereddict(dumper, data):
        return dumper.represent_mapping('tag:yaml.org,2002:map', data.items())
    
    yaml.add_representer(OrderedDict, represent_ordereddict, Dumper=yaml.SafeDumper)

    # Get the collection configuration
    config_key = "collection_upcoming_movies"
    collection_config = {}
    collection_name = "Upcoming Movies"
    
    if config_key in config:
        collection_config = deepcopy(config[config_key])
        collection_name = collection_config.pop("collection_name", "Upcoming Movies")
    
    # Get the future_days value for summary (only if not overridden in config)
    if "summary" not in collection_config:
        future_days = config.get('future_days_upcoming_movies', 30)
        summary = f"Movies releasing within {future_days} days or already released but not yet available"
        collection_config["summary"] = summary
    
    class QuotedString(str):
        pass

    def quoted_str_presenter(dumper, data):
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='"')

    yaml.add_representer(QuotedString, quoted_str_presenter, Dumper=yaml.SafeDumper)

    # Combine all movies
    all_movies = future_movies + released_movies
    
    # Handle the case when no movies are found
    if not all_movies:
        # Use default fallback structure but allow config overrides
        fallback_config = {
            "plex_search": {
                "all": {
                    "label": collection_name
                }
            },
            "item_label.remove": collection_name,
            "smart_label": "random",
            "build_collection": False
        }
        
        # Override with any config values
        fallback_config.update(collection_config)
        
        data = {
            "collections": {
                collection_name: fallback_config
            }
        }
        
        with open(output_file, "w", encoding="utf-8") as f:
            yaml.dump(data, f, Dumper=yaml.SafeDumper, sort_keys=False)
        return
    
    tmdb_ids = [m['tmdbId'] for m in all_movies if m.get('tmdbId')]
    if not tmdb_ids:
        # Use default fallback structure but allow config overrides
        fallback_config = {
            "plex_search": {
                "all": {
                    "label": collection_name
                }
            },
            "non_item_remove_label": collection_name,
            "build_collection": False
        }
        
        # Override with any config values
        fallback_config.update(collection_config)
        
        data = {
            "collections": {
                collection_name: fallback_config
            }
        }
        
        with open(output_file, "w", encoding="utf-8") as f:
            yaml.dump(data, f, Dumper=yaml.SafeDumper, sort_keys=False)
        return

    # Convert to comma-separated
    tmdb_ids_str = ", ".join(str(i) for i in sorted(tmdb_ids))

    # Create the collection data structure
    collection_data = deepcopy(collection_config)
    
    # Add default sync_mode if not provided in config
    if "sync_mode" not in collection_data:
        collection_data["sync_mode"] = "sync"
    
    # Add tmdb_movie (this should always be set by the script)
    collection_data["tmdb_movie"] = tmdb_ids_str

    # Create the final structure with ordered keys
    ordered_collection = OrderedDict()
    
    # Add summary first if it exists
    if "summary" in collection_data:
        ordered_collection["summary"] = collection_data["summary"]
    
    # Add sort_title second if it exists
    if "sort_title" in collection_data:
        if isinstance(collection_data["sort_title"], str):
            ordered_collection["sort_title"] = QuotedString(collection_data["sort_title"])
        else:
            ordered_collection["sort_title"] = collection_data["sort_title"]
    
    # Add all other keys except sync_mode and tmdb_movie
    for key, value in collection_data.items():
        if key not in ["summary", "sort_title", "sync_mode", "tmdb_movie"]:
            ordered_collection[key] = value
    
    # Add sync_mode and tmdb_movie at the end
    ordered_collection["sync_mode"] = collection_data["sync_mode"]
    ordered_collection["tmdb_movie"] = collection_data["tmdb_movie"]

    data = {
        "collections": {
            collection_name: ordered_collection
        }
    }

    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(data, f, Dumper=yaml.SafeDumper, sort_keys=False)

def check_video_file():
    """Check if UMFK video file exists"""
    video_folder = Path(__file__).parent / 'video'
    if not video_folder.exists():
        print(f"{RED}Video folder not found. Please create a 'video' folder in the script directory.{RESET}")
        return False
    
    source_files = list(video_folder.glob('UMFK.*'))
    if not source_files:
        print(f"{RED}UMFK video file not found in video folder. Please add a video file named 'UMFK' (with any extension).{RESET}")
        return False
    
    source_file = source_files[0]
    size_mb = source_file.stat().st_size / (1024 * 1024)
    print(f"{GREEN}Found video file: {source_file.name} ({size_mb:.1f} MB){RESET}")
    return True

def main():
    start_time = datetime.now()
    print(f"{BLUE}{'*' * 44}\n{'*' * 5} Upcoming Movies for Kometa {VERSION} {'*' * 5}\n{'*' * 44}{RESET}")
    check_for_updates()
    
    # Check if video file exists
    if not check_video_file():
        sys.exit(1)
    
    config = load_config()
    
    try:
        # Process and validate Radarr URL
        radarr_url = process_radarr_url(config['radarr_url'], config['radarr_api_key'])
        radarr_api_key = config['radarr_api_key']
        
        # Get configuration values
        future_days_upcoming_movies = config.get('future_days_upcoming_movies', 30)
        utc_offset = float(config.get('utc_offset', 0))
        future_only = str(config.get("future_only", "false")).lower() == "true"
        include_inCinemas = str(config.get("include_inCinemas", "false")).lower() == "true"
        cleanup = str(config.get("cleanup", "true")).lower() == "true"
        debug = str(config.get("debug", "false")).lower() == "true"
        
        print(f"future_days_upcoming_movies: {future_days_upcoming_movies}")
        print(f"UTC offset: {utc_offset} hours")
        print(f"future_only: {future_only}")
        print(f"include_inCinemas: {include_inCinemas}")
        print(f"cleanup: {cleanup}")
        print(f"debug: {debug}\n")
        
        # ---- Find Upcoming Movies ----
        print(f"{BLUE}Finding upcoming movies...{RESET}")
        future_movies, released_movies = find_upcoming_movies(
            radarr_url, radarr_api_key, future_days_upcoming_movies, utc_offset, future_only, include_inCinemas, debug
        )
        
        if future_movies:
            print(f"{GREEN}Found {len(future_movies)} future movies releasing within {future_days_upcoming_movies} days:{RESET}")
            for movie in future_movies:
                release_info = f" - {movie['releaseType']} Release: {movie['releaseDate']}"
                print(f"- {movie['title']}" + (f" ({movie['year']})" if movie['year'] else "") + release_info)
        else:
            print(f"{ORANGE}No future movies found releasing within {future_days_upcoming_movies} days.{RESET}")
        
        if released_movies:
            print(f"\n{GREEN}Found {len(released_movies)} released movies not yet available:{RESET}")
            for movie in released_movies:
                release_info = f" - {movie['releaseType']} Released: {movie['releaseDate']}"
                print(f"- {movie['title']}" + (f" ({movie['year']})" if movie['year'] else "") + release_info)
        elif not future_only:
            print(f"{ORANGE}No released movies found that are not yet available.{RESET}")
        
        # ---- Create Placeholder Videos ----
        all_movies = future_movies + released_movies
        if all_movies:
            print(f"\n{BLUE}Creating placeholder videos...{RESET}")
            successful_creates = 0
            failed_creates = 0
            
            for movie in all_movies:
                if create_placeholder_video(movie, config, debug):
                    successful_creates += 1
                else:
                    failed_creates += 1
            
            print(f"\n{GREEN}Placeholder creation summary:{RESET}")
            print(f"Successful: {successful_creates}")
            print(f"Failed: {failed_creates}")
        
        # ---- Cleanup Placeholder Videos ----
        if cleanup:
            print(f"\n{BLUE}Checking for placeholders to cleanup...{RESET}")
            cleanup_placeholder_videos(radarr_url, radarr_api_key, config, future_movies, released_movies, debug)
        else:
            if debug:
                print(f"{BLUE}[DEBUG] Placeholder cleanup is disabled{RESET}")
        
        # ---- Create Kometa subfolder ----
        kometa_folder = Path(__file__).parent / "Kometa"
        kometa_folder.mkdir(exist_ok=True)
        
        # ---- Create YAML Files ----
        overlay_file = kometa_folder / "UMFK_MOVIES_UPCOMING_OVERLAYS.yml"
        collection_file = kometa_folder / "UMFK_MOVIES_UPCOMING_COLLECTION.yml"
        
        create_overlay_yaml(str(overlay_file), future_movies, released_movies,
                          {"backdrop_future": config.get("backdrop_upcoming_movies_future", {}),
                           "text_future": config.get("text_upcoming_movies_future", {}),
                           "backdrop_released": config.get("backdrop_upcoming_movies_released", {}),
                           "text_released": config.get("text_upcoming_movies_released", {})})
        
        create_collection_yaml(str(collection_file), future_movies, released_movies, config)
        
        print(f"\n{GREEN}YAML files created successfully in Kometa folder{RESET}")
        
        # Calculate and display runtime
        end_time = datetime.now()
        runtime = end_time - start_time
        hours, remainder = divmod(runtime.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)
        runtime_formatted = f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"
        
        print(f"Total runtime: {runtime_formatted}")
        
    except ConnectionError as e:
        print(f"{RED}Error: {str(e)}{RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"{RED}Unexpected error: {str(e)}{RESET}")
        sys.exit(1)

if __name__ == "__main__":
    main()
