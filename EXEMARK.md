# Referencia de Sintaxis: Exemark (doc2elpx / md2elpx)

**Exemark** es el lenguaje de marcado ligero adaptado en este proyecto para crear contenidos educativos interactivos y exportarlos directamente a **eXeLearning (ELPX)**.

Dependiendo de si utilizas ficheros Markdown (`.md`) compilados con `md2elpx.py` o documentos de Microsoft Word (`.docx`) compilados con `docx2elpx.py`, el sistema soporta dos variantes de sintaxis optimizadas para cada entorno:

---

## 1. Variante Markdown (`.md` / `md2elpx`)
Esta sintaxis está pensada para ser escrita en editores de código como VSCode, aprovechando elementos nativos de Markdown.

### 📋 Metadatos del Documento (YAML Front Matter)
Se definen al principio del archivo mediante un bloque delimitado por tres guiones `---`.
```markdown
---
titulo: Introducción a la Programación
subtitulo: Conceptos básicos con Python
idioma: Valencià
autoria: Gerard
licencia: Creative Commons Attribution-ShareAlike 4.0
descripcion: Un recurso educativo abierto para iniciarse en la programación estructurada.
---
```
*(Nota: El idioma se puede escribir en formato largo y se mapeará a su correspondiente código ISO, ej. Valencià/Valenciano -> `va`, Castellano/Español -> `es`, English/Inglés -> `en`)*

### 🌳 Páginas y Estructura de Navegación
Para estructurar el árbol de páginas de eXeLearning, se utiliza la doble almohadilla (`# #`). Esto evita interferir con los títulos visuales estándar de un solo símbolo (`#` o `##`).
```markdown
# # Portada
Esta es la página de inicio del recurso.

## ## Unidad 1: Primeros Pasos
Esta es una subpágina (Nivel 2) en la jerarquía.

### ### 1.1 Variables y Tipos
Esta es una subsubpágina (Nivel 3) en la jerarquía.
```

### 📦 Bloques de Contenido (iDevices)
Los bloques o iDevices de texto se inician con el símbolo de mayor que (`>`) seguido de su título. Opcionalmente, se pueden configurar metadatos de tiempo estimado o participantes en las líneas inmediatamente siguientes usando llaves `{}`.
```markdown
> Reto 1: Descubrimiento de variables
{hora: 0:30}
{individual: 1}

En este bloque de contenido el alumno aprenderá a declarar variables.
```

### ⚡ Componentes Interactivos (Efectos FX)
Permiten crear contenidos colapsables, pestañas o carruseles para organizar la información visualmente. Se abren con `:::<tipo>` y se cierran con `:::`. Cada sección interna se declara con `>>`.

*   **Acordeón Dinámico (`:::acordeon`):**
    ```markdown
    :::acordeon
    >> Sección 1: Teoría
    Contenido teórico del primer bloque.
    
    >> Sección 2: Práctica
    Contenido práctico del segundo bloque.
    :::
    ```
*   **Pestañas Horizontales (`:::pestañas`):**
    ```markdown
    :::pestañas
    >> Teoría de Variables
    Explicación detallada...
    
    >> Código de Ejemplo
    ```python
    x = 10
    ```
    :::
    ```
*   **Carrusel de Diapositivas (`:::carrusel`):**
    ```markdown
    :::carrusel
    >> Diapositiva 1
    Primer bloque de contenido interactivo.
    
    >> Diapositiva 2
    Segundo bloque de contenido interactivo.
    :::
    ```
*   **Paginación (`:::paginación`):** Funciona igual que el carrusel pero con controles de avance y retroceso clásico.

### 🔍 Efecto Lightbox (Ampliación de Imágenes)
Permite al usuario hacer clic en una imagen para verla en pantalla completa de forma elegante. Se envuelve la imagen en un bloque `:::lightbox`.
```markdown
:::lightbox
![Logotipo de VSCode](https://code.visualstudio.com/assets/images/code-lg.png)
:::
```

### 🖼️ Figuras con Metadatos Completos
Permite añadir autoría, licencia y dimensiones exactas a una imagen. Se coloca un bloque de metadatos tipo front-matter inmediatamente debajo de la imagen estándar:
```markdown
![Tecnología en el Aula](https://images.unsplash.com/photo-1516321318423-f06f85e504b3)
---
titulo: Tecnología y Educación en el Aula [https://unsplash.com/photos/technology-in-education]
autor: Unsplash Contributor [https://unsplash.com/@unsplash]
alt: Estudiantes utilizando computadoras portátiles en un aula interactiva moderna
pie: Imagen demostrativa de aprendizaje híbrido [https://creativecommons.org]
ancho: 700
alto: 450
---
```

---

## 2. Variante Word / DOCX (`.docx` / `docx2elpx`)
Esta sintaxis está optimizada para ser redactada cómodamente en Microsoft Word (`.docx`). Evita el uso de formatos Markdown complejos y utiliza marcas basadas en llaves y caracteres sencillos.

### 📋 Metadatos del Documento
Se declaran al principio del documento de texto en Word usando llaves:
```text
{titulo: Mi Recurso Educativo Abierto}
{subtitulo: Creado desde un documento Word}
{idioma: Castellano}
{autoria: Nombre del Autor}
{licencia: creative commons: attribution - share alike 4.0}
{descripción: Descripción del recurso educativo en varias líneas.}
```

### 🌳 Páginas y Estructura de Navegación
Se utiliza el número de almohadillas simples (`#`) para determinar el nivel jerárquico de las páginas:
```text
# Portada de mi recurso
Introducción...

## Subpágina de nivel 2
Contenido...

### Subpágina de nivel 3
Contenido...
```

### 📦 Bloques de Contenido (iDevices)
Se inician con el símbolo de porcentaje (`%`) seguido del título del bloque. Al igual que en la variante Markdown, los metadatos van debajo entre llaves `{}`:
```text
% Bloque Práctico: Desafío de Código
{hora: 1:00}
{individual: 3}

Desarrolla una solución en Python para el siguiente problema...
```

### ⚡ Componentes Interactivos (Efectos FX)
Se inician con `{acordeon}`, `{pestañas}`, `{paginación}` o `{carrusel}`, cada pestaña o sección con `>>`, y se cierran con `{fin}`:
```text
{acordeon}
>> Reto 1: Descubrimiento
Este es el contenido correspondiente al primer bloque colapsable.

>> Misión 2: Creación
Contenido del segundo bloque colapsable.
{fin}
```

### 🔍 Efecto Lightbox
Se activa escribiendo `{lightbox}` justo antes de la imagen insertada en el documento de Word:
```text
{lightbox}
[Aquí se inserta la imagen directamente en Word]
```

### 🖼️ Figuras con Metadatos
Se insertan metadatos estructurados en llaves `{}` inmediatamente después de la imagen en Word:
```text
[Aquí se inserta la imagen directamente en Word]
{
   titulo: Título de la imagen [https://enlace.opcional.al.documento]
   autor: Autor de la imagen [https://enlace.al.autor]
   alt: Descripción alternativa (accesibilidad)
   pie: Texto del pie [https://enlace.del.pie]
   ancho: 1280
   alto: 720
}
```

---

## 3. Elementos Comunes (Soportados en ambas variantes)

### 🔗 Enlaces Locales, Descargas y YouTube
*   **Enlaces a archivos locales:** Si enlazas a un archivo local (ej. `[Descargar Guía PDF](Manual.pdf)`), el compilador copiará de forma automática el archivo `Manual.pdf` al directorio interno de recursos de eXeLearning y corregirá las rutas para que la descarga funcione en cualquier servidor.
*   **Vídeos de YouTube interactivos:** Si creas un enlace a un vídeo de YouTube (ej. `[Introducción a Markdown](https://www.youtube.com/watch?v=dQw4w9WgXcQ)`), el sistema lo convertirá automáticamente en un reproductor de vídeo incrustado e interactivo.

### 📝 Formato de Texto Estándar
Ambas variantes soportan el formateo de texto Markdown de toda la vida:
*   **Negrita:** `**texto**` o `__texto__`
*   *Cursiva:* `*texto*` o `_texto_`
*   ***Negrita y Cursiva:*** `***texto***`
*   ~~Tachado:~~ `~~texto~~`
*   Código en línea: `` `const x = 42;` ``
*   Subíndice HTML: `H<sub>2</sub>O` -> H<sub>2</sub>O
*   Superíndice HTML: `E = mc<sup>2</sup>` -> E = mc<sup>2</sup>

### 📊 Tablas de Datos
```markdown
| Curso | Asignatura | Alumnos | Estado |
| :--- | :---: | ---: | :---: |
| 1º ESO | Lengua Castellana | 25 | 🟢 Activo |
| 2º ESO | Matemáticas | 22 | 🟡 En espera |
```

### 💻 Bloques de Código de Programación
Soporta coloreado de sintaxis especificando el lenguaje:
```python
def saludo(nombre):
    mensaje = f"¡Hola, {nombre}! Bienvenido a eXeLearning."
    print(mensaje)
    return mensaje
```

### 📐 Fórmulas Matemáticas (KaTeX)
*   **En línea:** La famosa ecuación de Einstein es $E = mc^2$.
*   **En bloque:**
    $$x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}$$
