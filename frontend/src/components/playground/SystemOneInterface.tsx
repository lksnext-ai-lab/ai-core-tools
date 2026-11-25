import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { AlertTriangle, ChevronRight, FileText, Gauge, Loader2, Play, X } from 'lucide-react';
import { apiService } from '../../services/api';
import { formatCount, promptBudget, type EditorQuestion } from '../../utils/systemOneQuestions';
import { optionColor, scaleColor, yesNoColor } from '../../utils/systemOneColors';
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
  /** The agent's service, to know whether its provider takes images. */
  readonly serviceId?: number | null;
}

interface Evaluation {
  readonly id: number;
  readonly at: Date;
  readonly preview: string;
  readonly result: SystemOneResult;
}

const TEXT_FILE_ACCEPT = '.pdf,.txt,.md,.csv,.json,.log,.xml,.html';
const percent = (p: number) => `${Math.round(p * 100)}%`;

const formatMs = (ms: number) => (ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`);

const IMAGE_ACCEPT = 'image/png,image/jpeg'; // the formats OpenAI documents for the Decisions API

function isSupportedImage(file: File): boolean {
  return /^image\/(png|jpe?g)$/i.test(file.type) || /\.(png|jpe?g)$/i.test(file.name);
}

function isImage(file: File): boolean {
  return file.type.startsWith('image/') || /\.(png|jpe?g|gif|webp|bmp|tiff?|heic|svg)$/i.test(file.name);
}

function ProbabilityBar({ label, value, highlighted, color }: { readonly label: string; readonly value: number; readonly highlighted: boolean; readonly color?: string }) {
  const { t } = useTranslation('common');
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className={`w-32 truncate ${highlighted ? 'font-semibold text-gray-900' : 'text-gray-600'}`} title={label}>{label}</span>
      <div className="h-2 flex-1 rounded-full bg-gray-200" role="progressbar" aria-label={t('systemOne.playground.probabilityAria', { label })}
           aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(value * 100)}>
        <div className={`h-2 rounded-full ${color ? '' : highlighted ? 'bg-emerald-500' : 'bg-gray-400'}`}
             style={{ width: percent(value), ...(color ? { backgroundColor: color, opacity: highlighted ? 1 : 0.55 } : {}) }} />
      </div>
      <span className="w-10 text-right tabular-nums text-gray-700">{percent(value)}</span>
    </div>
  );
}

function decisionText(answer: SystemOneAnswer, t: TFunction): { text: string; determined: boolean } {
  if (answer.type === 'noul') return { text: answer.decision ? t('systemOne.playground.yes') : t('systemOne.playground.no'), determined: true };
  return answer.decision === null ? { text: t('systemOne.playground.undetermined'), determined: false } : { text: answer.decision, determined: true };
}

function AnswerCard({ questionKey, instructions, answer, question }: { readonly questionKey: string; readonly instructions?: string; readonly answer: SystemOneAnswer; readonly question?: SystemOneQuestion }) {
  const { t } = useTranslation('common');
  const colorStart = question?.type === 'score' ? question.color_start : undefined;
  const colorOfOption = (name: string) => optionColor(question?.type === 'choice' ? question.criteria.find((o) => o.key === name) : undefined, name);
  const { text, determined } = decisionText(answer, t);
  // Colors: Yes green / No red; each choice option its own stable color; a score runs green to red (see colorStart).
  const badgeColor = answer.type === 'noul' ? yesNoColor(answer.decision)
    : answer.type === 'choice' ? (answer.choice ? colorOfOption(answer.choice) : undefined)
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
        {answer.type === 'noul' && <ProbabilityBar label={t('systemOne.playground.yesThreshold', { threshold: percent(answer.threshold) })} value={answer.probability} highlighted={answer.decision} color={yesNoColor(true)} />}
        {answer.type === 'choice' && Object.entries(answer.probabilities).map(([option, p]) => (
          <ProbabilityBar key={option} label={option} value={p} highlighted={option === answer.choice} color={colorOfOption(option)} />
        ))}
        {answer.type === 'score' && Object.keys(answer.probabilities).map((index, i, all) => (
          <ProbabilityBar key={index} label={`${index} · ${answer.legend[index] ?? ''}`} value={answer.probabilities[index]}
                          highlighted={Number(index) === answer.level_index} color={scaleColor(i, all.length, colorStart)} />
        ))}
      </div>

      {answer.type !== 'noul' && (
        <p className="mt-2 text-xs text-gray-500">
          {answer.type === 'score' && <>{t('systemOne.playground.expectedLevel', { value: answer.expected_score.toFixed(2) })} · </>}
          <span title={t('systemOne.playground.confidenceHint')}>
            {t('systemOne.playground.confidence', { value: answer.confidence.toFixed(2) })}
          </span>
          {answer.decision === null && answer.min_probability != null && <> · {t('systemOne.playground.belowMinimum', { value: percent(answer.min_probability) })}</>}
        </p>
      )}
    </div>
  );
}

function ReductionNotice({ result }: { readonly result: SystemOneResult }) {
  const { t } = useTranslation('common');
  if (result.state_reduction === 'none') return null;
  const summarized = result.state_reduction === 'summarized';
  const message = t(summarized ? 'systemOne.playground.summarizedNotice' : 'systemOne.playground.truncatedNotice', {
    original: formatCount(result.original_chars),
    used: formatCount(result.state_chars),
  });
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
          {message}
          <br />
          <span className="font-medium underline">{summarized ? t('systemOne.playground.viewSummary') : t('systemOne.playground.viewEvaluatedText')}</span>
        </p>
        <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 transition-transform group-open:rotate-90" aria-hidden="true" />
      </summary>
      <pre className="mx-3 mb-3 max-h-80 overflow-auto whitespace-pre-wrap rounded-lg bg-white p-3 text-xs text-gray-800">{result.evaluated_text}</pre>
    </details>
  );
}

export const SystemOneInterface = ({ appId, agentId, agentName, questions, maxStateChars, summarizes, serviceId }: SystemOneInterfaceProps) => {
  const { t } = useTranslation('common');
  const [acceptsImages, setAcceptsImages] = useState(false);
  useEffect(() => {
    if (serviceId == null) return;
    apiService.getSystemOneService(appId, serviceId).then((svc) => setAcceptsImages(!!svc.supports_images)).catch(() => setAcceptsImages(false));
  }, [appId, serviceId]);
  const [text, setText] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<Evaluation[]>([]);
  const nextId = useRef(1);
  const fileInput = useRef<HTMLInputElement>(null);

  const questionByKey = new Map(questions.map((q) => [q.key, q]));
  // Say what is happening while it runs: a long text goes through the agent's LLM first, which takes seconds.
  // Images go to the model as they are: they are never summarized, so they do not count toward the text budget.
  const estimatedChars = text.trim().length + files.filter((f) => !isImage(f)).reduce((sum, f) => sum + f.size, 0);
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
    const rejected = incoming.filter((f) => isImage(f) && !(acceptsImages && isSupportedImage(f)));
    setError(rejected.length > 0
      ? t(acceptsImages ? 'systemOne.playground.imagesPngJpeg' : 'systemOne.playground.imagesNotSupported', { files: rejected.map((f) => f.name).join(', ') })
      : null);
    setFiles((current) => [...current, ...incoming.filter((f) => !rejected.includes(f))]);
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
      setError(err instanceof Error ? err.message : t('systemOne.playground.evaluationFailed'));
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
          <p className="text-sm text-gray-600 dark:text-gray-400">{t(acceptsImages ? 'systemOne.playground.descriptionWithImages' : 'systemOne.playground.descriptionTextOnly')}</p>
        </div>
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-4">
        <label htmlFor="so-text" className="mb-1 block text-sm font-medium text-gray-700">{t('systemOne.playground.textLabel')}</label>
        <textarea id="so-text" rows={6} value={text} onChange={(e) => setText(e.target.value)}
                  placeholder={t('systemOne.playground.textPlaceholder')}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm placeholder:text-gray-400/70 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500" />

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <input ref={fileInput} id="so-files" type="file" multiple accept={acceptsImages ? `${TEXT_FILE_ACCEPT},${IMAGE_ACCEPT}` : TEXT_FILE_ACCEPT} className="sr-only" onChange={(e) => addFiles(e.target.files)} />
          <label htmlFor="so-files" className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50">
            <FileText className="h-4 w-4" aria-hidden="true" /> {t('systemOne.playground.attachDocuments')}
          </label>
          {files.map((file, index) => (
            <span key={`${file.name}-${index}`} className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-3 py-1 text-xs text-gray-700">
              {file.name}
              <button type="button" aria-label={t('systemOne.playground.removeFile', { name: file.name })} className="text-gray-500 hover:text-red-600"
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
            {running ? (willSummarize ? t('systemOne.playground.summarizing') : t('systemOne.playground.evaluating')) : t('systemOne.playground.evaluate')}
          </button>
        </div>
      </div>

      {running && (
        <div className="flex items-start gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900" role="status">
          <Loader2 className="mt-0.5 h-5 w-5 shrink-0 animate-spin" aria-hidden="true" />
          <div>
            <p className="font-medium">
              {willSummarize ? t('systemOne.playground.summarizingStatus') : t('systemOne.playground.evaluating')}
            </p>
            <p className="text-emerald-800">
              {willSummarize
                ? t('systemOne.playground.summarizingNote')
                : slow && summarizes
                  ? t('systemOne.playground.slowNote')
                  : t('systemOne.playground.askingServer')}
            </p>
          </div>
        </div>
      )}

      <div aria-live="polite">
        {error && <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700" role="alert">{error}</div>}
      </div>

      {latest && (
        <section aria-label={t('systemOne.playground.latestResult')}>
          <h3 className="mb-2 text-sm font-semibold text-gray-700">{t('systemOne.playground.result')}</h3>
          <ReductionNotice result={latest.result} />
          <div className="space-y-3">
            {Object.entries(latest.result.answers).map(([key, answer]) => (
              <AnswerCard key={key} questionKey={key} instructions={questionByKey.get(key)?.instructions} answer={answer} question={questionByKey.get(key)} />
            ))}
          </div>
          <p className="mt-2 text-xs text-gray-500">
            {t('systemOne.playground.model', { model: latest.result.model })}
            {latest.result.usage && <> · {t('systemOne.playground.inputTokens', { count: latest.result.usage.input_tokens })}</>}
            {latest.result.timings && (
              <>
                {' · '}
                {latest.result.timings.summarization_ms != null
                  ? t('systemOne.playground.timingsFull', {
                    summarization: formatMs(latest.result.timings.summarization_ms),
                    evaluation: formatMs(latest.result.timings.evaluation_ms),
                  })
                  : t('systemOne.playground.timingsEvaluation', { evaluation: formatMs(latest.result.timings.evaluation_ms) })}
              </>
            )}
          </p>
        </section>
      )}

      {older.length > 0 && (
        <details className="rounded-xl border border-gray-200 bg-white p-4">
          <summary className="cursor-pointer text-sm font-medium text-gray-700">{t('systemOne.playground.previous', { count: older.length })}</summary>
          <div className="mt-3 space-y-4">
            {older.map((evaluation) => (
              <div key={evaluation.id}>
                <p className="mb-2 text-xs text-gray-500">{evaluation.at.toLocaleTimeString()} · {evaluation.preview}</p>
                <ReductionNotice result={evaluation.result} />
                <div className="space-y-2">
                  {Object.entries(evaluation.result.answers).map(([key, answer]) => (
                    <AnswerCard key={key} questionKey={key} instructions={questionByKey.get(key)?.instructions} answer={answer} question={questionByKey.get(key)} />
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
