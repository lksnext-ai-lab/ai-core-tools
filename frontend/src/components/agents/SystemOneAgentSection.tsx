import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, Gauge } from 'lucide-react';
import SystemOneQuestionsEditor from './SystemOneQuestionsEditor';
import { validateMaxStateChars, type EditorQuestion } from '../../utils/systemOneQuestions';
import { textLengthHint, type QuestionLimits } from '../../utils/systemOneLimits';

const inputClass =
  'w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all duration-200';

interface ServiceOption {
  readonly service_id: number;
  readonly name: string;
}

interface SystemOneAgentSectionProps {
  readonly appId: string;
  readonly systemOneServices: ServiceOption[];
  readonly aiServices: ServiceOption[];
  readonly serviceId?: number;
  readonly onServiceChange: (id: number | undefined) => void;
  readonly summarizationServiceId?: number;
  readonly onSummarizationChange: (id: number | undefined) => void;
  readonly maxStateChars: number;
  readonly onMaxStateCharsChange: (value: number) => void;
  readonly isTool: boolean;
  readonly onIsToolChange: (value: boolean) => void;
  readonly questions: EditorQuestion[];
  readonly onQuestionsChange: (questions: EditorQuestion[]) => void;
  readonly limits: QuestionLimits;
  readonly generalProblems: string[];
  readonly problemsByQuestion: string[][];
}

const toId = (raw: string): number | undefined => (raw === '' ? undefined : Number(raw));

function SystemOneAgentSection(props: SystemOneAgentSectionProps) {
  // What is typed is kept as text so the field can be emptied (a number input bound to Number('') shows a stuck 0).
  const [maxCharsDraft, setMaxCharsDraft] = useState(String(props.maxStateChars));
  useEffect(() => {
    // Follow the value when it changes from outside (the agent loads after the first render), never while typing.
    if (Number(maxCharsDraft) !== props.maxStateChars && !(maxCharsDraft === '' && Number.isNaN(props.maxStateChars))) {
      setMaxCharsDraft(Number.isNaN(props.maxStateChars) ? '' : String(props.maxStateChars));
    }
  }, [props.maxStateChars]);
  const maxCharsProblem = validateMaxStateChars(props.maxStateChars);
  const lengthHint = textLengthHint(props.maxStateChars, props.limits.maxPromptTokens);
  const { appId, systemOneServices, aiServices } = props;

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
        <div className="flex items-center mb-6">
          <div className="w-10 h-10 bg-emerald-100 rounded-xl flex items-center justify-center mr-4">
            <Gauge className="w-5 h-5 text-emerald-600" aria-hidden="true" />
          </div>
          <div>
            <h3 className="text-xl font-semibold text-gray-900">System One</h3>
            <p className="text-sm text-gray-600">
              Answers closed questions about a text with probabilities. Text only: images are not supported.
            </p>
          </div>
        </div>

        {systemOneServices.length === 0 && (
          <div className="mb-6 flex items-start gap-3 rounded-xl bg-amber-50 p-4 text-sm text-amber-800" role="alert">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <p>
              This app has no System One service yet.{' '}
              <Link className="font-medium underline" to={`/apps/${appId}/settings/system-one-services`}>Create one in Settings</Link>{' '}
              and come back.
            </p>
          </div>
        )}

        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          <div>
            <label htmlFor="so-service" className="block text-sm font-medium text-gray-700 mb-2">System One service *</label>
            <select id="so-service" className={inputClass} value={props.serviceId ?? ''} required
                    onChange={(e) => props.onServiceChange(toId(e.target.value))}>
              <option value="">Select a service...</option>
              {systemOneServices.map((s) => <option key={s.service_id} value={s.service_id}>{s.name}</option>)}
            </select>
            {props.serviceId == null && systemOneServices.length > 0 && (
              <p className="mt-1 text-xs text-amber-700">
                No service selected (it may have been deleted): this agent cannot evaluate anything until you choose one.
              </p>
            )}
          </div>

          <div>
            <label htmlFor="so-summarizer" className="block text-sm font-medium text-gray-700 mb-2">
              Summarization LLM <span className="font-normal text-gray-500">(optional)</span>
            </label>
            <select id="so-summarizer" className={inputClass} value={props.summarizationServiceId ?? ''}
                    onChange={(e) => props.onSummarizationChange(toId(e.target.value))}>
              <option value="">None: truncate long texts</option>
              {aiServices.map((s) => <option key={s.service_id} value={s.service_id}>{s.name}</option>)}
            </select>
            <p className="mt-1 text-xs text-gray-500">Used to shorten a text that does not fit. Without it the text is cut. The result always says which happened.</p>
          </div>

          <div>
            <label htmlFor="so-max-chars" className="block text-sm font-medium text-gray-700 mb-2">Maximum text length (characters)</label>
            <input id="so-max-chars" type="number" min={500} step={100} className={inputClass} value={maxCharsDraft}
                   aria-invalid={maxCharsProblem !== null} aria-describedby={maxCharsProblem ? 'so-max-chars-error' : 'so-max-chars-hint'}
                   onChange={(e) => {
                     setMaxCharsDraft(e.target.value);
                     props.onMaxStateCharsChange(e.target.value.trim() === '' ? Number.NaN : Number(e.target.value));
                   }} />
            {maxCharsProblem
              ? <p id="so-max-chars-error" role="alert" className="mt-1 text-xs text-red-600">{maxCharsProblem}</p>
              : <p id="so-max-chars-hint" className="mt-1 text-xs text-gray-500">At least 500. The model works best with shorter texts (around 6000).</p>}
            {!maxCharsProblem && lengthHint && <p className="mt-1 text-xs text-amber-700">{lengthHint}</p>}
          </div>

          <div className="flex items-start">
            <input id="so-is-tool" type="checkbox" className="mt-1 h-4 w-4 rounded border-gray-300 text-blue-600" checked={props.isTool}
                   onChange={(e) => props.onIsToolChange(e.target.checked)} />
            <div className="ml-3">
              <label htmlFor="so-is-tool" className="text-sm font-medium text-gray-900">Use as a tool</label>
              <p className="text-xs text-gray-500">Other agents can call it to classify, judge or decide over a text.</p>
            </div>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
        <SystemOneQuestionsEditor questions={props.questions} onChange={props.onQuestionsChange} limits={props.limits}
                                  generalProblems={props.generalProblems}
                                  problemsByQuestion={props.problemsByQuestion} />
      </div>
    </div>
  );
}

export default SystemOneAgentSection;
