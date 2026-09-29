"""Checks TriageUI before a release and cuts the release zip. Run it on the Mac, where git is.

    python tools/release.py check      every rule a release must pass; it changes nothing
    python tools/release.py package    dist/TriageUI-vX.Y.Z.zip, the skin built by the tag vX.Y.Z

check lists each problem on a line and exits 1 if there are any. It reads git, the tracked files and the EverQuest
folder (EQ_DIR, C:\\QUARM or the Mac mount, or --eq), whose per-character files name the characters that must never
appear in the repo. A match is reported by file and line, or by commit, never by the name. It also runs the tests
(--no-tests skips them) and builds the skin from that folder into a temporary one.

package builds the skin with the tag's build_skin.py on default from the same EverQuest folder and zips the TriageUI
folder, ready to drag into uifiles. Everything in it is ours but its EQUI_Animations.xml: default's, with ours added.
"""
import argparse
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from collections import namedtuple
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.dont_write_bytecode = True
import build_skin as skin  # noqa: E402

EQ_DIRS = [os.environ.get('EQ_DIR', ''), r'C:\QUARM', '/Volumes/[C] Windows 11/QUARM']
BRANCH = 'dev'
DIST = REPO / 'dist'
# Every commit's author and committer, with UTC dates, so neither the user's real identity nor their timezone is public.
IDENTITY = ('CopperGlade', '3092256+CopperGlade@users.noreply.github.com')
UTC = '+0000'
# Lines crediting an AI. A message that names CLAUDE.md is fine.
ATTRIBUTION = re.compile(r'^\s*co-authored-by:|generated with.*claude|noreply@anthropic\.com', re.I | re.M)
# Never tracked: the local notes, what the tools write, and any texture or skin XML. Our pixels and XML are generated,
# and other people's skin files stay on the user's machine.
UNTRACKED_FILES = ('claude.md',)
UNTRACKED_FOLDERS = ('notes/', 'build/', 'dist/')
UNTRACKED_SUFFIXES = ('.tga', '.dds', '.bmp', '.xml')
# The EverQuest folder's per-character files: UI_<name>_pq.proj.ini (the window layout), BZR_<name>_pq.proj.ini (the
# bazaar trader), <name>_pq.proj.ini and <name>_spellsets.ini.
CHARACTER_FILE = re.compile(r'(?:UI_|BZR_)?([A-Za-z]+)_(?:pq\.proj|spellsets)\.ini', re.I)
ALLOWED_NAMES = {'sebik'}
CONFTEST = REPO / 'tests' / 'conftest.py'  # its SECOND_PLAYER may appear under tests/
# Project Quarm forbids playing several characters at once, so nothing mentions it. A close box, a tab box or a
# dialog box is the skin's own word.
BOXING = re.compile(r'multi-?box|\bboxing\b|\bboxers?\b|\bdual[- ]?box', re.I)
VERSION_PATTERN = r'\d+\.\d+\.\d+'

Commit = namedtuple('Commit', 'hash author author_email author_date committer committer_email committer_date message')


def git(*args):
    return subprocess.run(['git', '-C', str(REPO), *args], capture_output=True, text=True, encoding='utf-8',
                          check=True).stdout


# The rules, on plain data

def state_problems(branch, status):
    """The branch and working tree: a release is cut from dev with everything committed."""
    problems = []
    if branch != BRANCH:
        problems.append(f'git: on {branch}, not {BRANCH}')
    if status.strip():
        problems.append('git: the working tree has uncommitted changes (git status)')
    return problems


def version_key(version):
    return tuple(int(part) for part in version.split('.'))


def readme_version(readme):
    """The version on README's tagline, the first line under its heading, or None."""
    for line in readme.splitlines():
        if line.strip() and not line.startswith('#'):
            found = re.search(rf'· v({VERSION_PATTERN}) ·', line)
            return found.group(1) if found else None
    return None


def source_version(text):
    """VERSION as build_skin.py's text sets it, or None."""
    found = re.search(r"^VERSION = '([^']*)'", text, re.M)
    return found.group(1) if found else None


def version_problems(version, readme, tags):
    """VERSION is X.Y.Z, above every release tag, not tagged yet, and on README's tagline."""
    if not re.fullmatch(VERSION_PATTERN, version):
        return [f'build_skin.py: VERSION {version} isn\'t X.Y.Z']
    problems = []
    released = [tag[1:] for tag in tags if re.fullmatch(f'v{VERSION_PATTERN}', tag)]
    if version in released:
        problems.append(f'build_skin.py: v{version} is already tagged, so VERSION needs a bump')
    elif released and version_key(version) < max(map(version_key, released)):
        problems.append(f'build_skin.py: VERSION {version} is below the latest tag')
    shown = readme_version(readme)
    if shown != version:
        problems.append(f'README.md: the tagline shows {f"v{shown}" if shown else "no version"}, not v{version}')
    return problems


def identity_problems(commits):
    """Every author and committer is CopperGlade's noreply identity, with a UTC date. The wrong one isn't printed."""
    problems = []
    for commit in commits:
        for role, name, email, date in (
                ('author', commit.author, commit.author_email, commit.author_date),
                ('committer', commit.committer, commit.committer_email, commit.committer_date)):
            if (name, email) != IDENTITY:
                problems.append(f'commit {commit.hash[:7]}: the {role} isn\'t {IDENTITY[0]} <{IDENTITY[1]}>')
            if not date.endswith(UTC):
                problems.append(f'commit {commit.hash[:7]}: the {role} date isn\'t UTC')
    return problems


def attribution_problems(commits):
    return [f'commit {commit.hash[:7]}: its message credits an AI'
            for commit in commits if ATTRIBUTION.search(commit.message)]


def tracked_problems(paths):
    """Only our own files are tracked."""
    problems = []
    for path in paths:
        lower = path.lower()
        if (lower.rsplit('/', 1)[-1] in UNTRACKED_FILES or lower.startswith(UNTRACKED_FOLDERS)
                or lower.endswith(UNTRACKED_SUFFIXES)):
            problems.append(f'{path}: tracked, but it must never be')
    return problems


def character_names(eq_dir):
    """The lowercased names of the characters with files in the EverQuest folder, but Sebik."""
    names = set()
    for path in Path(eq_dir).iterdir():
        found = CHARACTER_FILE.fullmatch(path.name)
        if found and path.is_file():
            names.add(found.group(1).lower())
    return names - ALLOWED_NAMES


def second_player(conftest):
    """The lowercased SECOND_PLAYER that conftest.py's text sets, or None."""
    found = re.search(r"^SECOND_PLAYER = '([A-Za-z]+)'", conftest, re.M)
    return found.group(1).lower() if found else None


def name_problems(texts, names, test_name=None):
    """Where texts ({where: text}, a path or 'commit <hash>') use a name, as a word of its own. test_name may appear
    under tests/. The name itself is never printed."""
    if not names:
        return []
    # Letters only around it: a name inside a longer word is someone else's, one between underscores is the name.
    pattern = re.compile(r'(?<![A-Za-z])(?:' + '|'.join(map(re.escape, sorted(names))) + r')(?![A-Za-z])', re.I)
    problems = []
    for where, text in texts.items():
        for number, line in enumerate(text.splitlines(), 1):
            if any(not (found.group().lower() == test_name and where.startswith('tests/'))
                   for found in pattern.finditer(line)):
                problems.append(f'{where}:{number}: a character name from the EverQuest folder')
    return problems


def boxing_problems(texts):
    return [f'{where}:{number}: mentions playing several characters at once'
            for where, text in texts.items() for number, line in enumerate(text.splitlines(), 1)
            if BOXING.search(line)]


def zip_name(version):
    return f'{skin.SKIN_NAME}-v{version}.zip'


def build_zip(source, eq_dir, out):
    """Builds the skin with source, a build_skin.py's text, on default from eq_dir, and zips it as out: the skin's
    files in a TriageUI folder, so dragging that folder into uifiles installs it. Returns out."""
    with tempfile.TemporaryDirectory() as scratch:
        builder = Path(scratch) / 'build_skin.py'
        builder.write_text(source, encoding='utf-8')
        # Its own module name, so the given builder runs and not the working tree's, which is already imported.
        spec = importlib.util.spec_from_file_location('tagged_build_skin', builder)
        tagged = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tagged)
        try:
            folder = tagged.build(eq_dir, out=Path(scratch) / tagged.SKIN_NAME)
        except tagged.BuildError as error:  # the given builder's own class, not skin.BuildError
            raise skin.BuildError(str(error)) from error
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(folder.iterdir()):
                # Dotfiles are the Mac's metadata, never the skin's.
                if path.is_file() and not path.name.startswith('.'):
                    archive.write(path, f'{folder.name}/{path.name}')
    return out


# Reading the repo

def tags():
    return git('tag', '--list').split()


def last_tag():
    """The latest release tag behind HEAD, or None before the first release."""
    try:
        return git('describe', '--tags', '--abbrev=0', '--match', 'v*').strip()
    except subprocess.CalledProcessError:
        return None


def commits_since(tag):
    """The commits since tag, or the whole history without one, newest first."""
    fields = '%x1f'.join(['%H', '%an', '%ae', '%ai', '%cn', '%ce', '%ci', '%B'])
    log = git('log', f'--format={fields}%x1e', *([f'{tag}..HEAD'] if tag else []))
    return [Commit(*record.strip('\n').split('\x1f')) for record in log.split('\x1e') if record.strip()]


def tracked_texts(paths):
    """The tracked files that are text, by path."""
    texts = {}
    for path in paths:
        try:
            texts[path] = (REPO / path).read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            pass
    return texts


def find_eq(eq_dir):
    folders = [Path(eq_dir)] if eq_dir else [Path(d) for d in EQ_DIRS if d]
    return next((folder for folder in folders if (folder / 'uifiles' / skin.DEFAULT_BASE).is_dir()), None)


def run_tests():
    """Runs the suite; returns (passed, pytest's summary line)."""
    result = subprocess.run([sys.executable, '-B', '-m', 'pytest', 'tests', '-p', 'no:cacheprovider', '-q'],
                            cwd=REPO, capture_output=True, text=True, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    return result.returncode == 0, lines[-1] if lines else 'no output'


def check(eq_dir=None, tests=True):
    """Every problem in the way of releasing VERSION."""
    tag = last_tag()
    commits = commits_since(tag)
    print(f'TriageUI {skin.VERSION}, {len(commits)} commits since {tag or "the start"}:')
    for commit in commits:
        print(f'  {commit.hash[:7]} {commit.message.splitlines()[0] if commit.message else ""}')
    paths = git('ls-files').splitlines()
    texts = tracked_texts(paths)
    problems = state_problems(git('rev-parse', '--abbrev-ref', 'HEAD').strip(), git('status', '--porcelain'))
    problems += version_problems(skin.VERSION, texts.get('README.md', ''), tags())
    problems += identity_problems(commits) + attribution_problems(commits) + tracked_problems(paths)
    problems += boxing_problems(texts)
    eq = find_eq(eq_dir)
    if eq is None:
        problems.append(f'no EverQuest folder with uifiles/{skin.DEFAULT_BASE} found (--eq), so names and the build '
                        'went unchecked')
    else:
        messages = {f'commit {commit.hash[:7]}': commit.message for commit in commits}
        problems += name_problems({**texts, **messages}, character_names(eq), second_player(CONFTEST.read_text()))
        with tempfile.TemporaryDirectory() as scratch:
            try:
                skin.build(eq, out=Path(scratch) / skin.SKIN_NAME)
                print(f'Build from {eq}: fine')
            except skin.BuildError as error:
                problems.append(f'build: {error}')
    if tests:
        passed, summary = run_tests()
        print(f'Tests: {summary}')
        if not passed:
            problems.append(f'tests: {summary}')
    return problems


def package(version=skin.VERSION, eq_dir=None):
    """Writes dist/TriageUI-vX.Y.Z.zip, the skin as the tag's build_skin.py builds it; returns its path."""
    tag = f'v{version}'
    if tag not in tags():
        raise SystemExit(f'There is no tag {tag} yet: tag the release commit first.')
    source = git('show', f'{tag}:build_skin.py')
    tagged = source_version(source)
    if tagged != version:
        raise SystemExit(f'{tag}\'s build_skin.py says VERSION {tagged}, not {version}.')
    eq = find_eq(eq_dir)
    if eq is None:
        raise SystemExit(f'No EverQuest folder with uifiles/{skin.DEFAULT_BASE} found to build from: give it with --eq.')
    DIST.mkdir(exist_ok=True)
    try:
        return build_zip(source, eq, DIST / zip_name(version))
    except skin.BuildError as error:
        raise SystemExit(f'build: {error}') from error


def main(argv=None):
    parser = argparse.ArgumentParser(description='Checks TriageUI before a release and cuts the release zip.')
    commands = parser.add_subparsers(dest='command', required=True)
    checking = commands.add_parser('check', help='every rule a release must pass; it changes nothing')
    checking.add_argument('--eq', type=Path, help='the EverQuest folder, for the character names and a real build')
    checking.add_argument('--no-tests', action='store_true', help='skip the test suite')
    packaging = commands.add_parser('package', help=f'dist/{zip_name(skin.VERSION)}, the skin built by the tag '
                                                    f'v{skin.VERSION}')
    packaging.add_argument('--eq', type=Path, help='the EverQuest folder, whose uifiles/default the skin is built on')
    args = parser.parse_args(argv)
    if args.command == 'package':
        out = package(eq_dir=args.eq)
        print(f'Wrote {out}')
        print(f'Attach it to the GitHub release v{skin.VERSION}, with dist/release-notes-v{skin.VERSION}.md as its notes.')
        return 0
    problems = check(args.eq, not args.no_tests)
    if problems:
        print(f'{len(problems)} problem{"s" if len(problems) > 1 else ""}:')
        for problem in problems:
            print(f'  {problem}')
        return 1
    print(f'Ready to release v{skin.VERSION}.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
