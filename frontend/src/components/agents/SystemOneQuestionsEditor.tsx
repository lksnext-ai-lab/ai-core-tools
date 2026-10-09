import { useState } from 'react';
import { ArrowDown, ArrowUp, GripVertical, Plus, Trash2 } from 'lucide-react';
import { randomId } from '../../utils/randomId';
import {
  MIN_OPTIONS,
  changeQuestionType,
  newQuestion,
  reorder,
  type EditorQuestion,
} from '../../utils/systemOneQuestions';
import type { QuestionLimits } from '../../utils/systemOneLimits';
import type { ChoiceOption, SystemOneQuestionType } from '../../types/systemOne';

// Placeholders are deliberately simple English examples, in light gray, so the expected shape of each box is obvious.
const inputClass =
  'w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 placeholder:text-gray-400/70';
const smallButton =
  'p-1.5 rounded-lg text-gray-500 hover:bg-gray-100 hover:text-gray-800 disabled:opacity-30 disabled:hover:bg-transparent';

const INSTRUCTION_EXAMPLE: Record<SystemOneQuestionType, string> = {
  noul: 'Is this message urgent?',
  choice: 'Which department should handle this?',
  score: 'How angry is the customer?',
};
const LEVEL_EXAMPLES = ['Calm', 'Annoyed', 'Angry', 'Furious'];
const TYPE_LABEL: Record<SystemOneQuestionType, string> = { noul: 'Yes / No', choice: 'Choice', score: 'Score' };

interface SystemOneQuestionsEditorProps {
  readonly questions: EditorQuestion[];
  readonly onChange: (questions: EditorQuestion[]) => void;
  /** About the list as a whole. */
  /** What the chosen server accepts (undefined fields = unknown, no upper limit is enforced). */
  readonly limits: QuestionLimits;
  readonly generalProblems: string[];
  /** Per question, same order: shown right above the question they belong to. */
  readonly problemsByQuestion: string[][];
}

function parseNumber(raw: string): number | undefined {
  return raw.trim() === '' ? undefined : Number(raw);
}

function SystemOneQuestionsEditor({ questions, onChange, limits, generalProblems, problemsByQuestion }: SystemOneQuestionsEditorProps) {
  const [announcement, setAnnouncement] = useState('');
  // Drag and drop: only the grip starts a drag (so text can still be selected inside the fields).
  const [armed, setArmed] = useState<number | null>(null);
  const [dragging, setDragging] = useState<number | null>(null);
  const [over, setOver] = useState<number | null>(null);
  const endDrag = () => { setArmed(null); setDragging(null); setOver(null); };
  const drop = (target: number) => {
    if (dragging !== null && dragging !== target) {
      onChange(reorder(questions, dragging, target));
      setAnnouncement(`Question moved to position ${target + 1} of ${questions.length}`);
    }
    endDrag();
  };
  const optionRange = limits.maxOptions === undefined ? `${MIN_OPTIONS} or more` : `${MIN_OPTIONS}-${limits.maxOptions}`;
  const optionsFull = (count: number) => limits.maxOptions !== undefined && count >= limits.maxOptions;
  const update = (index: number, next: EditorQuestion) => onChange(questions.map((q, i) => (i === index ? next : q)));
  const remove = (index: number) => onChange(questions.filter((_, i) => i !== index));
  // After a move the control that had the focus is re-created in its new place (or becomes disabled at an end):
  // put the focus back so the keyboard can keep moving the same question.
  const move = (index: number, delta: -1 | 1, focusId?: string) => {
    const target = index + delta;
    if (target < 0 || target >= questions.length) return;
    const next = [...questions];
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
    setAnnouncement(`Question moved to position ${target + 1} of ${questions.length}`);
    const questionId = questions[index]._id ?? String(index);
    window.setTimeout(() => {
      const wanted = focusId ? document.getElementById(focusId) : null;
      const fallback = document.getElementById(`${questionId}-${delta < 0 ? 'down' : 'up'}`);
      ((wanted as HTMLButtonElement | null)?.disabled ? fallback : wanted ?? fallback)?.focus();
    }, 0);
  };
  const moveWithKeyboard = (event: React.KeyboardEvent, index: number) => {
    if (!event.altKey || (event.key !== 'ArrowUp' && event.key !== 'ArrowDown')) return;
    event.preventDefault();
    move(index, event.key === 'ArrowUp' ? -1 : 1, (event.target as HTMLElement).id || undefined);
  };
  const add = (type: SystemOneQuestionType) => onChange([...questions, newQuestion(type, randomId())]);

  return (
    <div>
      <div className="mb-3 flex items-end justify-between">
        <div>
          <h4 className="text-base font-semibold text-gray-900">Questions</h4>
          <p className="text-sm text-gray-600">
            The agent answers all of them for every text. Keys and option names are part of what the model reads: make them descriptive.
            The order only decides how they are listed; each question is answered on its own. Drag a question by its handle to
            reorder (or use the arrows, or Alt+↑ / Alt+↓ inside a question).
          </p>
        </div>
        <span className="text-sm text-gray-500" aria-live="polite">{questions.length}{limits.maxQuestions === undefined ? '' : ` / ${limits.maxQuestions}`}</span>
      </div>

      <p className="sr-only" aria-live="polite">{announcement}</p>

      {generalProblems.length > 0 && (
        <ul className="mb-4 list-disc space-y-1 rounded-lg bg-red-50 p-3 pl-7 text-sm text-red-700" role="alert">
          {generalProblems.map((p) => <li key={p}>{p}</li>)}
        </ul>
      )}

      <div className="space-y-4">
        {questions.map((question, index) => {
          const id = question._id ?? String(index);
          const own = problemsByQuestion[index] ?? [];
          const describedBy = own.length > 0 ? `${id}-problems` : undefined;
          return (
            <fieldset key={id} onKeyDown={(e) => moveWithKeyboard(e, index)}
                      draggable={armed === index}
                      onDragStart={(e) => { setDragging(index); e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', id); }}
                      onDragOver={(e) => { if (dragging !== null) { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; setOver(index); } }}
                      onDrop={(e) => { e.preventDefault(); drop(index); }}
                      onDragEnd={endDrag}
                      className={`rounded-xl border bg-gray-50 p-4 transition-shadow ${own.length > 0 ? 'border-red-300' : 'border-gray-200'} ${
                        dragging === index ? 'opacity-50' : ''} ${over === index && dragging !== null && dragging !== index ? 'ring-2 ring-blue-400' : ''}`}>
              <legend className="px-2 text-sm font-medium text-gray-700">
                <span className="inline-flex items-center gap-1">
                  <span
                    className="cursor-grab select-none rounded p-0.5 text-gray-400 hover:bg-gray-200 hover:text-gray-700 active:cursor-grabbing"
                    title="Drag to reorder"
                    aria-hidden="true"
                    onMouseDown={() => setArmed(index)}
                    onMouseUp={() => setArmed(null)}
                  >
                    <GripVertical className="h-4 w-4" />
                  </span>
                  Question {index + 1}
                </span>
              </legend>

              {own.length > 0 && (
                <ul id={`${id}-problems`} data-question-problem className="mb-3 list-disc space-y-1 rounded-lg bg-red-50 p-3 pl-7 text-sm text-red-700" role="alert">
                  {own.map((p) => <li key={p}>{p}</li>)}
                </ul>
              )}

              <div className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_12rem_auto]">
                <div>
                  <label htmlFor={`${id}-key`} className="mb-1 block text-xs font-medium text-gray-600">Key</label>
                  <input id={`${id}-key`} aria-describedby={describedBy} className={inputClass} value={question.key} placeholder="is_urgent"
                         onChange={(e) => update(index, { ...question, key: e.target.value })} />
                </div>
                <div>
                  <label htmlFor={`${id}-type`} className="mb-1 block text-xs font-medium text-gray-600">Type</label>
                  <select id={`${id}-type`} className={inputClass} value={question.type}
                          onChange={(e) => update(index, changeQuestionType(question, e.target.value as SystemOneQuestionType))}>
                    {(Object.keys(TYPE_LABEL) as SystemOneQuestionType[]).map((t) => <option key={t} value={t}>{TYPE_LABEL[t]}</option>)}
                  </select>
                </div>
                <div className="flex items-end gap-1">
                  <button type="button" id={`${id}-up`} className={smallButton} aria-label={`Move question ${index + 1} up`} disabled={index === 0} onClick={() => move(index, -1, `${id}-up`)}>
                    <ArrowUp className="h-4 w-4" aria-hidden="true" />
                  </button>
                  <button type="button" id={`${id}-down`} className={smallButton} aria-label={`Move question ${index + 1} down`} disabled={index === questions.length - 1} onClick={() => move(index, 1, `${id}-down`)}>
                    <ArrowDown className="h-4 w-4" aria-hidden="true" />
                  </button>
                  <button type="button" className={`${smallButton} hover:text-red-600`} aria-label={`Remove question ${index + 1}`} onClick={() => remove(index)}>
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                  </button>
                </div>
              </div>

              <div className="mt-3">
                <label htmlFor={`${id}-instructions`} className="mb-1 block text-xs font-medium text-gray-600">Instructions</label>
                <input id={`${id}-instructions`} className={inputClass} value={question.instructions}
                       aria-describedby={describedBy}
                       placeholder={INSTRUCTION_EXAMPLE[question.type]}
                       onChange={(e) => update(index, { ...question, instructions: e.target.value })} />
              </div>

              {question.type === 'noul' && (
                <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-3">
                  <div>
                    <label htmlFor={`${id}-yes`} className="mb-1 block text-xs font-medium text-gray-600">Yes means <span className="font-normal">(optional)</span></label>
                    <input id={`${id}-yes`} className={inputClass} placeholder="Needs an answer today" value={question.criteria?.true ?? ''}
                           onChange={(e) => update(index, { ...question, criteria: { true: e.target.value, false: question.criteria?.false ?? '' } })} />
                  </div>
                  <div>
                    <label htmlFor={`${id}-no`} className="mb-1 block text-xs font-medium text-gray-600">No means <span className="font-normal">(optional)</span></label>
                    <input id={`${id}-no`} className={inputClass} placeholder="Can wait" value={question.criteria?.false ?? ''}
                           onChange={(e) => update(index, { ...question, criteria: { true: question.criteria?.true ?? '', false: e.target.value } })} />
                  </div>
                  <div>
                    <label htmlFor={`${id}-threshold`} className="mb-1 block text-xs font-medium text-gray-600">Threshold for "yes" <span className="font-normal">(optional)</span></label>
                    <input id={`${id}-threshold`} type="number" min={0} max={1} step={0.05} className={inputClass} placeholder="0.5"
                           value={question.threshold ?? ''} onChange={(e) => update(index, { ...question, threshold: parseNumber(e.target.value) })} />
                    <p className="mt-1 text-xs text-gray-500">Empty = 0.5. "Yes" when the probability reaches it.</p>
                  </div>
                </div>
              )}

              {question.type === 'choice' && (
                <div className="mt-3">
                  <p className="mb-1 text-xs font-medium text-gray-600">Options ({optionRange})</p>
                  <div className="space-y-2">
                    {question.criteria.map((option: ChoiceOption, optionIndex) => (
                      <div key={`${id}-o${optionIndex}`} className="grid grid-cols-[1fr_2fr_auto] gap-2">
                        <input aria-label={`Option ${optionIndex + 1} name`} className={inputClass} placeholder="billing" value={option.key}
                               onChange={(e) => update(index, { ...question, criteria: question.criteria.map((o, i) => (i === optionIndex ? { ...o, key: e.target.value } : o)) })} />
                        <input aria-label={`Option ${optionIndex + 1} description`} className={inputClass} placeholder="Invoices, payments, refunds" value={option.description ?? ''}
                               onChange={(e) => update(index, { ...question, criteria: question.criteria.map((o, i) => (i === optionIndex ? { ...o, description: e.target.value } : o)) })} />
                        <button type="button" className={`${smallButton} hover:text-red-600`} aria-label={`Remove option ${optionIndex + 1}`} disabled={question.criteria.length <= MIN_OPTIONS}
                                onClick={() => update(index, { ...question, criteria: question.criteria.filter((_, i) => i !== optionIndex) })}>
                          <Trash2 className="h-4 w-4" aria-hidden="true" />
                        </button>
                      </div>
                    ))}
                  </div>
                  <button type="button" className="mt-2 inline-flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800 disabled:opacity-40" disabled={optionsFull(question.criteria.length)}
                          onClick={() => update(index, { ...question, criteria: [...question.criteria, { key: '', description: '' }] })}>
                    <Plus className="h-4 w-4" aria-hidden="true" /> Add option
                  </button>
                </div>
              )}

              {question.type === 'score' && (
                <div className="mt-3">
                  <p className="mb-1 text-xs font-medium text-gray-600">Levels, from lowest to highest ({optionRange})</p>
                  <div className="space-y-2">
                    {question.criteria.map((level, levelIndex) => (
                      <div key={`${id}-l${levelIndex}`} className="grid grid-cols-[auto_1fr_auto] items-center gap-2">
                        <span className="w-6 text-center text-xs text-gray-500">{levelIndex}</span>
                        <input aria-label={`Level ${levelIndex} description`} className={inputClass} placeholder={LEVEL_EXAMPLES[levelIndex] ?? `Level ${levelIndex}`} value={level}
                               onChange={(e) => update(index, { ...question, criteria: question.criteria.map((l, i) => (i === levelIndex ? e.target.value : l)) })} />
                        <button type="button" className={`${smallButton} hover:text-red-600`} aria-label={`Remove level ${levelIndex}`} disabled={question.criteria.length <= MIN_OPTIONS}
                                onClick={() => update(index, { ...question, criteria: question.criteria.filter((_, i) => i !== levelIndex) })}>
                          <Trash2 className="h-4 w-4" aria-hidden="true" />
                        </button>
                      </div>
                    ))}
                  </div>
                  <button type="button" className="mt-2 inline-flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800 disabled:opacity-40" disabled={optionsFull(question.criteria.length)}
                          onClick={() => update(index, { ...question, criteria: [...question.criteria, ''] })}>
                    <Plus className="h-4 w-4" aria-hidden="true" /> Add level
                  </button>
                </div>
              )}

              {question.type !== 'noul' && (
                <div className="mt-3 max-w-xs">
                  <label htmlFor={`${id}-minp`} className="mb-1 block text-xs font-medium text-gray-600">
                    Minimum probability <span className="font-normal">(optional)</span>
                  </label>
                  <input id={`${id}-minp`} type="number" min={0} max={1} step={0.05} className={inputClass} placeholder="no minimum" value={question.min_probability ?? ''}
                         onChange={(e) => update(index, { ...question, min_probability: parseNumber(e.target.value) })} />
                  <p className="mt-1 text-xs text-gray-500">Below this probability the decision is left empty. Empty field = always decide.</p>
                </div>
              )}
            </fieldset>
          );
        })}
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {(Object.keys(TYPE_LABEL) as SystemOneQuestionType[]).map((type) => (
          <button key={type} type="button" onClick={() => add(type)} disabled={limits.maxQuestions !== undefined && questions.length >= limits.maxQuestions}
                  className="inline-flex items-center gap-1 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-40">
            <Plus className="h-4 w-4" aria-hidden="true" /> {TYPE_LABEL[type]} question
          </button>
        ))}
      </div>
    </div>
  );
}

export default SystemOneQuestionsEditor;
