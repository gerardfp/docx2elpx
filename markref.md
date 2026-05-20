---
titulo: Referencia de Sintaxis Markdown para md2elpx
subtitulo: Guía completa de elementos soportados por VSCode y la sintaxis exemark
idioma: Valencià
autoria: Gerard
licencia: Creative Commons Attribution-ShareAlike 4.0
descripción: Este fichero sirve como caso de prueba y referencia para todas las opciones de sintaxis Markdown estándar de VSCode y los componentes exemark que se traducen a eXeLearning (elpx).
---

# # Portada

Este es el contenido de la página principal (Portada). En esta página podemos incluir una introducción al recurso educativo.
Como las páginas de navegación se definen con doble almohadilla (`# #`), los siguientes encabezados son simplemente títulos visuales de nivel 2 y 3 dentro de esta misma página.

## Elementos Básicos de Formato

En esta sección probaremos las capacidades de formato de texto estándar soportadas por la vista previa de VSCode:

*   **Texto en negrita** (usando `**negrita**` o `__negrita__`).
*   *Texto en cursiva* (usando `*cursiva*` o `_cursiva*`).
*   ***Texto en negrita y cursiva*** (usando `***negrita y cursiva***`).
*   ~~Texto tachado~~ (usando `~~tachado~~`).
*   Código en línea: `const x = 42;` (usando `` `código` ``).
*   Subíndice usando HTML: H<sub>2</sub>O.
*   Superíndice usando HTML: E = mc<sup>2</sup>.

---
titulo: dfghjk
gtygy:  gfdggd
---

# # Página de Bloques y Estructura

En esta página se ejemplifica la división en subpáginas y bloques (iDevices) utilizando la sintaxis de doble almohadilla para la navegación y el símbolo mayor que `>` para los bloques.

## ## Subpágina de Prueba

Al usar `## ##` se crea una subpágina en la jerarquía del eXeLearning.

### ### Subsubpágina de Prueba

Al usar `### ###` se crea una subsubpágina (nivel 3) en la jerarquía.

> Bloque de Texto Estándar
{hora: 0:30}
{individual: 1}

Este es el contenido de un bloque de texto (iDevice) con metadatos específicos como tiempo estimado y modo de trabajo individual. 
Se inicia con el carácter `>` seguido del título del bloque.

Los metadatos se definen opcionalmente en la línea inmediatamente posterior:
*   `{hora: HH:MM}`
*   `{individual: N}` (o cualquier etiqueta de participantes).

> Bloque de Lectura y Citas

Aquí probamos otro iDevice de texto. Recuerda que, para escribir una cita en formato blockquote estándar de markdown dentro de un bloque, puedes simplemente indentarla o usar citas estándar dentro del contenido.

> "El diseño web moderno no se trata solo de la estética, sino de la experiencia de usuario y la accesibilidad de los contenidos digitales."
> — *Anónimo*

---

# # Listas, Tablas y Código

> Listas y Tareas

A continuación se muestran ejemplos de listas anidadas y listas de tareas, muy útiles para guías de aprendizaje.

## Lista no ordenada
*   Elemento principal 1
    *   Subelemento 1.1
    *   Subelemento 1.2
*   Elemento principal 2
    *   Subelemento 2.1

## Lista ordenada
1.  Paso número uno
2.  Paso número dos
    1.  Subpaso A
    2.  Subpaso B
3.  Paso número tres

## Lista de Tareas (Task Lists)
- [x] Tarea completada con éxito
- [ ] Tarea pendiente de revisión
- [ ] Tarea no iniciada

> Tablas y Datos

Las tablas de Markdown se renderizan perfectamente en HTML interactivo:

| Curso | Asignatura | Alumnos | Estado |
| :--- | :---: | ---: | :---: |
| 1º ESO | Lengua Castellana | 25 | 🟢 Activo |
| 2º ESO | Matemáticas | 22 | 🟡 En espera |
| 3º ESO | Física y Química | 18 | 🔴 Cerrado |

> Bloques de Código de Programación

Para cursos técnicos, los bloques de código con coloreado de sintaxis son indispensables:

```python
def saludo(nombre):
    """Función de prueba para md2elpx"""
    mensaje = f"¡Hola, {nombre}! Bienvenido a eXeLearning."
    print(mensaje)
    return mensaje
```

Y código HTML:

```html
<div class="alert alert-info">
    <strong>Info!</strong> Este es un aviso importante.
</div>
```

---

# # Contenido Multimedia y Recursos

> Enlaces y Vídeos

Los enlaces a recursos externos y archivos locales son esenciales:

*   **Enlace Externo**: [Ir a la web de VSCode](https://code.visualstudio.com)
*   **Enlace a Archivo Local**: [Descargar Guía PDF (Thisisapdf.pdf)](Thisisapdf.pdf) (Este archivo se copiará automáticamente al recurso del bloque).
*   **Vídeo de YouTube**: [Vídeo de Introducción a Markdown](https://www.youtube.com/watch?v=dQw4w9WgXcQ) (Se convertirá en un reproductor de vídeo interactivo integrado).

> Imágenes y Figuras con Metadatos

Aquí probamos la inserción de imágenes con diferentes opciones de visualización.

## Imagen con efecto Lightbox
Para activar la ampliación tipo Lightbox, colocamos la imagen dentro del contenedor `:::lightbox`:

:::lightbox
![Logotipo de VSCode](https://code.visualstudio.com/assets/images/code-lg.png)
:::

## Figura Educativa con Metadatos Completos
Justo después de la imagen, añadimos el bloque de metadatos tipo front matter delimitado por `---` para generar una figura eXeLearning con autoría, pie de foto y dimensiones adaptadas:

![Educación del Futuro](https://images.unsplash.com/photo-1516321318423-f06f85e504b3)
---
titulo: Tecnología y Educación en el Aula [https://unsplash.com/photos/technology-in-education]
autor: Unsplash Contributor [https://unsplash.com/@unsplash]
alt: Estudiantes utilizando computadoras portátiles en un aula interactiva moderna
pie: Imagen demostrativa de aprendizaje híbrido [https://creativecommons.org]
ancho: 700
alto: 450
---

---

# # Componentes Interactivos (FX)

En esta página se agrupan los efectos dinámicos de eXeLearning, útiles para organizar el contenido y evitar páginas excesivamente largas.

> Acordeón Dinámico

El acordeón colapsa y expande las secciones cuando el usuario hace clic. Se abre con `:::acordeon` y se cierra con `:::`.

:::acordeon
>> Reto 1: Descubrimiento de Markdown
Este es el contenido correspondiente al primer bloque colapsable. Aquí el alumno debe explorar la sintaxis básica.

>> Misión 2: Creación de Contenido
Este es el contenido correspondiente al segundo bloque colapsable. Se pueden incluir listas, código u otros formatos aquí.
:::

> Pestañas Horizontales

Las pestañas permiten alternar contenidos de forma fluida. Se abre con `:::pestañas` y se cierra con `:::`.

:::pestañas
>> Pestaña A: Teoría
El markdown es un lenguaje de marcado ligero creado por John Gruber en 2004 que busca la máxima legibilidad y facilidad de publicación tanto en sus formas de entrada como de salida.

>> Pestaña B: Práctica
Prueba a escribir `# Hola Mundo` en un archivo con extensión `.md` y ábrelo con VSCode para ver la vista previa.
:::

> Paginación e Imágenes Dinámicas

Las opciones de carrusel y paginación añaden controles de anterior/siguiente. Se abre con `:::carrusel` y se cierra con `:::`.

:::carrusel
>> Diapositiva 1
Contenido de la primera diapositiva del carrusel.

>> Diapositiva 2
Contenido de la segunda diapositiva del carrusel.
:::

---

# # Fórmulas Matemáticas y Emojis

> Notación Matemática y Emojis

VSCode admite renderizar expresiones matemáticas utilizando KaTeX. Nuestro compilador `md2elpx` también las integrará adecuadamente:

*   **Fórmula en línea**: La famosa ecuación de Einstein es $E = mc^2$.
*   **Fórmula en bloque**:

$$x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}$$

Y el uso directo de caracteres Unicode y Emojis para enriquecer el diseño visual:
*   Atención y Alertas: 🚀, ⚠️, 💡, 🧠, 🎯, 🔥.
*   Indicadores de estado: ✅, ❌, 🟡, 🟢, 🔴.