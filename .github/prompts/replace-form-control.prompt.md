
---
description: Sustituir campos completos de formulario por componentes reutilizables, conservando su funcionalidad
agent: agent
---

# Sustitución de controles de formulario

Sustituye los campos de formulario seleccionados o indicados por los componentes reutilizables correspondientes de `frontend/src/components/ui/FormField.tsx`.

Respeta las instrucciones generales del proyecto, las convenciones específicas del frontend y las instrucciones de rediseño UX.

## 1. Componentes disponibles

Utiliza los componentes existentes:

- `FormField`: inputs de tipo text, email, password, number, url y tel.
- `FormTextArea`: campos textarea.
- `FormSelect`: listas desplegables select.
- `FormCheckbox`: campos checkbox.

No crees componentes nuevos ni variantes que no existan.

## 2. Análisis previo

Antes de modificar cada campo:

- Examina el control original y su contexto.
- Consulta la implementación actual de `FormField.tsx`.
- Identifica el componente reutilizable correspondiente.
- Comprueba las props disponibles y sus tipos TypeScript.
- Identifica todos los elementos asociados al campo:
  - Label e indicador de obligatoriedad.
  - Mensajes de validación y error.
  - Textos de ayuda.
  - Contenedores y estilos.
  - Estados disabled, required y readOnly.
- Identifica los eventos, validaciones y condiciones de renderizado.
- Comprueba si utiliza formularios controlados, referencias o librerías externas.
- Detecta funcionalidades que el componente reutilizable no admite.
- No inventes propiedades.

## 3. Sustitución del campo completo

La unidad de sustitución es el campo completo, no únicamente el elemento HTML input, select, textarea o checkbox.

Para cada campo:

1. Sustituye el control y sus elementos asociados por el componente reutilizable correspondiente.
2. Traslada la etiqueta original a `label`.
3. Traslada el identificador original a `id`.
4. Conserva `value` o `checked`, según corresponda.
5. Conserva el evento `onChange` y la actualización del estado.
6. Conserva el tipo de input y sus propiedades compatibles.
7. Traslada los mensajes de error a `error`.
8. Traslada los textos de ayuda a `helpText`.
9. Conserva las condiciones que determinan cuándo se muestran los errores.
10. Conserva los estados `required` y `disabled`.
11. Conserva las opciones originales de los selects.
12. Conserva los atributos de accesibilidad compatibles.
13. Conserva los contenedores necesarios para mantener el layout.
14. Elimina los labels, mensajes y contenedores que hayan quedado redundantes.
15. No dupliques etiquetas, indicadores de obligatoriedad ni mensajes.
16. Mantén las clases adicionales únicamente cuando sean necesarias.

## 4. Propiedades de los componentes

### FormField

- Requiere `label`, `id`, `value` y `onChange`.
- `value`: string o number.
- `onChange`: `React.ChangeEvent<HTMLInputElement>`.
- `type`: text, email, password, number, url o tel.
- Admite `min`, `max`, `placeholder`, `disabled`, `required`, `error` y `helpText`.
- `className` personaliza el contenedor.
- `inputClassName` personaliza el input.

### FormTextArea

- Requiere `label`, `id`, `value` y `onChange`.
- `value`: string.
- `onChange`: `React.ChangeEvent<HTMLTextAreaElement>`.
- Admite `rows`, `placeholder`, `disabled`, `required`, `error` y `helpText`.
- `className` personaliza el contenedor.
- `textareaClassName` personaliza el textarea.

### FormSelect

- Requiere `label`, `id`, `value`, `onChange` y `options`.
- `value`: string o number.
- `onChange`: `React.ChangeEvent<HTMLSelectElement>`.
- `options`: array de objetos con `value` y `label`.
- Admite `disabled`, `required`, `error` y `helpText`.
- `className` personaliza el contenedor.
- `labelClassName` personaliza la etiqueta.

### FormCheckbox

- Requiere `label`, `id`, `checked` y `onChange`.
- `onChange`: `React.ChangeEvent<HTMLInputElement>`.
- Admite `disabled`, `helpText`, `ariaDescribedBy` y `className`.
- No admite actualmente `required` ni `error`.

## 5. Conservación de funcionalidades

- No modificar la lógica de negocio.
- No modificar las reglas ni los esquemas de validación.
- No cambiar el momento en que aparecen los mensajes de error.
- Conservar las condiciones de campos obligatorios.
- Conservar los valores iniciales y las actualizaciones de estado.
- Conservar los eventos y manejadores existentes.
- Conservar las condiciones de renderizado.
- Conservar el comportamiento de envío del formulario.
- Mantener los atributos de accesibilidad.
- No modificar la distribución visual del formulario.

## 6. Limitaciones e incompatibilidades

Los componentes reutilizables no admiten todas las propiedades HTML nativas.

Comprobar especialmente:

- Eventos `onBlur`, `onFocus`, `onKeyDown` y `onInput`.
- Referencias `ref`.
- Propiedades `readOnly`, `autoComplete`, `pattern` y `maxLength`.
- Atributos ARIA personalizados.
- Tipos de input no soportados.
- Selects con `multiple`, `optgroup` u opciones deshabilitadas.
- Textareas con propiedades adicionales.
- Checkboxes con `required`, `indeterminate` o validaciones específicas.
- Campos sin etiqueta visible.
- Mensajes de error que no puedan representarse mediante `error`.

Si alguna funcionalidad no está soportada:

1. No elimines ni alteres esa funcionalidad.
2. No modifiques `FormField.tsx` automáticamente.
3. No realices una sustitución incompleta.
4. Explica la incompatibilidad.
5. Solicita confirmación antes de continuar con ese campo.

## 7. Restricciones

- No modificar servicios, API ni backend.
- No modificar rutas ni permisos.
- No modificar dependencias ni configuración.
- No modificar `FormField.tsx` ni sus stories.
- No modificar otros componentes reutilizables.
- No modificar campos fuera del alcance solicitado.
- Limitar los cambios a los campos seleccionados y sus imports.
- No introducir estilos que contradigan el sistema de diseño.
- Respetar las convenciones TypeScript y React del proyecto.

## 8. Validación

- Comprobar que cada campo utiliza el componente correcto.
- Comprobar que todas las props existen realmente.
- Comprobar que los valores y eventos se conservan.
- Comprobar que las validaciones siguen funcionando.
- Comprobar que los errores aparecen bajo las mismas condiciones.
- Comprobar que los estados disabled y required se mantienen.
- Comprobar que no existen etiquetas ni mensajes duplicados.
- Comprobar que se mantiene la distribución del formulario.
- Comprobar que no se altera el envío del formulario.
- Comprobar que se conserva la accesibilidad.
- Ejecutar las comprobaciones de TypeScript disponibles.
- No afirmar que una comprobación ha pasado si no se ha ejecutado.

## 9. Resultado

Al finalizar, indicar:

- Archivos modificados.
- Controles originales sustituidos.
- Componentes reutilizables utilizados.
- Funcionalidades y validaciones conservadas.
- Incompatibilidades detectadas.
- Comprobaciones realizadas.
