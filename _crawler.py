"""Crawler completo de territoriohuanca.com - descarga todas las paginas y assets."""
import os, re, time, json
from urllib.parse import urljoin, urlsplit, urlunsplit, unquote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from collections import deque

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
os.makedirs(ASSETS_DIR, exist_ok=True)

ROOT_URL = "https://www.territoriohuanca.com/"
ROOT_HOST = urlsplit(ROOT_URL).netloc
SITEMAP_URLS = [
    "https://www.territoriohuanca.com/page-sitemap.xml",
    "https://www.territoriohuanca.com/post-sitemap.xml",
    "https://www.territoriohuanca.com/blog-sitemap.xml",
    "https://www.territoriohuanca.com/p-nacional-sitemap.xml",
    "https://www.territoriohuanca.com/p-internacional-sitemap.xml",
]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
MAX_PAGES = 100
MAX_ASSET_BYTES = 100 * 1024 * 1024
TIMEOUT = 25
DELAY = 0.15

LINK_PAT = re.compile(r'<link\b[^>]*\bhref=["\']([^"\']+)["\'][^>]*>', re.I)
SCRIPT_PAT = re.compile(r'<script\b[^>]*\bsrc=["\']([^"\']+)["\'][^>]*>', re.I)
IMG_PAT = re.compile(r'<img\b[^>]*\bsrc=["\']([^"\']+)["\'][^>]*>', re.I)
IMG_SRCSET_PAT = re.compile(r'\bsrcset=["\']([^"\']+)["\']', re.I)
ANCHOR_PAT = re.compile(r'<a\b[^>]*\bhref=["\']([^"\']+)["\'][^>]*>', re.I)
STYLE_BLOCK_PAT = re.compile(r'<style\b[^>]*>(.*?)</style>', re.I | re.S)
URL_FUNC_PAT = re.compile(r'url\((?:["\']?)([^)"\']+)(?:["\']?)\)', re.I)
LOC_PAT = re.compile(r'<loc>([^<]+)</loc>', re.I)


def fetch(url, as_text=True):
    req = Request(url, headers={"User-Agent": UA, "Referer": ROOT_URL})
    with urlopen(req, timeout=TIMEOUT) as r:
        data = r.read()
        ct = (r.headers.get("Content-Type") or "").split(";")[0].strip()
        if as_text:
            charset = "utf-8"
            m = re.search(r"charset=([^\s;]+)", r.headers.get("Content-Type", ""), re.I)
            if m:
                charset = m.group(1)
            try:
                return data.decode(charset, errors="replace"), ct
            except Exception:
                return data.decode("utf-8", errors="replace"), ct
        return data, ct


def normalize_url(u, base):
    if not u:
        return None
    u = u.strip()
    lu = u.lower()
    if lu.startswith(("mailto:", "tel:", "javascript:", "data:", "#")):
        return None
    abs_ = urljoin(base, u)
    s = urlsplit(abs_)
    if s.scheme not in ("http", "https"):
        return None
    if s.netloc != ROOT_HOST:
        return None
    s = s._replace(fragment="")
    path = s.path or "/"
    return urlunsplit(s._replace(path=path))


def page_filename(url):
    s = urlsplit(url)
    path = unquote(s.path or "/")
    if path in ("/", ""):
        base = "index"
        if s.query:
            base = "q__" + re.sub(r"[^A-Za-z0-9._-]", "_", s.query)[:80]
    else:
        p = path.strip("/")
        p = re.sub(r"/?(index\.(html?|php))$", "", p, flags=re.I)
        p = p.replace("/", "__")
        if s.query:
            p = p + "__q-" + re.sub(r"[^A-Za-z0-9._-]", "_", s.query)[:60]
        base = re.sub(r"[^A-Za-z0-9._-]", "_", p) or "index"
    return base + ".html"


def asset_filename(url, tipo):
    s = urlsplit(url)
    base = (unquote(s.path).split("/")[-1] or "archivo").split("?")[0]
    if "." not in base:
        ext = {"css": ".css", "js": ".js", "font": ".bin", "img": ".bin"}.get(tipo, ".bin")
        base = base + ext
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    return base


def extract_assets(html, page_url):
    found = []
    for m in LINK_PAT.finditer(html):
        tag = m.group(0)
        rel = m.group(1)
        is_stylesheet = bool(re.search(r'rel\s*=\s*["\']?stylesheet', tag, re.I))
        is_preload_asset = bool(re.search(r"\.(woff2?|ttf|otf|eot|png|jpe?g|svg|webp|gif|ico|css)(?:\?|#|$)", rel, re.I))
        if not (is_stylesheet or is_preload_asset):
            continue
        if rel.lower().startswith(("data:", "javascript:")):
            continue
        absu = urljoin(page_url, rel)
        if re.search(r"\.css(?:\?|#|$)", rel, re.I) or is_stylesheet:
            t = "css"
        elif re.search(r"\.(woff2?|ttf|otf|eot)(?:\?|#|$)", rel, re.I):
            t = "font"
        else:
            t = "img"
        found.append((absu, rel, t))
    for m in SCRIPT_PAT.finditer(html):
        rel = m.group(1)
        if rel.lower().startswith(("data:", "javascript:")):
            continue
        found.append((urljoin(page_url, rel), rel, "js"))
    for m in IMG_PAT.finditer(html):
        rel = m.group(1)
        if rel.lower().startswith("data:"):
            continue
        found.append((urljoin(page_url, rel), rel, "img"))
    for m in IMG_SRCSET_PAT.finditer(html):
        srcset = m.group(1)
        for part in srcset.split(","):
            url_part = part.strip().split(" ")[0].strip()
            if url_part and not url_part.lower().startswith("data:"):
                found.append((urljoin(page_url, url_part), url_part, "img"))
    for sb in STYLE_BLOCK_PAT.findall(html):
        for u in URL_FUNC_PAT.findall(sb):
            if u.lower().startswith("data:"):
                continue
            absu = urljoin(page_url, u)
            ext = os.path.splitext(urlsplit(absu).path)[1].lower()
            if ext in (".woff", ".woff2", ".ttf", ".otf", ".eot"):
                t = "font"
            elif ext == ".css":
                t = "css"
            elif ext == ".js":
                t = "js"
            else:
                t = "img"
            found.append((absu, u, t))
    for m in re.finditer(r'style=["\']([^"\']+)["\']', html, re.I):
        for u in URL_FUNC_PAT.findall(m.group(1)):
            if u.lower().startswith("data:"):
                continue
            found.append((urljoin(page_url, u), u, "img"))
    return found


def extract_links(html, page_url):
    out = []
    for m in ANCHOR_PAT.finditer(html):
        href = m.group(1)
        n = normalize_url(href, page_url)
        if n:
            out.append((href, n))
    return out


def discover_from_sitemaps():
    seeds = [ROOT_URL]
    for sm in SITEMAP_URLS:
        try:
            xml, _ = fetch(sm, as_text=True)
            for m in LOC_PAT.finditer(xml):
                u = m.group(1).strip()
                n = normalize_url(u, sm)
                if n and n not in seeds:
                    seeds.append(n)
        except Exception as e:
            print(f"  ! sitemap {sm}: {e}")
    return seeds


print(f"== Descubriendo URLs desde sitemaps ==")
seeds = discover_from_sitemaps()
print(f"   Seed URLs: {len(seeds)}")

visited_pages = {}
queue = deque()
for s in seeds:
    if s not in visited_pages:
        visited_pages[s] = page_filename(s)
        queue.append(s)

page_html = {}
errors_pages = []

print(f"== Crawl BFS (cap {MAX_PAGES}) ==")
while queue and len(page_html) < MAX_PAGES:
    url = queue.popleft()
    try:
        path = urlsplit(url).path or "/"
        ext = os.path.splitext(path)[1].lower()
        if ext and ext not in (".html", ".htm", ".php", ".aspx", ".jsp"):
            continue
        html, ct = fetch(url, as_text=True)
        if ct and "html" not in ct.lower():
            continue
        page_html[url] = html
        print(f"  [{len(page_html):3d}] {visited_pages[url]:55s} <- {url}")
        for raw, nu in extract_links(html, url):
            if nu not in visited_pages and len(visited_pages) < MAX_PAGES:
                fn = page_filename(nu)
                base, ex = os.path.splitext(fn)
                k = 1
                while fn in visited_pages.values():
                    fn = f"{base}-{k}{ex}"
                    k += 1
                visited_pages[nu] = fn
                queue.append(nu)
        time.sleep(DELAY)
    except HTTPError as e:
        errors_pages.append((url, f"HTTP {e.code}"))
        print(f"  ! {url} -> HTTP {e.code}")
    except URLError as e:
        errors_pages.append((url, f"URLError {e.reason}"))
        print(f"  ! {url} -> URLError {e.reason}")
    except Exception as e:
        errors_pages.append((url, str(e)[:120]))
        print(f"  ! {url} -> {e}")

print(f"\n== Total paginas: descargadas={len(page_html)} descubiertas={len(visited_pages)} errores={len(errors_pages)} ==")

all_assets = {}
used_names = set(os.listdir(ASSETS_DIR))
page_asset_tokens = {}

for purl, html in page_html.items():
    tokens = []
    for absu, raw, tipo in extract_assets(html, purl):
        tokens.append((raw, absu))
        if absu not in all_assets:
            name = asset_filename(absu, tipo)
            final = name
            n = 1
            while final in used_names:
                b, e = os.path.splitext(name)
                final = f"{b}-{n}{e}"
                n += 1
            used_names.add(final)
            all_assets[absu] = (tipo, "assets/" + final)
    page_asset_tokens[purl] = tokens

print(f"== Assets unicos detectados: {len(all_assets)} ==")

total_bytes = 0
asset_errors = []
downloaded = 0
skipped_existing = 0
for absu, (tipo, local_rel) in all_assets.items():
    out_path = os.path.join(BASE_DIR, local_rel.replace("/", os.sep))
    if os.path.exists(out_path):
        skipped_existing += 1
        continue
    try:
        data, ct = fetch(absu, as_text=False)
        if total_bytes + len(data) > MAX_ASSET_BYTES:
            asset_errors.append((absu, "limite total excedido"))
            continue
        total_bytes += len(data)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(data)
        downloaded += 1
        time.sleep(0.05)
    except HTTPError as e:
        asset_errors.append((absu, f"HTTP {e.code}"))
    except Exception as e:
        asset_errors.append((absu, str(e)[:120]))

print(f"== Assets: nuevos={downloaded} reusados={skipped_existing} errores={len(asset_errors)} bytes_nuevos={total_bytes} ==")


def rewrite(html, page_url):
    out = html
    for raw_href, nu in extract_links(html, page_url):
        if nu in visited_pages and nu in page_html:
            target = visited_pages[nu]
            for q in ('"', "'"):
                out = out.replace(f'href={q}{raw_href}{q}', f'href={q}{target}{q}')
    for raw_tok, absu in page_asset_tokens.get(page_url, []):
        if absu in all_assets:
            local = all_assets[absu][1]
            for tok in {raw_tok, absu}:
                if not tok:
                    continue
                for q in ('"', "'"):
                    out = out.replace(q + tok + q, q + local + q)

    def repl_url(m):
        raw = m.group(1)
        absu = urljoin(page_url, raw)
        if absu in all_assets:
            return f"url({all_assets[absu][1]})"
        return m.group(0)

    out = URL_FUNC_PAT.sub(repl_url, out)

    def repl_srcset(m):
        srcset = m.group(1)
        new_parts = []
        for part in srcset.split(","):
            tk = part.strip()
            if not tk:
                continue
            bits = tk.split(" ", 1)
            u = bits[0]
            rest = (" " + bits[1]) if len(bits) > 1 else ""
            absu = urljoin(page_url, u)
            if absu in all_assets:
                u = all_assets[absu][1]
            new_parts.append(u + rest)
        return 'srcset="' + ", ".join(new_parts) + '"'

    out = IMG_SRCSET_PAT.sub(repl_srcset, out)
    return out


written = 0
for purl, html in page_html.items():
    fn = visited_pages[purl]
    final = rewrite(html, purl)
    with open(os.path.join(BASE_DIR, fn), "w", encoding="utf-8") as f:
        f.write(final)
    written += 1

print(f"== HTMLs reescritos y guardados: {written} ==")

manifest = {
    "urlOrigen": ROOT_URL,
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "paginas": [{"url": u, "archivo": visited_pages[u]} for u in page_html.keys()],
    "totalPaginas": len(page_html),
    "totalAssets": len(all_assets),
    "assetsDescargadosAhora": downloaded,
    "assetsReutilizados": skipped_existing,
    "erroresPaginas": [{"url": u, "error": e} for u, e in errors_pages],
    "erroresAssets": [{"url": u, "error": e} for u, e in asset_errors],
}
with open(os.path.join(BASE_DIR, "clon-manifest.json"), "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)

print(f"\n== Done. Output: {BASE_DIR} ==")
if asset_errors:
    print("Errores assets (primeros 10):")
    for u, e in asset_errors[:10]:
        print(f"  - {u[:90]} => {e}")
if errors_pages:
    print("Errores paginas (primeros 10):")
    for u, e in errors_pages[:10]:
        print(f"  - {u} => {e}")
