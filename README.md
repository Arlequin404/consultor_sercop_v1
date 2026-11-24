# Consultor SERCOP

Aplicación local para consultar necesidades de contratación del SERCOP, filtrar resultados y revisar la información y los documentos de los procesos disponibles.

## Requisitos

- Windows.
- Python 3.10 o superior.
- Conexión a internet.
- Tkinter, incluido normalmente en la instalación de Python para Windows.

No se necesitan paquetes externos de Python.

## Instalación y ejecución

### Opción 1: iniciar con el archivo BAT

1. Descomprime el proyecto en una carpeta.
2. Abre la carpeta del proyecto.
3. Haz doble clic en `INICIAR.bat`.

La primera vez se creará automáticamente el entorno virtual `.venv`. En las siguientes ejecuciones se reutilizará.

### Opción 2: ejecutar desde PowerShell

Abre PowerShell y entra en la carpeta del proyecto. Por ejemplo:

```powershell
cd "C:\Users\Aalex\Desktop\consultor_sercop_v1"
```

Crea el entorno virtual:

```powershell
python -m venv .venv
```

Ejecuta la aplicación:

```powershell
.\.venv\Scripts\python.exe app.py
```

Para las siguientes ejecuciones no necesitas volver a crear el entorno. Solo entra en la carpeta y ejecuta:

```powershell
.\.venv\Scripts\python.exe app.py
```

Si `python` no se reconoce, instala Python desde [python.org](https://www.python.org/downloads/) y marca la opción **Add Python to PATH** durante la instalación. Después, cierra y vuelve a abrir PowerShell.

## Uso de la aplicación

### Consultar necesidades

1. Escribe una o varias palabras en el campo de búsqueda.
2. Selecciona el modo de búsqueda:
   - **Todas las palabras:** busca resultados que contengan todas las palabras.
   - **Cualquiera:** busca cualquiera de las frases separadas por comas.
   - **Frase exacta:** busca la frase completa.
3. Pulsa **Consultar SERCOP**.
4. Selecciona una fila para ver la descripción publicada.
5. Haz doble clic en una fila o pulsa **Ver detalle** para revisar más información.

Ejemplo para la opción **Cualquiera**:

```text
correo, google workspace, nube
```

### Filtros avanzados

Pulsa **Filtros avanzados** para mostrar u ocultar los filtros disponibles:

- Provincia o cantón.
- Tipo de necesidad.
- Estado.
- Días máximos restantes hasta la fecha límite.
- Solo vigentes.

Después de cambiar los filtros, pulsa **Aplicar filtros**. También puedes usar **Limpiar filtros** para restablecerlos.

### Dónde buscar

Pulsa **Dónde buscar** para mostrar u ocultar las secciones del SERCOP.

Actualmente, la aplicación consulta automáticamente **Necesidades y recepción de proformas**. Las demás secciones seleccionadas se abren en el portal para realizar la búsqueda manualmente; sus resultados todavía no se combinan dentro de la aplicación.

### Ficha y documentos

Para revisar una necesidad:

1. Selecciona una fila.
2. Pulsa **Ficha completa**, **Abrir necesidad** o **Documentos**.
3. Si el listado no proporciona un enlace directo reconocible, la aplicación solicitará la dirección de la ficha oficial del SERCOP.

Si se detectan documentos, puedes seleccionar algunos o intentar descargar todos en un ZIP. También puedes descargarlos directamente en una carpeta.

El número de archivos aparece como **Sin consultar** hasta que se revisan los enlaces de documentos de la necesidad.

### Exportar resultados

Pulsa **Exportar CSV** para guardar los resultados filtrados y abrirlos posteriormente en Excel u otra aplicación compatible.

### Modo noche

Pulsa **Modo noche** para cambiar los colores de la interfaz. Para volver al tema anterior, pulsa **Modo claro**.

La selección del tema se mantiene durante la sesión actual.

## Limitaciones actuales

- La consulta automática revisa un solo lote del listado de necesidades. No está comprobado que incluya todas las oportunidades.
- Las otras secciones del SERCOP todavía requieren búsqueda manual en el portal.
- El presupuesto se muestra solo cuando la fuente lo identifica como presupuesto referencial. Si no está disponible, se indica en la aplicación.
- El tipo de necesidad no confirma por sí solo si existe una puja o subasta.
- Algunas fichas o documentos podrían no detectarse, necesitar una sesión o requerir una verificación del portal.
- La aplicación no resuelve captchas automáticamente.
- Las pausas entre descargas moderan las solicitudes, pero no garantizan que el portal permita el acceso.
- La aplicación todavía no usa inteligencia artificial para clasificar oportunidades.

**Antes de presentar una proforma, confirma en el SERCOP el estado, la fecha límite, los requisitos y los documentos oficiales.**

## Posibles mejoras futuras

- Integrar automáticamente más secciones del SERCOP.
- Comprobar la cobertura de todos los lotes disponibles.
- Crear un perfil editable de la empresa.
- Agregar una búsqueda orientada a Wursta.
- Incorporar IA para analizar requisitos y sugerir oportunidades.
- Preparar borradores de propuestas a partir de formatos de la empresa.
