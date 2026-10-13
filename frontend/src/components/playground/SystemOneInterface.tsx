import { useEffect, useRef, useState } from 'react';
import { AlertTriangle, ChevronRight, FileText, Gauge, Loader2, Play, X } from 'lucide-react';
import { apiService } from '../../services/api';
import { promptBudget, type EditorQuestion } from '../../utils/systemOneQuestions';
import { categoryColor, scaleColor, yesNoColor } from '../../utils/systemOneColors';
import type {
  SystemOneAnswer,
  SystemOneQuestion,
  SystemOneResult,
} from '../../types/systemOne';

interface SystemOneInterfaceProps {
  readonly appId: number;
  readonly agentId: number;
  readonly agentName: string;
  /** The agent's questions, to show them in their defined order with their instructions. */
  readonly questions: SystemOneQuestion[];
  /** The agent's per-prompt budget in characters, and whether a summarizing LLM is set (to say what is going on). */
  readonly maxStateChars: number;
  readonly summarizes: boolean;
}

interface Evaluation {
  readonly id: number;
  readonly at: Date;
  readonly preview: string;
  readonly result: SystemOneResult;
}

const TEXT_FILE_ACCEPT = '.pdf,.txt,.md,.csv,.json,.log,.xml,.html';
const percent = (p: number) => `${Math.round(p * 100)}%`;

function isImage(file: File): boolean {
  return file.type.startsWith('image/') || /\.(png|jpe?g|gif|webp|bmp|tiff?|heic|svg)$/i.test(file.name);
}

function ProbabilityBar({ label, value, highlighted, color }: { readonly label: string; readonly value: number; readonly highlighted: boolean; readonly color?: string }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className={`w-32 truncate ${highlighted ? 'font-semibold text-gray-900' : 'text-gray-600'}`} title={label}>{label}</span>
      <div className="h-2 flex-1 rounded-full bg-gray-200" role="progressbar" aria-label={`${label} probability`}
           aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(value * 100)}>
        <div className={`h-2 rounded-full ${color ? '' : highlighted ? 'bg-emerald-500' : 'bg-gray-400'}`}
             style={{ width: percent(value), ...(color ? { backgroundColor: color, opacity: highlighted ? 1 : 0.55 } : {}) }} />
      </div>
      <span className="w-10 text-right tabular-nums text-gray-700">{percent(value)}</span>
    </div>
  );
}

function decisionText(answer: SystemOneAnswer): { text: string; determined: boolean } {
  if (answer.type === 'noul') return { text: answer.decision ? 'Yes' : 'No', determined: true };
  return answer.decision === null ? { text: 'Undetermined', determined: false } : { text: answer.decision, determined: true };
}

/** The playground's own color preference of a score question (undefined for the other types). */
function colorStartOf(question: SystemOneQuestion | undefined): 'green' | 'red' | undefined {
  return question?.type === 'score' ? question.color_start : undefined;
}

function AnswerCard({ questionKey, instructions, answer, colorStart }: { readonly questionKey: string; readonly instructions?: string; readonly answer: SystemOneAnswer; readonly colorStart?: 'green' | 'red' }) {
  const { text, determined } = decisionText(answer);
  // Colors: Yes green / No red; each choice option its own stable color; a score runs green to red (see colorStart).
  const badgeColor = answer.type === 'noul' ? yesNoColor(answer.decision)
    : answer.type === 'choice' ? (answer.choice ? categoryColor(answer.choice) : undefined)
    : scaleColor(answer.level_index ?? 0, Object.keys(answer.probabilities).length || 1, colorStart);
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-gray-900">{questionKey}</p>
          {instructions && <p className="text-xs text-gray-500">{instructions}</p>}
        </div>
        <span className={`rounded-full px-3 py-1 text-sm font-medium text-white ${badgeColor ? '' : determined ? 'bg-emerald-600' : 'bg-gray-500'}`}
              style={badgeColor ? { backgroundColor: badgeColor } : undefined}>
          {text}
        </span>
      </div>

      <div className="mt-3 space-y-1">
        {answer.type === 'noul' && <ProbabilityBar label={`Yes (threshold ${percent(answer.threshold)})`} value={answer.probability} highlighted={answer.decision} color={yesNoColor(true)} />}
        {answer.type === 'choice' && Object.entries(answer.probabilities).map(([option, p]) => (
          <ProbabilityBar key={option} label={option} value={p} highlighted={option === answer.choice} color={categoryColor(option)} />
        ))}
        {answer.type === 'score' && Object.keys(answer.probabilities).map((index, i, all) => (
          <ProbabilityBar key={index} label={`${index} · ${answer.legend[index] ?? ''}`} value={answer.probabilities[index]}
                          highlighted={Number(index) === answer.level_index} color={scaleColor(i, all.length, colorStart)} />
        ))}
      </div>

      {answer.type !== 'noul' && (
        <p className="mt-2 text-xs text-gray-500">
          {answer.type === 'score' && <>Expected level {answer.expected_score.toFixed(2)} · </>}
          <span title="How concentrated the whole distribution is. It is not the accuracy of the answer, and it can be low even when the chosen option is clearly the best.">
            Confidence {answer.confidence.toFixed(2)}
          </span>
          {answer.decision === null && answer.min_probability != null && <> · below the minimum probability ({percent(answer.min_probability)})</>}
        </p>
      )}
    </div>
  );
}

function ReductionNotice({ result }: { readonly result: SystemOneResult }) {
  if (result.state_reduction === 'none') return null;
  const summarized = result.state_reduction === 'summarized';
  const message = (
    <>
      The text was {summarized ? 'summarized' : 'truncated'} before evaluating ({result.original_chars.toLocaleString()} →{' '}
      {result.state_chars.toLocaleString()} characters).
      <br />
      The decisions are based on {summarized ? 'its summary' : 'its first part'}.
    </>
  );
  // Without the text there is nothing to open (an older response): keep the plain notice.
  if (!result.evaluated_text) {
    return (
      <div className="mb-3 flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-800" role="status">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <p>{message}</p>
      </div>
    );
  }
  return (
    <details className="group mb-3 rounded-lg bg-amber-50 text-sm text-amber-800">
      <summary className="flex cursor-pointer list-none items-start gap-2 p-3 [&::-webkit-details-marker]:hidden">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <p className="flex-1">
          {message} <span className="font-medium underline">{summarized ? 'View the summary' : 'View the text that was evaluated'}</span>
        </p>
        <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 transition-transform group-open:rotate-90" aria-hidden="true" />
      </summary>
      <pre className="mx-3 mb-3 max-h-80 overflow-auto whitespace-pre-wrap rounded-lg bg-white p-3 text-xs text-gray-800">{result.evaluated_text}</pre>
    </details>
  );
}

export const SystemOneInterface = ({ appId, agentId, agentName, questions, maxStateChars, summarizes }: SystemOneInterfaceProps) => {
  const [text, setText] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<Evaluation[]>([]);
  const nextId = useRef(1);
  const fileInput = useRef<HTMLInputElement>(null);

  const questionByKey = new Map(questions.map((q) => [q.key, q]));
  // Say what is happening while it runs: a long text goes through the agent's LLM first, which takes seconds.
  const estimatedChars = text.trim().length + files.reduce((sum, f) => sum + f.size, 0);
  const willSummarize = summarizes && estimatedChars > promptBudget(questions as EditorQuestion[], maxStateChars);
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (!running) { setSlow(false); return; }
    const timer = window.setTimeout(() => setSlow(true), 6000);
    return () => window.clearTimeout(timer);
  }, [running]);
  const canRun = !running && (text.trim() !== '' || files.length > 0);

  function addFiles(selected: FileList | null) {
    if (!selected) return;
    const incoming = Array.from(selected);
    const images = incoming.filter(isImage);
    if (images.length > 0) {
      setError(`System One evaluates text only: images are not supported (${images.map((f) => f.name).join(', ')})`);
    } else {
      setError(null);
    }
    setFiles((current) => [...current, ...incoming.filter((f) => !isImage(f))]);
    if (fileInput.current) fileInput.current.value = '';
  }

  async function handleEvaluate() {
    setRunning(true);
    setError(null);
    try {
      const result = await apiService.evaluateSystemOne(appId, agentId, text, files);
      const preview = text.trim() !== '' ? text.trim().slice(0, 80) : files.map((f) => f.name).join(', ');
      setHistory((current) => [{ id: nextId.current++, at: new Date(), preview, result }, ...current]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The evaluation failed');
    } finally {
      setRunning(false);
    }
  }

  const [latest, ...older] = history;

  return (
    <div className="mx-auto max-w-4xl space-y-5 p-4">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-100"><Gauge className="h-5 w-5 text-emerald-600" aria-hidden="true" /></div>
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{agentName}</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400">Paste a text (or attach text documents) and see the answer to each question. Text only.</p>
        </div>
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-4">
        <label htmlFor="so-text" className="mb-1 block text-sm font-medium text-gray-700">Text to evaluate</label>
        <textarea id="so-text" rows={6} value={text} onChange={(e) => setText(e.target.value)}
                  placeholder="Hi, the router has not worked since yesterday and we have an event tomorrow..."
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm placeholder:text-gray-400/70 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500" />

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <input ref={fileInput} id="so-files" type="file" multiple accept={TEXT_FILE_ACCEPT} className="sr-only" onChange={(e) => addFiles(e.target.files)} />
          <label htmlFor="so-files" className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50">
            <FileText className="h-4 w-4" aria-hidden="true" /> Attach documents
          </label>
          {files.map((file, index) => (
            <span key={`${file.name}-${index}`} className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-3 py-1 text-xs text-gray-700">
              {file.name}
              <button type="button" aria-label={`Remove ${file.name}`} className="text-gray-500 hover:text-red-600"
                      onClick={() => setFiles((current) => current.filter((_, i) => i !== index))}>
                <X className="h-3 w-3" aria-hidden="true" />
              </button>
            </span>
          ))}
        </div>

        <div className="mt-4 flex justify-end">
          <button type="button" onClick={() => void handleEvaluate()} disabled={!canRun}
                  className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50">
            {running ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Play className="h-4 w-4" aria-hidden="true" />}
            {running ? (willSummarize ? 'Summarizing...' : 'Evaluating...') : 'Evaluate'}
          </button>
        </div>
      </div>

      {running && (
        <div className="flex items-start gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900" role="status">
          <Loader2 className="mt-0.5 h-5 w-5 shrink-0 animate-spin" aria-hidden="true" />
          <div>
            <p className="font-medium">
              {willSummarize ? 'Summarizing the text before evaluating it...' : 'Evaluating...'}
            </p>
            <p className="text-emerald-800">
              {willSummarize
                ? "The text is longer than the room each question leaves, so the agent's LLM condenses it first. This can take up to a minute."
                : slow && summarizes
                  ? "This is taking longer than usual: long texts are condensed with the agent's LLM first."
                  : 'Asking the System One server.'}
            </p>
          </div>
        </div>
      )}

      <div aria-live="polite">
        {error && <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700" role="alert">{error}</div>}
      </div>

      {latest && (
        <section aria-label="Latest result">
          <h3 className="mb-2 text-sm font-semibold text-gray-700">Result</h3>
          <ReductionNotice result={latest.result} />
          <div className="space-y-3">
            {Object.entries(latest.result.answers).map(([key, answer]) => (
              <AnswerCard key={key} questionKey={key} instructions={questionByKey.get(key)?.instructions} answer={answer} colorStart={colorStartOf(questionByKey.get(key))} />
            ))}
          </div>
          <p className="mt-2 text-xs text-gray-500">
            Model {latest.result.model}
            {latest.result.usage && <> · {latest.result.usage.input_tokens} input tokens</>}
          </p>
        </section>
      )}

      {older.length > 0 && (
        <details className="rounded-xl border border-gray-200 bg-white p-4">
          <summary className="cursor-pointer text-sm font-medium text-gray-700">Previous evaluations ({older.length})</summary>
          <div className="mt-3 space-y-4">
            {older.map((evaluation) => (
              <div key={evaluation.id}>
                <p className="mb-2 text-xs text-gray-500">{evaluation.at.toLocaleTimeString()} · {evaluation.preview}</p>
                <ReductionNotice result={evaluation.result} />
                <div className="space-y-2">
                  {Object.entries(evaluation.result.answers).map(([key, answer]) => (
                    <AnswerCard key={key} questionKey={key} instructions={questionByKey.get(key)?.instructions} answer={answer} colorStart={colorStartOf(questionByKey.get(key))} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
};
