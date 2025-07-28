# MessageContent Component

El componente `MessageContent` renderiza contenido de mensajes con soporte para diferentes formatos:

## Características

### 1. **Texto Plano**
- Preserva saltos de línea
- Renderiza texto simple sin formato

### 2. **JSON**
- Detecta automáticamente contenido JSON
- Formatea con indentación y sintaxis highlighting
- Muestra en bloques de código con fondo gris

### 3. **Markdown**
- **Encabezados**: `# H1`, `## H2`, `### H3`
- **Texto en negrita**: `**texto**`
- **Texto en cursiva**: `*texto*`
- **Enlaces**: `[texto](url)`
- **Código inline**: `` `código` ``
- **Bloques de código**: ```` ```json\n{"key": "value"}\n``` ````
- **Listas**: `- item` o `1. item`
- **Citas**: `> texto`
- **Tablas**: `| columna1 | columna2 |`

## Ejemplos de Uso

```tsx
import MessageContent from './MessageContent';

// Texto plano
<MessageContent content="Hola mundo" />

// JSON
<MessageContent content='{"positive": true, "message": "test"}' />

// Markdown
<MessageContent content="**Bold text** and *italic text*" />

// Código
<MessageContent content="```json\n{\"key\": \"value\"}\n```" />
```

## Detección Automática

El componente detecta automáticamente el tipo de contenido:

1. **JSON**: Si el contenido es un JSON válido
2. **Markdown**: Si contiene sintaxis de markdown
3. **Texto plano**: Por defecto

## Estilos

- **JSON**: Fondo gris, scroll horizontal, formato indentado
- **Markdown**: Estilos Tailwind CSS con `prose` classes
- **Texto plano**: `whitespace-pre-wrap` para preservar saltos de línea 