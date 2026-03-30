# Output Parsers

## What is an Output Parser?

An **Output Parser** defines a JSON schema that forces an agent to return structured data instead of free-form text. This is useful when you need the agent's response to be machine-readable — for example, to feed it into another system, display it in a form, or process it programmatically.

When an Output Parser is attached to an agent, the LLM is instructed to always return a JSON object that matches the defined schema.

## Creating an Output Parser

1. Open your App and go to **Output Parsers**.
2. Click **New Output Parser**.
3. Give it a name.
4. Define the **JSON schema** — describe the fields you want the agent to return.
5. Save.

## Example

**Schema:**
```json
{
  "type": "object",
  "properties": {
    "summary": { "type": "string", "description": "A one-sentence summary" },
    "sentiment": { "type": "string", "enum": ["positive", "neutral", "negative"] },
    "action_required": { "type": "boolean" }
  },
  "required": ["summary", "sentiment", "action_required"]
}
```

**Agent response (with this parser):**
```json
{
  "summary": "The customer is happy with the product but had a shipping issue.",
  "sentiment": "positive",
  "action_required": true
}
```

## Attaching an Output Parser to an Agent

1. Open the agent configuration.
2. Set the **Output Parser** field.
3. Save.

All responses from this agent will now follow the defined schema.

## When to Use Output Parsers

- **Data extraction**: Extract specific fields from documents or user inputs.
- **Classification**: Classify messages into categories.
- **Automation**: Feed structured agent output into workflows, databases, or APIs.
- **Form filling**: Have the agent populate a structured form from unstructured input.

## Notes

- Output Parsers work best with capable LLMs (GPT-4, Claude 3+). Smaller models may not reliably follow complex schemas.
- The Playground displays structured output in a readable format.
- If the LLM fails to produce valid JSON, the platform returns the raw response with an error indicator.
