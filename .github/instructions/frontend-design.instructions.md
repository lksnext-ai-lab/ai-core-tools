
---
applyTo: "frontend/src/**/*.{ts,tsx}"
---

# Reglas permanentes de diseño frontend — Mattin AI

## Principio general

El rediseño de Mattin AI está finalizado.

El diseño implementado actualmente constituye la referencia visual del proyecto.

Estas instrucciones se aplican siempre que se creen o modifiquen componentes,
páginas, formularios o elementos visuales del frontend, independientemente
de que la tarea esté relacionada con un rediseño.

Toda nueva funcionalidad debe integrarse respetando el diseño existente.

No realizar rediseños generales ni modificaciones visuales ajenas a la tarea.

## Antes de crear o modificar componentes

- Antes de crear cualquier elemento visual, revisar los componentes reutilizables existentes, especialmente en `frontend/src/components/ui`, y comprobar si alguno cubre la necesidad mediante sus props o variantes.
- Revisar sus props y variantes antes de crear una implementación alternativa.
- Aplicar las reglas semánticas de tokens definidas en estas instrucciones, utilizando los tokens de `tailwind.config.js`.
- Consultar `tailwind.config.js` únicamente cuando sea necesario verificar un token o resolver un caso no contemplado.
- Consultar `index.css` solo cuando la tarea afecte a estilos globales o clases CSS específicas definidas en ese archivo.
- Revisar componentes similares para mantener la coherencia visual.
- Esta comprobación incluye no solo controles de formulario, sino también alertas, mensajes de validación, notificaciones, ventanas modales, tarjetas, badges, tooltips, indicadores de carga y otros elementos de interfaz.
- Priorizar los componentes compartidos existentes frente a implementaciones personalizadas con JSX y Tailwind cuando su funcionalidad y uso previsto sean equivalentes.
- Revisar cómo se implementan elementos similares en otras pantallas antes de decidir qué componente utilizar.

## Reglas generales

- La aplicación utiliza React, TypeScript y Tailwind CSS 3.
- Conservar la lógica de negocio y el comportamiento existente.
- Conservar eventos `onClick`, `onChange`, estados `disabled` y `loading`,
  navegación, validaciones y permisos.
- No modificar servicios, API ni backend salvo que la tarea lo requiera.
- No modificar dependencias ni configuración sin autorización.
- Respetar los estilos y variables CSS existentes.
- No modificar componentes ajenos a la tarea.
- Mantener compatibilidad con modo claro, modo oscuro y diseño responsive.
- No rediseñar componentes existentes salvo que se solicite expresamente
  o sea necesario para integrar correctamente la funcionalidad solicitada.
- Si se detecta un componente con el diseño antiguo fuera del alcance
  de la tarea, informar sin modificarlo.


## Consistencia visual

- Priorizar los componentes y tokens del sistema de diseño existente.
- No introducir colores, tipografías o espaciados nuevos si existe un valor equivalente definido en el proyecto.
- Evitar repetir bloques extensos de clases Tailwind.
- No utilizar estilos inline para sobrescribir estilos de Tailwind.
- No utilizar !important salvo que sea estrictamente necesario.


### Uso semántico de tokens de diseño

Los tokens de diseño de Mattin AI están definidos en `tailwind.config.js`.

Al crear o modificar componentes, utilizar los tokens según la función visual de cada elemento.

Priorizar siempre los estilos proporcionados por los componentes reutilizables.

#### Textos

- Texto principal, nombres y contenido habitual: `text-fg dark:text-fg-dark`.
- Texto secundario, descripciones y contenido complementario: `text-fg-secondary dark:text-fg-secondary-dark`.
- Texto terciario, metadatos y contenido de menor jerarquía: `text-fg-tertiary dark:text-fg-tertiary-dark`.
- Texto de menor relevancia o deshabilitado: utilizar los tokens `fg.faint` o `fg.faint2` según el patrón existente.
- Para texto sobre superficies de alto contraste, utilizar `text-ink-on` o `dark:text-ink-on-dark` cuando corresponda al patrón existente.
- No utilizar colores arbitrarios como `text-gray-*`, `text-slate-*` o valores hexadecimales cuando exista un token semántico equivalente en el proyecto.
- Respetar los colores propios de los componentes reutilizables y sus variantes.

#### Fondos

- Fondo general de página: `bg-canvas dark:bg-canvas-dark`.
- Fondo de superficie o contenido: `bg-surface dark:bg-surface-dark`.
- Fondo alternativo de superficie: `bg-surface-tint dark:bg-surface-tint-dark`.
- Fondo de superficie al pasar el ratón: `bg-surface-hover dark:bg-surface-hover-dark`.
- Para tarjetas, utilizar preferentemente `CardApp` o `ButtonCard` y sus variantes.
- No aplicar fondos personalizados a componentes que ya gestionan su propia apariencia.

#### Bordes

- Borde general: `border-line dark:border-line-dark`.
- Borde de mayor contraste: `border-line-strong dark:border-line-strong-dark`.
- Para tarjetas, formularios y tablas, respetar los bordes definidos en sus componentes reutilizables.
- No introducir grosores ni colores de borde arbitrarios.

#### Estados y mensajes

- Información: `info`, `info-bg`, `info-border`.
- Éxito: `success`, `success-bg`, `success-border`.
- Error: `error`, `error-bg`, `error-border`.
- Advertencia: `bronze`, `bronze-bg`, `bronze-border`.
- Utilizar las variantes `dark` correspondientes.
- Priorizar los componentes reutilizables de alertas, badges y mensajes antes de aplicar estos tokens manualmente.
- No utilizar colores genéricos como `blue-*`, `green-*`, `red-*` o `yellow-*` para representar estados.

#### Estados interactivos

- Utilizar el token `accent` para el foco de controles cuando corresponda al patrón del componente.
- Respetar los estilos de hover, selected, disabled y focus definidos en los componentes reutilizables.
- No añadir anillos, sombras ni bordes adicionales cuando el componente ya gestiona esos estados.
- Los estilos de foco de `ButtonCard` se gestionan exclusivamente dentro del propio componente.

#### Tipografía

- Utilizar `font-sans` (Inter) para el texto habitual.
- Utilizar `font-display` (Space Grotesk) para títulos y elementos que sigan ese patrón.
- Respetar los tamaños, pesos y jerarquías definidos en los componentes reutilizables.
- No introducir tamaños arbitrarios cuando exista un patrón establecido.

#### Criterios generales

- Utilizar siempre tokens semánticos de Mattin AI en lugar de colores directos de Tailwind.
- Mantener compatibilidad con modo claro y oscuro.
- No crear nuevos tokens ni modificar los existentes sin autorización.
- No sobrescribir los estilos visuales de componentes reutilizables desde las páginas.
- Consultar `tailwind.config.js` solo para verificar tokens existentes o resolver usos no documentados.
- No consultar `index.css` como catálogo de tokens.

## Gestión de variantes

- Utilizar variant para diferencias visuales significativas.
- Utilizar size cuando existan distintos tamaños.
- No crear variantes diferentes únicamente para cambiar textos,
  iconos o contenido.
- Evitar combinaciones de props que produzcan estados visuales
  contradictorios.
- No crear variantes nuevas si las existentes cubren el diseño.

## Contenedores visuales y tarjetas

El componente `CardApp` es la referencia principal para los contenedores visuales de tipo tarjeta en Mattin AI.

### Reutilización de CardApp

- Antes de crear un `div` con fondo, borde, padding o esquinas redondeadas que funcione como tarjeta o sección visual independiente, comprobar si puede utilizarse `CardApp`.
- Priorizar `CardApp` frente a contenedores personalizados cuando su estructura y comportamiento cubran la necesidad.
- Utilizar las variantes existentes según su finalidad:
  - `white`: tarjetas y secciones de contenido generales.
  - `canvas`: bloques con superficie alternativa.
  - `selected`: elementos que representan una selección activa.
  - `subtle`: bloques secundarios sin borde.
- No crear nuevas variantes ni modificar las existentes sin comprobar primero si cubren la necesidad.
- No modificar `CardApp` para resolver un caso particular sin valorar el impacto en sus otros usos.

### Cabeceras y contenido

- Utilizar las propiedades `titulo`, `subtitulo`, `icon` y `headerExtra` cuando permitan resolver la cabecera de la tarjeta.
- Evitar crear manualmente cabeceras que dupliquen las funcionalidades existentes de `CardApp`.
- Mantener la estructura, alineación y espaciado proporcionados por el componente.
- Utilizar `children` para incorporar el contenido específico de cada tarjeta.

### Estilos y personalización

- Respetar los fondos, bordes, radios, padding y colores definidos en las variantes de `CardApp`.
- Evitar sobrescribir mediante `className` los estilos visuales base del componente.
- Utilizar `className` únicamente para ajustes de disposición o necesidades justificadas que no alteren la identidad visual de la variante.
- No duplicar manualmente las clases de `CardApp` en otros componentes.


### Cuando CardApp no sea adecuado

- Utilizar un contenedor personalizado únicamente cuando `CardApp` no cubra la necesidad funcional, estructural o semántica.
- No utilizar `CardApp` para elementos que ya disponen de un componente reutilizable específico.
- Cuando sea necesario crear un contenedor personalizado de tipo tarjeta, utilizar como referencia visual la variante de `CardApp` que mejor se adapte a su finalidad.

#### Estilos de referencia

- Para contenedores equivalentes a la variante `white`,
  utilizar los siguientes estilos:
  - Fondo: `bg-surface dark:bg-surface-dark`.
  - Borde: `border border-line dark:border-btCard-border-dark`.
  - Esquinas: `rounded-md`.
  - Padding: `p-4`.
  - Sin sombras.

- Para contenedores equivalentes a otras variantes (`canvas`, `subtle`, `selected`), consultar los estilos definidos en `CardApp.tsx` y respetar sus tokens y convenciones.

- Mantener la misma apariencia visual en modo claro y oscuro.

#### Restricciones visuales

- No utilizar `rounded-lg`, `rounded-xl`, `rounded-2xl` ni otros radios diferentes de `rounded-md` en contenedores de tipo tarjeta, salvo que un componente existente requiera expresamente otro radio.
- No añadir sombras (`shadow`, `shadow-sm`, `shadow-md`, `shadow-lg`, etc.) a tarjetas o contenedores personalizados.
- No introducir bordes más gruesos, colores de fondo alternativos ni efectos hover decorativos que no estén definidos en la variante de referencia.
- Respetar las excepciones propias de cada variante, como el borde de 2 px de `selected`.
- No utilizar valores arbitrarios de Tailwind cuando existan tokens o estilos equivalentes en el proyecto.
- No crear una apariencia visual diferente si los estilos existentes permiten resolver la necesidad.
- Evitar copiar manualmente las clases de `CardApp` cuando pueda utilizarse directamente el componente.


### Comprobación final

- Verificar que los nuevos contenedores de tipo tarjeta reutilizan `CardApp` siempre que sea adecuado.
- Comprobar que no se han duplicado cabeceras, bordes o estilos proporcionados por el componente.
- Revisar que las variantes utilizadas corresponden a la finalidad visual del contenedor.
- Comprobar la coherencia de los contenedores personalizados con el sistema de diseño existente.


## Tarjetas interactivas y selección — ButtonCard

El componente `ButtonCard` es la referencia principal para tarjetas interactivas y tarjetas de selección en Mattin AI.

### Cuándo utilizar ButtonCard

- Antes de crear una tarjeta que permita ejecutar una acción, navegar a un recurso o seleccionar una opción, comprobar si puede utilizarse `ButtonCard`.
- Priorizar `ButtonCard` frente a implementaciones manuales con `div`, `button` y clases Tailwind cuando el componente cubra la necesidad.
- No utilizar `CardApp` para simular una tarjeta interactiva si `ButtonCard` proporciona el comportamiento requerido.
- No utilizar `ButtonCard` para tarjetas exclusivamente informativas o contenedores de secciones sin interacción. En esos casos, valorar primero `CardApp`.

### Selección de variantes

- `default`:
  - Para tarjetas cuya finalidad principal sea abrir un recurso, navegar o ejecutar una acción.
  - Utilizar el comportamiento de clic de la tarjeta.

- `selectable`:
  - Para tarjetas que representan opciones seleccionables mediante un estado visual.
  - Utilizar la propiedad `selected` para reflejar la selección.
  - No implementar manualmente los estilos de selección.

- `selectable-radio`:
  - Para elegir una única opción dentro de un grupo.
  - Utilizar `radioName` y `radioValue` cuando corresponda.
  - No añadir controles radio independientes si la variante ya proporciona esa funcionalidad.

- `selectable-check`:
  - Para activar o desactivar opciones independientes.
  - Utilizar `selected`, `checkboxLabel` y `checkboxHelpText` cuando corresponda.
  - No añadir un checkbox manual si la variante ya lo incluye.

### Interacción y accesibilidad

- Utilizar `onClick` para gestionar la acción o el cambio de selección.
- Mantener sincronizada la propiedad `selected` con el estado real de la opción.
- Utilizar `disabled` cuando la acción no esté disponible.
- Proporcionar un `ariaLabel` descriptivo e internacionalizado.
- Respetar el comportamiento de teclado y accesibilidad proporcionado por el componente.
- Cuando la tarjeta contenga controles interactivos propios, revisar el uso de `interactiveChildren` y el comportamiento de los eventos para evitar acciones duplicadas.
- No crear manualmente una capa de botón sobre la tarjeta:
  `ButtonCard` ya proporciona ese comportamiento.

### Estilos y personalización

- Respetar los fondos, bordes, radios, padding y estados visuales definidos en las variantes de `ButtonCard`.
- No añadir sombras ni radios diferentes mediante `className`.
- No sobrescribir los estilos base de las variantes.
- Utilizar `className` únicamente para ajustes de layout que no alteren la identidad visual del componente.
- No recrear manualmente los estilos de selección, hover o estado activo que ya proporciona `ButtonCard`.
- Mantener compatibilidad con modo claro y oscuro.
- No añadir estilos de foco, anillos (`ring`), bordes ni sombras a `ButtonCard` desde las páginas que lo utilizan.
- Los estilos de foco de teclado de `ButtonCard` se gestionan exclusivamente dentro del componente reutilizable.
- Utilizar el token `accent` para el indicador de foco, tanto en modo claro como oscuro.
- Mostrar el indicador únicamente mediante `:focus-visible`, evitando que aparezca al hacer clic con el ratón.
- No añadir clases `focus:*`, `focus-within:*` ni `focus-visible:*` desde las páginas que utilizan `ButtonCard`.
- Mantener independientes los estados de foco y selección.

### Cuando ButtonCard no sea adecuado

- Utilizar otro componente reutilizable cuando la tarjeta necesite un comportamiento que `ButtonCard` no proporciona.
- Si es imprescindible crear una tarjeta interactiva personalizada, tomar como referencia visual la variante de `ButtonCard` equivalente.
- Utilizar los mismos tokens de fondo, borde, radio, padding y estados visuales.
- No introducir sombras, `rounded-lg`, `rounded-xl`, colores arbitrarios ni efectos decorativos ajenos al sistema de diseño.
- Mantener la accesibilidad y el comportamiento de teclado adecuados al tipo de interacción.
- No modificar `ButtonCard` para resolver una necesidad particular sin valorar el impacto en sus otros usos.

### Comprobación final

- Verificar que se ha utilizado `ButtonCard` cuando la tarjeta es interactiva y el componente cubre la necesidad.
- Comprobar que la variante elegida corresponde al comportamiento esperado.
- Verificar que los estados `selected` y `disabled` funcionan correctamente.
- Comprobar que no se han duplicado botones, radios o checkboxes que el componente ya proporciona.
- Revisar la interacción por teclado y la accesibilidad.
- Comprobar la internacionalización de los textos.

## Estructura y diseño de páginas completas

Al crear páginas nuevas, seguir la estructura y los
patrones de layout existentes en Mattin AI.

### Layout general

- Las páginas protegidas utilizan `Layout.tsx` mediante `ProtectedLayoutRoute`.
- El layout proporciona cabecera, sidebar, footer, área de contenido y scroll.
- El contenedor principal ya aplica: `px-4 py-6 sm:px-6 lg:px-10 lg:py-10`.
- El contenido global está centrado en `max-w-7xl`.
- No duplicar el padding ni el ancho máximo proporcionados por el layout.
- No crear layouts principales alternativos si el existente cubre la necesidad.

### Encabezados y navegación

- Utilizar el componente `Title.tsx` para títulos y subtítulos de página.
- Seleccionar la variante de título adecuada según la jerarquía existente.
- Los breadcrumbs los proporciona el layout mediante `PageTitle` y `Breadcrumbs.tsx`.
- No duplicar breadcrumbs dentro del contenido.
- Mantener la posición habitual de las acciones  principales y secundarias.
- Permitir que los encabezados con varias acciones se adapten a pantallas estrechas.

### Páginas de listado

Referencias: `AgentsPage.tsx`, `DomainsPage.tsx`.

- Utilizar `space-y-6` como separación vertical habitual.
- Mantener título y acciones en el encabezado.
- Utilizar el ancho global del layout salvo necesidad justificada de limitarlo.
- Reutilizar los componentes existentes de tablas, botones, estados de carga, alertas y acciones.
- Mantener el comportamiento responsive de las tablas.

### Páginas de formulario y edición

Referencias: `AgentFormPage.tsx`, `SiloFormPage.tsx`.

- Priorizar `max-w-4xl mx-auto` para formularios que necesiten una anchura de lectura controlada.
- No añadir padding de página si ya lo proporciona el layout principal.
- Utilizar los componentes reutilizables de formulario.
- Utilizar `FormActions` para las acciones finales cuando corresponda.
- Mantener las acciones de Cancelar y Guardar en la posición habitual.
- Organizar los campos con grids responsive cuando sea necesario.

### Páginas con pestañas

Referencias: `AgentFormPage.tsx`, `MarketplacePage.tsx`,
`DomainDetailPage.tsx`.

- Utilizar el componente reutilizable `Tabs.tsx`.
- Colocar las pestañas debajo del encabezado.
- Mantener una separación coherente entre pestañas y contenido.
- Utilizar el ancho global o `max-w-4xl` según la complejidad del contenido.
- Mantener la navegación por teclado y el comportamiento responsive del componente.
- No crear implementaciones alternativas de pestañas  si el componente existente cubre la necesidad.

### Páginas de detalle

Referencias: `ScheduledTaskDetailPage.tsx`,
`DomainDetailPage.tsx`.

- Utilizar `Title.tsx` para el encabezado.
- Agrupar la información mediante los componentes de cards y secciones existentes.
- Utilizar `max-w-4xl` cuando el contenido requiera una anchura de lectura controlada.
- Mantener las acciones principales junto al título cuando corresponda.
- Permitir el ajuste de las acciones en pantallas  estrechas.
- Utilizar grids responsive para distribuir los datos.

### Comprobación final

- Verificar que la página hereda correctamente el layout.
- Comprobar que no existe padding duplicado.
- Revisar alineación de títulos, pestañas y contenido.
- Verificar la coherencia de márgenes y espaciados.
- Comprobar el comportamiento responsive.
- Mantener la internacionalización de todos los textos.
- No modificar páginas existentes para adaptarlas
  a estas instrucciones.
  
## Tablas y páginas de listado

Al crear o modificar páginas de listado, respetar los
patrones visuales existentes en Mattin AI.

### Componente de tabla

- Utilizar el componente reutilizable `Table.tsx` para mostrar listados tabulares.
- No crear tablas HTML personalizadas cuando `Table` cubra la necesidad.
- Aprovechar las propiedades existentes de `Table` para configurar columnas, contenido, acciones, estados vacíos y comportamiento responsive.
- No modificar `Table.tsx` para resolver necesidades específicas de una pantalla si pueden solucionarse  mediante sus propiedades.

### Iconos y nombres

- Cuando una fila muestre un icono junto al nombre del elemento, utilizar el componente reutilizable `BackgroundImage`.
- No mostrar iconos directamente con clases Tailwind cuando el patrón visual existente requiera `BackgroundImage`.
- Para los iconos junto al nombre, utilizar como referencia:
  - `size={34}`
  - `iconSize={17}`
- Seleccionar el icono Lucide correspondiente al tipo de recurso mostrado.
- Mantener la alineación vertical y separación entre icono y nombre utilizadas en los listados.
  
### Tipografía y colores de las columnas

- La columna principal, normalmente el nombre del recurso, debe destacar visualmente sobre las demás.
- Para el texto de la columna principal utilizar:
  - Tamaño y peso: `text-sm font-medium`.
  - Color: `text-fg dark:text-fg-dark`.
- Para el contenido de las columnas secundarias utilizar:
  - Tamaño: `text-xs`.
  - Color: `text-fg-secondary dark:text-fg-secondary-dark`.
- Aplicar estas diferencias mediante las propiedades de las columnas o sus funciones de renderizado, sin modificar los estilos globales de `Table`.
- Los estados, badges, enlaces y controles de acciones deben conservar los colores, tamaños y estilos definidos por sus respectivos componentes reutilizables.
- No introducir tamaños ni colores arbitrarios cuando existan tokens equivalentes en el proyecto.


### Columnas fijas y desplazamiento horizontal

- En las tablas de listado, mantener fija la primera columna durante el desplazamiento horizontal.
- Cuando exista una última columna de acciones, mantenerla también fija durante el desplazamiento horizontal.
- Utilizar las propiedades existentes de `Table.tsx` para configurar las columnas fijas.
- Activar `stickyEdgeColumns` cuando corresponda y utilizar `sticky: 'right'` en la columna de acciones.
- No implementar manualmente columnas sticky mediante contenedores o estilos personalizados si `Table` ya proporciona esa funcionalidad.
- Mantener correctamente los fondos, bordes y estados hover de las columnas fijas.
- Comprobar el comportamiento con desplazamiento horizontal, especialmente en pantallas pequeñas.
- No fijar otras columnas salvo que la funcionalidad lo requiera expresamente.

### Estado vacío

- Utilizar las propiedades `emptyIcon`, `emptyMessage` y `emptySubMessage` de `Table`.
- No crear manualmente un estado vacío fuera de la tabla cuando el componente ya lo permite.
- Para `emptyIcon`, utilizar `BackgroundImage` con las siguientes dimensiones de referencia:
  - `size={64}`
  - `iconSize={32}`
- Seleccionar un icono adecuado al tipo de recurso o listado.
- No utilizar iconos Lucide directamente con tamaños, fondos o colores personalizados para sustituir este patrón.
- Internacionalizar los mensajes del estado vacío.

### Layout y responsive

- Heredar los márgenes y padding del layout principal.
- No añadir padding de página que duplique el existente.
- Mantener la alineación del título, acciones y tabla.
- Utilizar el ancho global disponible salvo que exista una necesidad justificada de limitarlo.
- Respetar el comportamiento responsive de `Table`, incluyendo el scroll horizontal cuando sea necesario.
- Reutilizar los componentes existentes para las acciones de cada fila.

### Comprobación final

- Verificar que se utiliza el componente `Table`.
- Comprobar que los iconos de las filas utilizan `BackgroundImage` cuando corresponde.
- Comprobar la jerarquía tipográfica entre la columna principal y las secundarias.
- Verificar el estado vacío con y sin datos.
- Comprobar que los mensajes están internacionalizados.
- Revisar márgenes, alineación y comportamiento responsive.

## Selección de contenedores y navegación

Al crear o modificar formularios, seleccionar el contenedor más adecuado según la complejidad, el contexto y los patrones existentes en la aplicación.

Aplicar los siguientes criterios en orden:

1. Edición inline:
   - Para modificar directamente un valor visible.
   - Cuando no sea necesario abrir una nueva interfaz.

2. Ventana modal:
   - Para confirmaciones, decisiones puntuales o formularios muy sencillos.
   - Cuando la operación no necesite una navegación propia.
   - Evitar modales para formularios extensos o con pestañas.

3. Asistente en página:
   - Para procesos con varios pasos dependientes.
   - Cuando sea necesario completar o validar una etapa antes de continuar con la siguiente.

4. Panel lateral:
   - Para consultar o editar información manteniendo visible el contexto de la pantalla principal.
   - Para formularios relativamente breves, de una columna y sin pasos ni pestañas de edición.
   - Como orientación, hasta unos 8 campos, con opciones avanzadas plegadas cuando corresponda.
   - Evitar paneles para formularios con contenido extenso, tablas editables, código o configuraciones complejas.

5. Página completa:
   - Para formularios extensos, configuraciones avanzadas, múltiples secciones o pestañas de edición.
   - Cuando el usuario necesite espacio para trabajar con el contenido o una navegación propia.
   - Para procesos que no encajen adecuadamente en una modal o panel lateral. 

### Reglas generales de contenedores

- Revisar primero los patrones y componentes existentes.
- No elegir automáticamente una modal porque la acción se inicie desde un botón de una página.
- Mantener coherencia entre los contenedores utilizados para crear y editar un mismo tipo de recurso.
- Reutilizar los componentes de navegación y pestañas existentes en la aplicación.
- Para páginas completas, priorizar el patrón de pestañas utilizado actualmente en las páginas equivalentes.
- Para paneles laterales, respetar la estructura, anchura y comportamiento de los paneles existentes.
- Evitar abrir modales sobre otras modales.
- Proteger los cambios sin guardar al cerrar o abandonar formularios, siguiendo los patrones existentes.
- Respetar la navegación, accesibilidad y comportamiento responsive de la aplicación.
- No modificar contenedores existentes solo para adaptarlos a estas reglas.
- Aplicar estas decisiones a funcionalidades nuevas o modificaciones solicitadas, sin iniciar rediseños de pantallas existentes.
- Si el usuario especifica el tipo de contenedor, respetar su elección.
- Si existen alternativas igualmente adecuadas y la decisión afecta significativamente a la experiencia de usuario, consultar antes de implementar.

## Validación y mensajes en formularios

- Antes de implementar un formulario, revisar las propiedades y funcionalidades de los componentes reutilizables existentes.
- Utilizar los mecanismos de ayuda, validación y mensajes de error que ya proporcionan los componentes del proyecto.
- No implementar manualmente mensajes de error o ayuda si el componente reutilizable ya dispone de esa funcionalidad.
- Mostrar los errores de validación específicos de un campo debajo del propio campo, utilizando las propiedades previstas por el componente.
- No utilizar tooltips para mostrar errores de validación cuando el componente permite mostrar mensajes debajo.
- Los tooltips pueden utilizarse para información adicional o ayuda contextual, pero no deben sustituir los mensajes de error visibles.
- Cuando un campo tenga un error, aplicar también el estado visual de error que proporcione el componente reutilizable.
- Los mensajes explicativos deben utilizar los mecanismos de ayuda existentes en los componentes.
- Utilizar el componente de alerta reutilizable para errores generales del formulario, cuando corresponda.
- Evitar duplicar el mismo mensaje de error en una alerta general y debajo del campo.
- Respetar las convenciones de internacionalización del proyecto para todos los mensajes de ayuda y validación.
- No introducir nuevos mecanismos de validación si los existentes cubren la necesidad.
- Respetar el momento y comportamiento de validación utilizado en los formularios existentes (al perder el foco, al guardar, durante la escritura, etc.), sin introducir un patrón diferente.
- Priorizar las propiedades de ayuda y error de los componentes reutilizables frente a implementaciones manuales, aunque estas últimas reproduzcan detalles decorativos de otros formularios, salvo que dichos detalles sean un requisito explícito de la tarea.

## Validación de cambios

- Comprobar que los cambios no generan errores de TypeScript.
- Comprobar que no se han eliminado funcionalidades existentes.
- No modificar archivos fuera del alcance de la tarea.
- Informar de los archivos modificados y de las comprobaciones realizadas.
- No afirmar que una comprobación ha pasado si no se ha ejecutado.

## Accesibilidad

- Cumplir las convenciones de accesibilidad WCAG 2.1
  establecidas en el proyecto.
- Utilizar elementos HTML semánticos.
- Garantizar la navegación mediante teclado.
- Mantener indicadores de foco visibles.
- Incluir `aria-label` en botones que solo contienen iconos.
- No utilizar únicamente el color para transmitir información.
- Conservar los atributos de accesibilidad al sustituir
  componentes existentes.
  
## Arquitectura

- Respetar la separación entre biblioteca base y aplicaciones cliente.
- Crear componentes genéricos reutilizables en `frontend/src/components/ui`.
- No incorporar personalizaciones específicas de un cliente directamente en la biblioteca base.
- Respetar los mecanismos de configuración y extensión existentes en el proyecto.


## Creación y ubicación de componentes

Antes de crear un componente React, determinar si es un componente UI reutilizable, un componente específico de una funcionalidad o un componente interno de una página.

### Componentes UI reutilizables

- Ubicar en `frontend/src/components/ui` los componentes genéricos de presentación o interacción que puedan utilizarse en distintas funcionalidades.
- Estos componentes no deben depender de entidades, servicios, rutas ni lógica de negocio específicos.
- Deben permitir configurar su comportamiento y presentación mediante props.
- Antes de crear uno nuevo, comprobar si existe un componente equivalente o una variante reutilizable.
- Seguir las convenciones de diseño, accesibilidad, internacionalización y Storybook del proyecto.

### Componentes específicos de una funcionalidad

- Mantener los componentes vinculados a una entidad o funcionalidad concreta fuera de `components/ui`.
- Ubicarlos siguiendo la estructura existente de esa funcionalidad o junto a las páginas que los utilizan.
- No convertir automáticamente un componente en UI genérico por utilizarse en varias pantallas.
- Evitar que los componentes genéricos dependan de modelos o lógica de negocio específicos.

### Componentes internos de una página

- Si un componente solo se utiliza en una página y contiene lógica específica de ella, mantenerlo próximo a esa página.
- Extraer componentes cuando mejore la claridad, el mantenimiento o la reutilización del código.
- No crear componentes independientes para fragmentos pequeños que no aporten una responsabilidad clara.

### Criterios de decisión

Antes de decidir la ubicación, comprobar:

1. ¿Existe ya un componente que cubra la necesidad?
2. ¿Es independiente de la lógica de negocio?
3. ¿Puede utilizarse en funcionalidades diferentes sin conocer sus entidades o servicios?
4. ¿Su API puede expresarse mediante props genéricas?
5. ¿Existe una convención de ubicación para componentes equivalentes en el proyecto?

- Si es genérico y reutilizable, utilizar `components/ui`.
- Si pertenece a una funcionalidad, mantenerlo en su ámbito.
- Si es exclusivo de una página, mantenerlo próximo a ella.
- No mover componentes existentes ni reorganizar carpetas sin que la tarea lo requiera.

### Verificación final

- Comprobar que cada componente nuevo está ubicado según su responsabilidad.
- Evitar duplicar componentes UI existentes.
- Comprobar que los componentes genéricos no contienen dependencias de negocio innecesarias.
- Crear o actualizar las stories de Storybook cuando corresponda según las reglas del proyecto.

## Creación de nuevos componentes UI

Cuando se solicite crear un nuevo componente, seguir las siguientes reglas:

### 1. Estilos
- Utilizar **Tailwind CSS 3** para definir los estilos.
- Priorizar las clases estándar de Tailwind frente a valores arbitrarios, salvo que el diseño requiera medidas específicas.
- Reutilizar los colores, fuentes y variables CSS existentes en el proyecto.
- Incluir soporte para modo claro y oscuro mediante las clases `dark:` de Tailwind.
- Evitar estilos inline y archivos CSS adicionales salvo que sean necesarios.
- Utilizar exclusivamente las bibliotecas de iconos existentes en el proyecto.
- No instalar nuevas bibliotecas de iconos.
- Importar los iconos individualmente.

### 2. Props y variantes
- Priorizar el uso de una prop `variant` para representar las distintas apariencias visuales del componente.
- Evitar añadir numerosos props booleanos que compliquen su configuración y mantenimiento.
- Definir las variantes mediante tipos TypeScript, utilizando uniones de literales.
- Utilizar props independientes cuando representen contenido, datos o funcionalidades, como `onClick`, `disabled`, `children` o `loading`.
- Definir valores por defecto razonables.
- Mantener una API sencilla, clara y fácil de entender.
- Declarar las propiedades de las interfaces como `readonly`.
- Exportar las interfaces de props separadamente del componente.
- Priorizar uniones discriminadas cuando existan configuraciones de props mutuamente excluyentes.
- No utilizar `any`; utilizar tipos específicos o `unknown` con validación cuando corresponda.

### 3. Reutilización
- Cuando se cree un componente UI reutilizable, diseñarlo de forma genérica e independiente de una pantalla concreta.
- Para componentes específicos de una funcionalidad o página, seguir los criterios de ubicación establecidos en "Creación y ubicación de componentes".
- Comprobar si existe un componente similar antes de crear uno nuevo.
- Mantener separada la presentación de la lógica de negocio.
- Respetar la arquitectura de frontend definida en
  las instrucciones generales del proyecto.
- Crear componentes reutilizables de propósito general
  en `frontend/src/components/ui`, cuando corresponda.
- Los componentes específicos de un cliente deben seguir
  la estructura de `clients/`.
- No modificar la biblioteca base para incorporar
  personalizaciones exclusivas de un cliente.


### 4. Storybook

#### Creación y actualización automática

- Crear o actualizar las stories de Storybook como parte de la misma tarea de desarrollo, sin esperar a que el usuario lo solicite expresamente.
- Crear un archivo `.stories.tsx` para cada componente UI reutilizable nuevo.
- Cuando se modifique un componente UI reutilizable, revisar su story existente y actualizarla si cambian sus props, variantes, estados o comportamiento visual.
- No exigir stories para componentes internos específicos de una página, salvo que su complejidad o necesidad de documentación lo justifique.
- No modificar stories de componentes ajenos a la tarea.

#### Variantes, estados e interacciones

- Asegurar que todas las variantes visuales del componente puedan visualizarse en Storybook.
- Incluir los estados relevantes, como `disabled`, `loading`, `hover`, `selected` o `error`, cuando correspondan.
- Documentar las props mediante los controles de Storybook siempre que sea posible.
- Utilizar las utilidades de Storybook para representar interacciones como `onClick` cuando corresponda.
- Evitar duplicar stories cuando las diferencias puedan representarse mediante controles.

#### Modo claro y oscuro

- Asegurar que los componentes y sus variantes puedan visualizarse en modo claro y oscuro.
- Priorizar el selector global de tema de Storybook.
- No duplicar stories exclusivamente para representar los modos claro y oscuro.

#### Verificación final

- Antes de finalizar una tarea que cree o modifique un componente UI reutilizable, comprobar si es necesario crear o actualizar su story.
- Verificar que las stories reflejan las props, variantes, estados e interacciones actuales del componente.
- Comprobar que las stories modificadas no presentan errores de TypeScript ni de compilación.
- No considerar completa la implementación de un componente UI reutilizable nuevo si falta su story correspondiente.

### 5. Calidad
- Utilizar React y TypeScript.
- Definir interfaces o tipos claros para las props.
- Utilizar HTML semántico y atributos de accesibilidad cuando corresponda.
- No modificar otros componentes ni la lógica de negocio salvo que la tarea lo requiera.


## Verificación obligatoria de las instrucciones de diseño

Estas instrucciones deben aplicarse durante la implementación de cualquier componente, formulario, tabla o página del frontend.

### Antes de implementar

- Identificar las secciones de este archivo que afectan a la tarea solicitada.
- Revisar los componentes reutilizables relacionados y sus propiedades disponibles.
- Consultar los patrones de referencia indicados en las instrucciones cuando corresponda.
- Tener en cuenta las reglas aplicables desde el inicio, no únicamente cuando el usuario solicite una revisión.

### Antes de finalizar

- Revisar el código creado o modificado y comprobar que cumple todas las reglas de diseño aplicables.
- Verificar que se han utilizado correctamente los componentes reutilizables y sus propiedades.
- Comprobar especialmente los requisitos específicos del tipo de interfaz implementada:
  - Formularios: componentes reutilizables, validaciones, ayuda y mensajes de error.
  - Tablas: iconos, tipografía, columnas fijas y estado vacío.
  - Tarjetas de contenido: uso de `CardApp` y sus variantes.
  - Tarjetas interactivas: uso de `ButtonCard`, variantes, selección, interacción y foco de teclado.
  - Páginas: layout, márgenes, títulos y navegación.
  - Pestañas: componente reutilizable y conservación del estado.
  - Componentes nuevos: responsabilidad, ubicación y reutilización.
  - Storybook: creación o actualización de stories cuando corresponda.
- Verificar la internacionalización de todos los textos nuevos.
- Corregir los incumplimientos detectados antes de dar la tarea por terminada.
- Si alguna regla no puede cumplirse, explicar el motivo y solicitar confirmación antes de aplicar una alternativa.

### Criterio de finalización

- No considerar terminada una tarea de interfaz hasta haber comprobado el cumplimiento de las instrucciones de diseño aplicables.
- No limitarse a afirmar que se han seguido las reglas: comprobarlo en el código implementado.
- Realizar esta revisión como parte del trabajo habitual, sin esperar a que el usuario la solicite expresamente.
