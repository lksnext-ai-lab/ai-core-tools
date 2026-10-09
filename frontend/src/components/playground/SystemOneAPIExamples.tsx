import { useState } from 'react';
import { Check, Copy, KeyRound } from 'lucide-react';
import type { SystemOneQuestion } from '../../types/systemOne';

interface SystemOneAPIExamplesProps {
  readonly appId: number;
  readonly agentId: number;
  readonly agentName: string;
  readonly questions: SystemOneQuestion[];
}

function exampleResponse(questions: SystemOneQuestion[]): string {
  const answers: Record<string, unknown> = {};
  for (const q of questions.slice(0, 3)) {
    if (q.type === 'noul') {
      answers[q.key] = { type: 'noul', decision: true, probability: 0.91, threshold: q.threshold ?? 0.5 };
    } else if (q.type === 'choice') {
      const [first, second] = q.criteria;
      answers[q.key] = {
        type: 'choice', decision: first?.key ?? 'option', choice: first?.key ?? 'option', probability: 0.73,
        probabilities: { [first?.key ?? 'option']: 0.73, [second?.key ?? 'other']: 0.27 }, confidence: 0.39,
      };
    } else {
      answers[q.key] = {
        type: 'score', decision: q.criteria[1] ?? 'level', level_index: 1, probability: 0.62, expected_score: 1.2,
        legend: Object.fromEntries(q.criteria.map((c, i) => [String(i), c])),
        probabilities: Object.fromEntries(q.criteria.map((_, i) => [String(i), i === 1 ? 0.62 : 0.38 / Math.max(q.criteria.length - 1, 1)])),
        confidence: 0.3,
      };
    }
  }
  return JSON.stringify(
    { answers, state_reduction: 'none', original_chars: 120, state_chars: 120, model: 'nimble-latest', usage: { input_tokens: 400, output_tokens: 4 } },
    null,
    2,
  );
}

function CodeBlock({ title, code }: { readonly title: string; readonly code: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }
  return (
    <div className="rounded-xl border border-gray-200 bg-white">
      <div className="flex items-center justify-between border-b border-gray-200 px-4 py-2">
        <h4 className="text-sm font-semibold text-gray-800">{title}</h4>
        <button type="button" onClick={() => void copy()} className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-gray-600 hover:bg-gray-100">
          {copied ? <Check className="h-3 w-3" aria-hidden="true" /> : <Copy className="h-3 w-3" aria-hidden="true" />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre className="overflow-x-auto p-4 text-xs text-gray-800"><code>{code}</code></pre>
    </div>
  );
}

export const SystemOneAPIExamples = ({ appId, agentId, agentName, questions }: SystemOneAPIExamplesProps) => {
  const baseUrl = globalThis.location.origin;
  const endpoint = `${baseUrl}/public/v1/app/${appId}/system-one/${agentId}/evaluate`;

  const curl = `curl -X POST "${endpoint}" \\
  -H "X-API-KEY: your-api-key" \\
  -F "text=Hi, the router has not worked since yesterday" \\
  -F "files=@ticket.pdf"`;

  const python = `import requests

response = requests.post(
    "${endpoint}",
    headers={"X-API-KEY": "your-api-key"},
    data={"text": "Hi, the router has not worked since yesterday"},
    files=[("files", open("ticket.pdf", "rb"))],  # optional: text documents only
)
response.raise_for_status()
for key, answer in response.json()["answers"].items():
    print(key, answer["decision"])`;

  const javascript = `const form = new FormData();
form.append("text", "Hi, the router has not worked since yesterday");
// form.append("files", fileInput.files[0]); // optional: text documents only

const response = await fetch("${endpoint}", {
  method: "POST",
  headers: { "X-API-KEY": "your-api-key" },
  body: form,
});
const { answers } = await response.json();
console.log(answers);`;

  return (
    <div className="mx-auto max-w-4xl space-y-5 p-4">
      <div>
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">API Examples — {agentName}</h2>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Evaluate a text with this agent from your own application. One call returns one typed answer per question.
        </p>
      </div>

      <div className="flex items-start gap-3 rounded-xl bg-blue-50 p-4 text-sm text-blue-800">
        <KeyRound className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <p>Create an API key in the app settings and send it in the <code>X-API-KEY</code> header. The request is multipart: a <code>text</code> field and optional <code>files</code> (text documents; images are rejected).</p>
      </div>

      <CodeBlock title="cURL" code={curl} />
      <CodeBlock title="Python" code={python} />
      <CodeBlock title="JavaScript" code={javascript} />
      <CodeBlock title="Response" code={exampleResponse(questions)} />

      <p className="text-xs text-gray-500">
        <code>decision</code> is <code>null</code> when a choice or score does not reach its minimum probability. <code>state_reduction</code> tells whether the text was summarized or truncated to fit.
      </p>
    </div>
  );
};
