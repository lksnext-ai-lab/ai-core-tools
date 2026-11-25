import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowDown, ArrowUp, GripVertical, Plus, Trash2 } from 'lucide-react';
import { randomId } from '../../utils/randomId';
import DecimalInput from './DecimalInput';
import { optionColor, scaleColor } from '../../utils/systemOneColors';
import {
  MIN_OPTIONS,
  changeQuestionType,
  newQuestion,
  reorder,
  type EditorQuestion,
} from '../../utils/systemOneQuestions';
import type { QuestionLimits } from '../../utils/systemOneLimits';
import type { ChoiceOption, SystemOneQuestionType } from '../../types/systemOne';

// Placeholders are deliberately simple examples, in light gray, so the expected shape of each box is obvious.
const inputClass =
  'w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 placeholder:text-gray-400/70';
const smallButton =
  'p-1.5 rounded-lg text-gray-500 hover:bg-gray-100 hover:text-gray-800 disabled:opacity-30 disabled:hover:bg-transparent';

const INSTRUCTION_EXAMPLE_KEY: Record<SystemOneQuestionType, string> = {
  noul: 'systemOne.questions.exampleYesNo',
  choice: 'systemOne.questions.exampleChoice',
  score: 'systemOne.questions.exampleScore',
};
const TYPE_LABEL_KEY: Record<SystemOneQuestionType, string> = {
  noul: 'systemOne.questions.typeYesNo',
  choice: 'systemOne.questions.typeChoice',
  score: 'systemOne.questions.typeScore',
};
const ADD_LABEL_KEY: Record<SystemOneQuestionType, string> = {
  noul: 'systemOne.questions.addYesNo',
  choice: 'systemOne.questions.addChoice',
  score: 'systemOne.questions.addScore',
};
const QUESTION_TYPES = Object.keys(TYPE_LABEL_KEY) as SystemOneQuestionType[];
const LEVEL_EXAMPLE_COUNT = 4;

interface SystemOneQuestionsEditorProps {
  readonly questions: EditorQuestion[];
  readonly onChange: (questions: EditorQuestion[]) => void;
  /** What the chosen server accepts (undefined fields = unknown, no upper limit is enforced). */
  readonly limits: QuestionLimits;
  readonly generalProblems: string[];
  /** Per question, same order: shown right above the question they belong to. */
  readonly problemsByQuestion: string[][];
}

function SystemOneQuestionsEditor({ questions, onChange, limits, generalProblems, problemsByQuestion }: SystemOneQuestionsEditorProps) {
  const { t } = useTranslation('common');
  const [announcement, setAnnouncement] = useState('');
  // Drag and drop: only the grip starts a drag (so text can still be selected inside the fields).
  const [armed, setArmed] = useState<number | null>(null);
  const [dragging, setDragging] = useState<number | null>(null);
  const [over, setOver] = useState<number | null>(null);
  const endDrag = () => { setArmed(null); setDragging(null); setOver(null); };
  const drop = (target: number) => {
    if (dragging !== null && dragging !== target) {
      onChange(reorder(questions, dragging, target));
      setAnnouncement(t('systemOne.questions.moved', { position: target + 1, total: questions.length }));
    }
    endDrag();
  };
  const optionRange = limits.maxOptions === undefined ? t('systemOne.questions.rangeOrMore', { min: MIN_OPTIONS }) : `${MIN_OPTIONS}-${limits.maxOptions}`;
  const optionsFull = (count: number) => limits.maxOptions !== undefined && count >= limits.maxOptions;
  const update = (index: number, next: EditorQuestion) => onChange(questions.map((q, i) => (i === index ? next : q)));
  const remove = (index: number) => onChange(questions.filter((_, i) => i !== index));
  // After a move the control that had the focus is re-created in its new place (or becomes disabled at an end):
  // put the focus back so the keyboard can keep moving the same question.
  const move = (index: number, delta: -1 | 1, focusId?: string) => {
    const target = index + delta;
    if (target < 0 || target >= questions.length) return;
    onChange(reorder(questions, index, target));
    setAnnouncement(t('systemOne.questions.moved', { position: target + 1, total: questions.length }));
    const questionId = questions[index]._id ?? String(index);
    window.setTimeout(() => {
      const wanted = focusId ? document.getElementById(focusId) : null;
      const fallback = document.getElementById(`${questionId}-${delta < 0 ? 'down' : 'up'}`);
      ((wanted as HTMLButtonElement | null)?.disabled ? fallback : wanted ?? fallback)?.focus();
    }, 0);
  };
  const add = (type: SystemOneQuestionType) => onChange([...questions, newQuestion(type, randomId())]);

  return (
    <div>
      <div className="mb-3 flex items-end justify-between gap-4">
        <div className="min-w-0">
          <h4 className="text-base font-semibold text-gray-900">{t('systemOne.questions.title')}</h4>
          <p className="text-sm text-gray-600">
            {t('systemOne.questions.help')}
          </p>
        </div>
        <span className="shrink-0 whitespace-nowrap text-sm text-gray-500" aria-live="polite">{questions.length}{limits.maxQuestions === undefined ? '' : ` / ${limits.maxQuestions}`}</span>
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
            <fieldset key={id}
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
                    title={t('systemOne.questions.dragTitle')}
                    aria-hidden="true"
                    onMouseDown={() => setArmed(index)}
                    onMouseUp={() => setArmed(null)}
                  >
                    <GripVertical className="h-4 w-4" />
                  </span>
                  {t('systemOne.questions.questionN', { n: index + 1 })}
                </span>
              </legend>

              {own.length > 0 && (
                <ul id={`${id}-problems`} data-question-problem className="mb-3 list-disc space-y-1 rounded-lg bg-red-50 p-3 pl-7 text-sm text-red-700" role="alert">
                  {own.map((p) => <li key={p}>{p}</li>)}
                </ul>
              )}

              <div className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_12rem_auto]">
                <div>
                  <label htmlFor={`${id}-key`} className="mb-1 block text-xs font-medium text-gray-600">{t('systemOne.questions.key')}</label>
                  <input id={`${id}-key`} aria-describedby={describedBy} className={inputClass} value={question.key} placeholder="is_urgent"
                         onChange={(e) => update(index, { ...question, key: e.target.value })} />
                </div>
                <div>
                  <label htmlFor={`${id}-type`} className="mb-1 block text-xs font-medium text-gray-600">{t('systemOne.questions.type')}</label>
                  <select id={`${id}-type`} className={inputClass} value={question.type}
                          onChange={(e) => update(index, changeQuestionType(question, e.target.value as SystemOneQuestionType))}>
                    {QUESTION_TYPES.map((type) => <option key={type} value={type}>{t(TYPE_LABEL_KEY[type])}</option>)}
                  </select>
                </div>
                <div className="flex items-end gap-1">
                  <button type="button" id={`${id}-up`} className={smallButton} aria-label={t('systemOne.questions.moveUp', { n: index + 1 })} disabled={index === 0} onClick={() => move(index, -1, `${id}-up`)}>
                    <ArrowUp className="h-4 w-4" aria-hidden="true" />
                  </button>
                  <button type="button" id={`${id}-down`} className={smallButton} aria-label={t('systemOne.questions.moveDown', { n: index + 1 })} disabled={index === questions.length - 1} onClick={() => move(index, 1, `${id}-down`)}>
                    <ArrowDown className="h-4 w-4" aria-hidden="true" />
                  </button>
                  <button type="button" className={`${smallButton} hover:text-red-600`} aria-label={t('systemOne.questions.remove', { n: index + 1 })} onClick={() => remove(index)}>
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                  </button>
                </div>
              </div>

              <div className="mt-3">
                <label htmlFor={`${id}-instructions`} className="mb-1 block text-xs font-medium text-gray-600">{t('systemOne.questions.instructions')}</label>
                <input id={`${id}-instructions`} className={inputClass} value={question.instructions}
                       aria-describedby={describedBy}
                       placeholder={t(INSTRUCTION_EXAMPLE_KEY[question.type])}
                       onChange={(e) => update(index, { ...question, instructions: e.target.value })} />
              </div>

              {question.type === 'noul' && (
                <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-3">
                  <div>
                    <label htmlFor={`${id}-yes`} className="mb-1 block text-xs font-medium text-gray-600">{t('systemOne.questions.yesMeans')} <span className="font-normal">{t('systemOne.questions.optional')}</span></label>
                    <input id={`${id}-yes`} className={inputClass} placeholder={t('systemOne.questions.yesPlaceholder')} value={question.criteria?.true ?? ''}
                           onChange={(e) => update(index, { ...question, criteria: { true: e.target.value, false: question.criteria?.false ?? '' } })} />
                  </div>
                  <div>
                    <label htmlFor={`${id}-no`} className="mb-1 block text-xs font-medium text-gray-600">{t('systemOne.questions.noMeans')} <span className="font-normal">{t('systemOne.questions.optional')}</span></label>
                    <input id={`${id}-no`} className={inputClass} placeholder={t('systemOne.questions.noPlaceholder')} value={question.criteria?.false ?? ''}
                           onChange={(e) => update(index, { ...question, criteria: { true: question.criteria?.true ?? '', false: e.target.value } })} />
                  </div>
                  <div>
                    <label htmlFor={`${id}-threshold`} className="mb-1 block text-xs font-medium text-gray-600">{t('systemOne.questions.threshold')} <span className="font-normal">{t('systemOne.questions.optional')}</span></label>
                    <DecimalInput id={`${id}-threshold`} className={inputClass} placeholder="0.5"
                                  value={question.threshold} onChange={(value) => update(index, { ...question, threshold: value })} />
                    <p className="mt-1 text-xs text-gray-500">{t('systemOne.questions.thresholdHelp')}</p>
                  </div>
                  <p className="text-xs text-gray-500 md:col-span-3">
                    {t('systemOne.questions.noulHelp')}
                  </p>
                </div>
              )}

              {question.type === 'choice' && (
                <div className="mt-3">
                  <p className="mb-1 text-xs font-medium text-gray-600">{t('systemOne.questions.options', { range: optionRange })}</p>
                  <div className="space-y-2">
                    {question.criteria.map((option: ChoiceOption, optionIndex) => (
                      <div key={`${id}-o${optionIndex}`} className="grid grid-cols-[auto_1fr_2fr_auto] items-center gap-2">
                        <span className="inline-flex items-center gap-1" title={option.color ? t('systemOne.questions.colorChosen') : t('systemOne.questions.colorAutomatic')}>
                          <input type="color" aria-label={t('systemOne.questions.optionColor', { n: optionIndex + 1 })} className="h-8 w-8 cursor-pointer rounded border border-gray-300 bg-white p-0.5"
                                 value={optionColor(option)}
                                 onChange={(e) => update(index, { ...question, criteria: question.criteria.map((o, i) => (i === optionIndex ? { ...o, color: e.target.value } : o)) })} />
                          {option.color && (
                            <button type="button" className="text-[10px] text-gray-500 underline hover:text-gray-800" aria-label={t('systemOne.questions.optionAutoColor', { n: optionIndex + 1 })}
                                    onClick={() => update(index, { ...question, criteria: question.criteria.map((o, i) => (i === optionIndex ? { ...o, color: null } : o)) })}>
                              {t('systemOne.questions.auto')}
                            </button>
                          )}
                        </span>
                        <input aria-label={t('systemOne.questions.optionName', { n: optionIndex + 1 })} className={inputClass} placeholder={t('systemOne.questions.optionNamePlaceholder')} value={option.key}
                               onChange={(e) => update(index, { ...question, criteria: question.criteria.map((o, i) => (i === optionIndex ? { ...o, key: e.target.value } : o)) })} />
                        <input aria-label={t('systemOne.questions.optionDescription', { n: optionIndex + 1 })} className={inputClass} placeholder={t('systemOne.questions.optionDescriptionPlaceholder')} value={option.description ?? ''}
                               onChange={(e) => update(index, { ...question, criteria: question.criteria.map((o, i) => (i === optionIndex ? { ...o, description: e.target.value } : o)) })} />
                        <button type="button" className={`${smallButton} hover:text-red-600`} aria-label={t('systemOne.questions.removeOption', { n: optionIndex + 1 })} disabled={question.criteria.length <= MIN_OPTIONS}
                                onClick={() => update(index, { ...question, criteria: question.criteria.filter((_, i) => i !== optionIndex) })}>
                          <Trash2 className="h-4 w-4" aria-hidden="true" />
                        </button>
                      </div>
                    ))}
                  </div>
                  <button type="button" className="mt-2 inline-flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800 disabled:opacity-40" disabled={optionsFull(question.criteria.length)}
                          onClick={() => update(index, { ...question, criteria: [...question.criteria, { key: '', description: '' }] })}>
                    <Plus className="h-4 w-4" aria-hidden="true" /> {t('systemOne.questions.addOption')}
                  </button>
                </div>
              )}

              {question.type === 'score' && (
                <div className="mt-3">
                  <p className="mb-1 text-xs font-medium text-gray-600">{t('systemOne.questions.levels', { range: optionRange })}</p>
                  <div className="space-y-2">
                    {question.criteria.map((level, levelIndex) => (
                      <div key={`${id}-l${levelIndex}`} className="grid grid-cols-[auto_1fr_auto] items-center gap-2">
                        <span className="inline-flex w-12 items-center justify-end gap-1.5 text-xs text-gray-500">
                          <span className="h-3 w-3 rounded-full" aria-hidden="true"
                                style={{ backgroundColor: scaleColor(levelIndex, question.criteria.length, question.color_start ?? 'green') }} />
                          {levelIndex}
                        </span>
                        <input aria-label={t('systemOne.questions.levelDescription', { n: levelIndex })} className={inputClass} placeholder={levelIndex < LEVEL_EXAMPLE_COUNT ? t(`systemOne.questions.levelExample${levelIndex}`) : t('systemOne.questions.levelFallback', { n: levelIndex })} value={level}
                               onChange={(e) => update(index, { ...question, criteria: question.criteria.map((l, i) => (i === levelIndex ? e.target.value : l)) })} />
                        <button type="button" className={`${smallButton} hover:text-red-600`} aria-label={t('systemOne.questions.removeLevel', { n: levelIndex })} disabled={question.criteria.length <= MIN_OPTIONS}
                                onClick={() => update(index, { ...question, criteria: question.criteria.filter((_, i) => i !== levelIndex) })}>
                          <Trash2 className="h-4 w-4" aria-hidden="true" />
                        </button>
                      </div>
                    ))}
                  </div>
                  <button type="button" className="mt-2 inline-flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800 disabled:opacity-40" disabled={optionsFull(question.criteria.length)}
                          onClick={() => update(index, { ...question, criteria: [...question.criteria, ''] })}>
                    <Plus className="h-4 w-4" aria-hidden="true" /> {t('systemOne.questions.addLevel')}
                  </button>
                  <fieldset className="mt-3 flex flex-wrap items-center gap-4 text-xs text-gray-600">
                    <legend className="mb-1 block font-medium">{t('systemOne.questions.colorsLegend')}</legend>
                    <label className="inline-flex items-center gap-1.5">
                      <input type="radio" name={`${id}-color`} checked={(question.color_start ?? 'green') === 'green'}
                             onChange={() => update(index, { ...question, color_start: 'green' })} />
                      {t('systemOne.questions.colorGreenFirst')}
                    </label>
                    <label className="inline-flex items-center gap-1.5">
                      <input type="radio" name={`${id}-color`} checked={question.color_start === 'red'}
                             onChange={() => update(index, { ...question, color_start: 'red' })} />
                      {t('systemOne.questions.colorRedFirst')}
                    </label>
                  </fieldset>
                </div>
              )}

              {question.type !== 'noul' && (
                <div className="mt-3 max-w-xs">
                  <label htmlFor={`${id}-minp`} className="mb-1 block text-xs font-medium text-gray-600">
                    {t('systemOne.questions.minProbability')} <span className="font-normal">{t('systemOne.questions.optional')}</span>
                  </label>
                  <DecimalInput id={`${id}-minp`} className={inputClass} placeholder={t('systemOne.questions.minProbabilityPlaceholder')}
                                value={question.min_probability} onChange={(value) => update(index, { ...question, min_probability: value })} />
                  <p className="mt-1 text-xs text-gray-500">{t('systemOne.questions.minProbabilityHelp')}</p>
                </div>
              )}
            </fieldset>
          );
        })}
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {QUESTION_TYPES.map((type) => (
          <button key={type} type="button" onClick={() => add(type)} disabled={limits.maxQuestions !== undefined && questions.length >= limits.maxQuestions}
                  className="inline-flex items-center gap-1 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-40">
            <Plus className="h-4 w-4" aria-hidden="true" /> {t(ADD_LABEL_KEY[type])}
          </button>
        ))}
      </div>
    </div>
  );
}

export default SystemOneQuestionsEditor;
