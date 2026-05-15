# territoriohuanca-clon

Clon estático local de [territoriohuanca.com](https://www.territoriohuanca.com/) (agencia de turismo en Huancayo, Perú), capturado con fines de estudio de diseño y referencia.

## Contenido

- **41 páginas HTML** descubiertas vía sitemap + crawl BFS (home, contacto, 13 tours, 4 blog, 9 destinos nacionales, 5 internacionales, etc.).
- **363 assets** locales en `assets/` (CSS, JS, imágenes, SVG, fuentes). Total ~22 MB.
- Navegación interna 100% local: enlaces y rutas de assets reescritos para funcionar sin servidor.

## Estructura

```
.
├── index.html                                  # Home
├── contactenos.html, territorio-huanca.html ... # Páginas institucionales
├── tour-huancayo__<slug>.html                  # 13 tours
├── blog__<slug>.html                           # Blog
├── q__p-nacional_<slug>.html                   # 9 destinos nacionales (con query params)
├── q__p-internacional_<slug>.html              # 5 internacionales
├── assets/                                     # CSS, JS, imágenes, fuentes
├── clon-manifest.json                          # Inventario: URLs originales → archivos locales, errores
└── _crawler.py                                 # Script reutilizable para re-clonar/actualizar
```

## Re-clonar / actualizar

El crawler es idempotente — re-usa assets ya descargados:

```bash
python _crawler.py
```

Usa solo stdlib de Python (3.8+). Lee 5 sub-sitemaps de Yoast SEO, hace BFS de enlaces internos, descarga páginas y assets, y reescribe rutas.

## Limitaciones conocidas

- **Tidio chat widget** devuelve 404 en producción — no clonado.
- **Google Fonts CDN, analytics y similares** siguen cargando desde la red (es comportamiento esperado en clones estáticos).
- **Contenido inyectado por JavaScript** en runtime no está pre-renderizado.
- Link interno `/tour-canon-de-shutjo/` (sin prefijo `tour-huancayo`) está roto también en el origen.

## Aviso

Este es un mirror estático con fines de estudio. Los derechos del diseño, copy e imágenes pertenecen a Territorio Huanca. No es un sitio oficial ni afiliado.
