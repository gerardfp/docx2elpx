# Generación de ODE (Objeto Digital Educativo) 
```
Objeto Digital Educativo
└── páginas
└── actividades (iDevices)
└── recursos multimedia
└── metadatos
```

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

# Elementos

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

```
{acordeon}
>> Titulo 1 del acordeón
Contenido 1 del acordeón
>> Titulo 2 del acordeón
Contenido 2 del acordeón
{fin}
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