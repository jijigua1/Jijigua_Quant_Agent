"""Single-user paper library inside the operator-configured research workspace.

Uploaded PDFs are untrusted bytes: never executed, never followed as links, parsed only in a resource-limited child
(Linux). Identity = SHA-256 of the bytes: identical bytes are deduplicated; the same file name with new bytes is a new
version, never an overwrite. Discovery resolves natural phrases ("刚上传的", a name fragment) to one paper, or returns the
candidates for the user to choose. This is a single-user controlled workspace, not a multi-tenant service.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import unicodedata

from .contracts import canonical
from .security import Denied

MAX_BYTES = 50 * 1024 ** 2
MAX_PAPERS = 300
TITLE_ARTEFACT = re.compile(r'\.(tex|dvi|docx?)$|^PII:|^Microsoft Word|^untitled|use style|^paper title|^arXiv:\S|'
                            r'^(研究报告|research report|working paper)$|'
                            # web stamps and journal running heads are not titles (live H2: www.cgws.com, ssoar.info, "Vol.42, No.2")
                            r'^\[?(https?://|www\.)|^vol\.?\s*\d+|^volume\s+\d+|^\d+(\s|$)|^doi:', re.I)
MAX_TOTAL_BYTES = 3 * 1024 ** 3
MAX_PAGES = 400


class PaperError(Denied):
    pass


def _now():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')


def _digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as src:
        for block in iter(lambda: src.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def safe_name(name):
    """Display name only (never a path): last component, NFC, control characters removed, bounded."""
    name = unicodedata.normalize('NFC', str(name)).replace('\\', '/').split('/')[-1]
    name = ''.join(ch for ch in name if unicodedata.category(ch)[0] != 'C').strip()
    return (name or 'paper.pdf')[:160]


def pdf_metadata(path, timeout=60):
    """Open the PDF in a child with CPU/memory limits (Linux); returns pages, encrypted, title. Never extracts code."""
    def probe():
        import fitz
        doc = fitz.open(str(path))
        try:
            if doc.needs_pass or doc.is_encrypted:
                return dict(encrypted=True, pages=None, title='')
            meta = doc.metadata or {}
            title = (meta.get('title') or '').strip()
            first = doc[0].get_text('text') if doc.page_count else ''
            lines = [x.strip() for x in first.splitlines() if len(x.strip()) > 8]
            # Typesetting artefacts (PII:..., *.tex, Microsoft Word - ..., template placeholders, arXiv stamps, generic
            # "研究报告") are not titles; fall back to the first page-one line that is not one either.
            if not title or TITLE_ARTEFACT.search(title):
                title = next((x for x in lines if not TITLE_ARTEFACT.search(x)), '')
            heading = ' '.join(' '.join(lines[:12]).split())[:600]
            return dict(encrypted=False, pages=doc.page_count, title=title[:200], heading=heading)
        finally:
            doc.close()
    if os.name != 'posix':
        try:
            return probe()
        except Exception as exc:
            raise PaperError('PDF_UNREADABLE') from exc
    read_end, write_end = os.pipe()
    pid = os.fork()
    if pid == 0:
        try:
            import resource
            os.close(read_end)
            resource.setrlimit(resource.RLIMIT_CPU, (timeout, timeout))
            resource.setrlimit(resource.RLIMIT_AS, (1536 * 1024 ** 2,) * 2)
            resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            os.write(write_end, json.dumps(probe()).encode())
            os._exit(0)
        except BaseException:
            os._exit(3)
    os.close(write_end)
    deadline = time.monotonic() + timeout + 5
    while True:
        done, status = os.waitpid(pid, os.WNOHANG)
        if done:
            break
        if time.monotonic() > deadline:
            os.kill(pid, 9)
            os.waitpid(pid, 0)
            os.close(read_end)
            raise PaperError('PDF_PARSE_TIMEOUT')
        time.sleep(.05)
    raw = os.read(read_end, 1 << 16)
    os.close(read_end)
    if not os.WIFEXITED(status) or os.WEXITSTATUS(status):
        raise PaperError('PDF_UNREADABLE')
    return json.loads(raw)


class PaperLibrary:
    def __init__(self, root):
        root = Path(root)
        if not root.is_absolute() or '..' in root.parts or root.is_symlink():
            raise Denied('PAPER_ROOT_INVALID')
        self.root = root
        for sub in ('files', 'incoming', 'cache', 'tasks', 'approved_code'):
            d = root / sub
            d.mkdir(mode=0o700, parents=True, exist_ok=True)
            if d.is_symlink():
                raise Denied('PAPER_ROOT_LINK')
        self.registry_path = root / 'registry.json'

    # ------------------------------------------------------------------ registry
    def entries(self):
        if not self.registry_path.exists():
            return []
        if self.registry_path.is_symlink():
            raise Denied('PAPER_REGISTRY_LINK')
        return json.loads(self.registry_path.read_text(encoding='utf-8'))

    def _save(self, rows):
        temp = self.registry_path.with_name('registry.' + str(os.getpid()) + '.tmp')
        temp.write_text(canonical(rows, max_bytes=4 * 1024 ** 2), encoding='utf-8')
        os.replace(temp, self.registry_path)

    def _lock(self):
        lock = self.root / '.registry.lock'
        for _ in range(200):
            try:
                return os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                if time.time() - lock.stat().st_mtime > 120:
                    lock.unlink(missing_ok=True)
                time.sleep(.05)
        raise PaperError('PAPER_REGISTRY_BUSY')

    def _unlock(self, fd):
        os.close(fd)
        (self.root / '.registry.lock').unlink(missing_ok=True)

    def path(self, entry):
        p = self.root / 'files' / (entry['sha256'] + '.pdf')
        if p.is_symlink() or not p.is_file():
            raise PaperError('PAPER_FILE_MISSING')
        return p

    # ------------------------------------------------------------------ import
    def receive_fd(self, fd, sha256):
        """Copy bytes from a launcher-provided descriptor into incoming/ (this user's directory) and check the SHA."""
        import re as _re
        if not _re.fullmatch(r'[0-9a-f]{64}', sha256 or ''):
            raise PaperError('UPLOAD_SHA256_REQUIRED')
        target = self.root / 'incoming' / ('fd-' + os.urandom(8).hex())
        h = hashlib.sha256()
        total = 0
        out = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0), 0o600)
        try:
            while block := os.read(fd, 1 << 20):
                total += len(block)
                if total > MAX_BYTES:
                    raise PaperError('PDF_TOO_LARGE')
                h.update(block)
                os.write(out, block)
        finally:
            os.close(out)
            os.close(fd)
        if h.hexdigest() != sha256:
            target.unlink(missing_ok=True)
            raise PaperError('UPLOAD_INCOMPLETE_OR_CHANGED')
        return target

    def import_pdf(self, incoming, original_name, *, source='upload'):
        """Validate an incoming file (already copied into incoming/ by the trusted launcher) and register it."""
        incoming = Path(incoming)
        if incoming.parent != self.root / 'incoming' or incoming.is_symlink():
            raise PaperError('INCOMING_PATH_DENIED')
        try:
            st = os.lstat(incoming)
            if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
                raise PaperError('INCOMING_NOT_REGULAR_FILE')
            if st.st_size == 0:
                raise PaperError('PDF_EMPTY')
            if st.st_size > MAX_BYTES:
                raise PaperError('PDF_TOO_LARGE')
            with open(incoming, 'rb') as fh:
                head = fh.read(1024)
            if b'%PDF-' not in head[:1024]:
                raise PaperError('NOT_A_PDF')
            meta = pdf_metadata(incoming)
            if meta['encrypted']:
                raise PaperError('PDF_ENCRYPTED')
            if not meta['pages'] or meta['pages'] > MAX_PAGES:
                raise PaperError('PDF_PAGE_COUNT')
            sha = _digest(incoming)
            fd = self._lock()
            try:
                rows = self.entries()
                same = next((r for r in rows if r['sha256'] == sha), None)
                if same:
                    # the same bytes uploaded again are what the user "just uploaded" (stored once; first upload time kept)
                    same['last_uploaded_at'] = _now()
                    self._save(rows)
                    return dict(same, duplicate=True)
                if len(rows) >= MAX_PAPERS or sum(r['bytes'] for r in rows) + st.st_size > MAX_TOTAL_BYTES:
                    raise PaperError('PAPER_QUOTA_EXCEEDED')
                name = safe_name(original_name)
                version = 1 + sum(r['name'] == name for r in rows)
                target = self.root / 'files' / (sha + '.pdf')
                os.replace(incoming, target)
                os.chmod(target, 0o600)
                entry = dict(paper_id=sha[:12], sha256=sha, name=name, version=version, title=meta['title'], heading=meta['heading'], pages=meta['pages'],
                             bytes=st.st_size, uploaded_at=_now(), source=source, status='REGISTERED')
                rows.append(entry)
                self._save(rows)
                return dict(entry, duplicate=False)
            finally:
                self._unlock(fd)
        finally:
            if incoming.exists() and not incoming.is_symlink():
                incoming.unlink()

    # ------------------------------------------------------------------ discovery
    def touch(self, sha256):
        """Record that a research turn used this paper ('继续刚刚中断的论文研究' resolves to the latest one)."""
        fd = self._lock()
        try:
            rows = self.entries()
            for r in rows:
                if r['sha256'] == sha256:
                    r['last_research_at'] = time.time()
            self._save(rows)
        finally:
            self._unlock(fd)

    def _complete_metadata(self):
        """Entries registered before page-one headings existed get them once (local PDF read, no model)."""
        rows = self.entries()
        if all('heading' in r for r in rows):
            return rows
        fd = self._lock()
        try:
            rows = self.entries()
            for r in rows:
                if 'heading' not in r:
                    meta = pdf_metadata(self.path(r))
                    r.update(title=meta['title'], heading=meta['heading'])
            self._save(rows)
        finally:
            self._unlock(fd)
        return rows

    def resolve(self, query=''):
        """'' / 'latest' / 最近 → newest; else name/title/author/sha-prefix match. Returns dict(status, paper|candidates)."""
        rows = sorted(self._complete_metadata(), key=lambda r: r.get('last_uploaded_at') or r['uploaded_at'])
        if not rows:
            return dict(status='NO_PAPERS', candidates=[])
        q = unicodedata.normalize('NFC', (query or '').strip().lower())
        if q in ('', 'latest', 'last', 'newest') or re.search(r'刚(刚)?上传|最近上传|最新上传|最新的|最后上传', q):
            return dict(status='FOUND', paper=rows[-1], basis='most recent upload')
        studied = [r for r in rows if r.get('last_research_at')]
        if studied and re.search(r'继续|中断|刚才|刚刚(研究|那篇|的论文)|上一篇|resume|continue', q):
            return dict(status='FOUND', paper=max(studied, key=lambda r: r['last_research_at']), basis='most recently researched')
        if re.fullmatch(r'[0-9a-f]{6,64}', q):
            hits = [r for r in rows if r['sha256'].startswith(q)]
        else:
            stop = {'论文', '那篇', '这篇', '研究', '读取', '上传', '我的', '我刚', '提取', '因子', '一篇', '文章', 'the', 'and', 'paper', 'pdf'}
            q = re.sub(r'(那篇|这篇|论文|研究|读取|继续|一下|里面的|的)', ' ', q)
            tokens = [t for t in re.findall(r'[a-z0-9#]{3,}|[一-鿿]{2,}', q) if t not in stop]
            text = lambda r: (r['name'] + ' ' + r.get('title', '') + ' ' + r.get('heading', '')).lower()
            hits = [r for r in rows if tokens and all(t in text(r) for t in tokens)]
            # a Latin/number identifier the user typed (AQR, CN03, 0212641, 1110.3383) that names exactly one file decides,
            # before shared topic words ("趋势跟踪" in another report's title) can make it ambiguous (live H1)
            ident = [t for t in tokens if re.fullmatch(r'[a-z0-9#]+', t) and not t.isdigit() or re.fullmatch(r'\d{4,}', t)]
            named_by = {id(r): r for t in ident for r in rows if t in r['name'].lower()}
            if not hits and len(named_by) == 1:
                return dict(status='FOUND', paper=next(iter(named_by.values())), basis='distinctive identifier in the file name')
            # an identifier as the user typed it -- an acronym in capitals (AQR, MACD) or a code with digits (CN03, 0212641) --
            # that names exactly one file decides even when ordinary words ("trend following") also match other files
            # (live J3: "AQR趋势跟踪论文（time series momentum / trend following）" was located as the xiangcai report)
            raw_ids = {t.lower() for t in re.findall(r'(?<![A-Za-z0-9])([A-Z]{2,6}|[A-Za-z]*\d[A-Za-z0-9.]*)(?![A-Za-z0-9])', query or '')
                       if len(t) >= 3 or re.search(r'\d', t)}
            owners = {t: [r for r in rows if t in r['name'].lower()] for t in raw_ids}
            decisive = {id(v[0]): v[0] for v in owners.values() if len(v) == 1}
            if not hits and len(decisive) == 1:
                return dict(status='FOUND', paper=next(iter(decisive.values())), basis='identifier typed by the user names one file')
            if not hits and tokens:              # partial match: only the papers matching the most query words
                # a word in the file name or title counts twice a word that only appears in the page-one text
                # (live Q4: "moving average" is the MA paper's title but only body text of the MACD paper).
                # A Chinese sentence is one long run ("华泰那份量化月报里"): its two-character pieces are scored instead
                # (A/B: "研究华泰那份量化月报里的因子" and "长城证券技术指标叠加" were NOT_FOUND).
                filler = {'那份', '份量', '这份', '报里', '里的', '的因', '因子', '研究', '论文', '那篇', '一篇', '文章', '中的', '里面'}
                terms = [t for t in tokens if not re.fullmatch(r'[一-鿿]+', t)] + sorted(
                    {t[i:i + 2] for t in tokens if re.fullmatch(r'[一-鿿]+', t) for i in range(len(t) - 1)} - filler)
                named = lambda r: (r['name'] + ' ' + r.get('title', '')).lower()
                score = {id(r): sum(2 if t in named(r) else 1 if t in text(r) else 0 for t in terms) for r in rows}
                best = max(score.values())
                hits = [r for r in rows if best and score[id(r)] == best]
        if len(hits) == 1:
            return dict(status='FOUND', paper=hits[0], basis='name/title match')
        if not hits:
            return dict(status='NOT_FOUND', candidates=[self.public(r) for r in rows[-8:]])
        return dict(status='AMBIGUOUS', candidates=[self.public(r) for r in hits[-8:]])

    @staticmethod
    def public(r):
        return {k: r[k] for k in ('name', 'version', 'title', 'pages', 'uploaded_at', 'status', 'last_uploaded_at') if k in r}
