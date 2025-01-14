import sublime
import subprocess
import os
import os.path
import threading
import platform
from time import sleep

# Used for output suppression when calling subprocess functions; see
# http://stackoverflow.com/questions/10251391/suppressing-output-in-python-subprocess-call
devnull = open(os.devnull, 'w')

# Used to prevent a new command prompt window from popping up every time a new
# process is spawned on Windows. See
# https://docs.python.org/2/library/subprocess.html#subprocess.STARTUPINFO
if platform.system() == 'Windows':
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags = subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
else:
    startupinfo = None

def start(): # Gets invoked at the bottom of this file.
    """
    Regularly (every 1h) updates the file_exclude_patterns setting.
    """
    if is_first_launch():
        migrate_exclude_patterns()
        record_first_launch()

    def run():
        update_file_exclude_patterns()
        sublime.set_timeout(run, 1000 * 3600)

    run()

def update_file_exclude_patterns():
    """
    Updates the "file_exclude_patterns" preference to include all .gitignored
    files.

    Also includes any additional files or folders listed in the
    "extra_file_exclude_patterns" and "extra_folder_exclude_patterns" settings.
    """
    s = sublime.load_settings("Preferences.sublime-settings")
    file_exclude_patterns = s.get('binary_file_patterns', []) or []
    folder_exclude_patterns = s.get('binary_file_patterns', []) or []
    for path in all_ignored_paths():
        is_directory = os.path.isdir(path)
        if platform.system() == 'Windows':
            # For some bizarre reason Sublime wants all its filenames to look like
            #     C/somedir/somefile
            # instead of
            #     C:\somedir\somefile
            # as they are normally written on Windows, and will not understand the
            # latter at all. All the other functions in this file return paths with
            # OS-standard separtors and include the colon after the drive letter on
            # Windows, so we need to convert them here to Sublime-format.
            path = windows_path_to_sublime_path(path)
        if is_directory:
            folder_exclude_patterns.append(path)
            folder_exclude_patterns.append(path + '/*')
        else:
            file_exclude_patterns.append(path)

    new_files = set(file_exclude_patterns)
    old_files = set(s.get('binary_file_patterns', []) or [])

    # Only make changes if anything has actually changed, to avoid spamming the
    # sublime console
    if new_files != old_files:
        s.set('binary_file_patterns', list(file_exclude_patterns))
        sublime.save_settings("Preferences.sublime-settings")

def all_ignored_paths():
    """
    Returns a list of all .gitignored files or folders contained in repos
    contained within or containing any folders open in any open windows.
    """

    open_folders = set()
    for window in sublime.windows():
        open_folders.update(window.folders())

    all_ignored_paths = set()
    for folder in open_folders:
        ignored_paths = folder_ignored_paths(folder)
        all_ignored_paths.update(ignored_paths)

    return list(all_ignored_paths)

def folder_ignored_paths(folder):
    """
    Returns a list (without duplicates, in the case of weird repo-nesting) of
    all files/folders within the given folder that are git ignored.

    The folder itself need not be the top level of a git repo, nor even within
    a git repo.
    """

    all_ignored_paths = set()

    # First find all repos CONTAINED in this folder:
    repos = set(find_git_repos(folder))

    # Then, additionally, if this folder is itself contained within a repo,
    # find the .git folder of the repo containing it:
    if is_in_git_repo(folder):
        repos.add(parent_repo_path(folder))

    # Now we find all the ignored paths in any of the above repos
    for git_repo in repos:
        ignored_paths = repo_ignored_paths(git_repo)
        all_ignored_paths.update(ignored_paths)

    return list(all_ignored_paths)

def is_in_git_repo(folder):
    """
    Returns true if the given folder is contained within a git repo
    """

    exit_code = subprocess.call(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=folder,
        stdout=devnull,
        stderr=devnull,
        startupinfo=startupinfo
    )

    return exit_code == 0

def parent_repo_path(folder):
    """
    Takes the path to a folder contained within a git repo, and returns the
    parent repo.
    """

    # abspath call converts forward slashes to backslashes on Windows; we do
    # this wherever necessary to keep the format of our paths standardised on
    # Windows.
    return os.path.abspath(
        subprocess.Popen(
            ['git', 'rev-parse', '--show-toplevel'],
            stdout=subprocess.PIPE,
            cwd=folder,
            startupinfo=startupinfo
        ).stdout.read().decode('utf-8', 'ignore').strip()
    )

def find_git_repos(folder):
    """
    Returns a list of all git repos within the given ancestor folder.
    """

    return [root for root, subfolders, files
                 in os.walk(folder)
                 if '.git' in subfolders]

def repo_ignored_paths(git_repo):
    """
    Takes the path of a git repo and lists all ignored files/folders in the
    repo.
    """

    # Trick for listing ignored files nicked from
    # http://stackoverflow.com/a/2196755/1709587
    command_output = subprocess.Popen(
        ['git', 'clean', '-ndX'],
        stdout=subprocess.PIPE,
        cwd=git_repo,
        startupinfo=startupinfo,
        env={'LANG':'C'}
    ).stdout.read()

    command_output = command_output.decode('utf-8', 'ignore')

    if command_output.isspace() or command_output == u'':
        return []

    lines = command_output.strip().split(u'\n')
    # Each line in `lines` now looks something like:
    # "Would remove foo/bar/yourfile.txt"

    relative_paths = [line.replace(u'Would remove ', u'', 1).rstrip(u'/')
                      for line in lines]
    absolute_paths = [os.path.join(git_repo, path) for path in relative_paths]
    return absolute_paths

def is_first_launch():
    s = sublime.load_settings("gitignorer.sublime-settings")
    return not s.get('_sublime_gitignorer_has_run', False)

def migrate_exclude_patterns():
    """
    Runs on first launch; purpose is to prevent people who have already set
    exclusion patterns from losing them when they install this package.
    """

def record_first_launch():
    s = sublime.load_settings("gitignorer.sublime-settings")
    s.set('_sublime_gitignorer_has_run', True)
    sublime.save_settings("gitignorer.sublime-settings")

def windows_path_to_sublime_path(path):
    """
    Removes the colon after the drive letter and replaces backslashes with
    slashes.

    e.g.

        windows_path_to_sublime_path("C:\somedir\somefile")
        == "C/somedir/somefile"
    """

    assert(path[1] == u':')
    without_colon = path[0] + path[2:]
    return without_colon.replace(u'\\', u'/')

start()
