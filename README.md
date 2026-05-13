# Tutorial

## Metadatos
```
{titulo: Este sería el título principal en los metadatos}
{subtitulo: Este sería el subtítulo principal en los metadatos}
{idioma: Valencià}
{autoria: Esta sería la autoría principal en los metadatos}
{licencia: public domain}
{descripción: Esta sería la descripción principal .
En los metadatos}
```

## Elementos

* Páginas / subpáginas
```
# Titulo de la página

Contenido

## Titulo de la subpágina

Contenido

### Titulo de la subsubpágina

Contenido
```

* Idevice Text
```
% bloque de texto
{hora: 1:00}
{individual: 3}

Contenido
```

* Lightbox
```
{lightbox}

Imagen
```

* Acordeón, Pestañas, Paginación, Carrusel

cambia {acordeon} per {pestañas}, {paginación} o {carrusel}

```
{acordeon}
>> Titulo 1 del acordeón
Contenido 1 del acordeón
>> Titulo 2 del acordeón
Contenido 2 del acordeón
{fin}
```

* Enlaces a documentos y multimedia

```
* Documentos: Inserta un enlace en Word (Ctrl+K) y escribe el nombre del archivo (ej. archivo.pdf) como destino. El archivo debe estar en la misma carpeta que el .docx.
* YouTube: Inserta un enlace a un vídeo de YouTube y se convertirá automáticamente en un reproductor incrustado.
```

* Figura con metadatos

Justo a continuación de la imagen se puede incluir el bloque de metadatos con el siguiente formato:

```text
{
   titulo: Título de la imagen [https://enlace.opcional.al.documento]
   autor: Autor de la imagen [https://enlace.al.autor]
   alt: Descripción alternativa (accesibilidad)
   pie: Texto del pie [https://enlace.del.pie]
   ancho: 1280
   alto: 720
}
```
*Nota: La licencia se establece automáticamente como CC BY.*
Todos los campos son opcionales.
Los enlaces dentro de "titulo", "autor" y "pie" también son opcionales: `Texto [URL]`.

# Dev
## Generación de ODE (Objeto Digital Educativo) 
```
Objeto Digital Educativo
└── páginas
└── actividades (iDevices)
└── recursos multimedia
└── metadatos
```

# Estructura HTML

```
<main class="page">
  <article class="box">
    <div class="box-content">
      <div class="idevice_node">
        "IDEVICE CONTENT"
      </div>
    </div>
  </article>
</main>
```


## build dist

    uv run pyinstaller doc2elpx.spec