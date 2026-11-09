import { ArrowDown, ArrowUp, Layers } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { MiddlewareType } from '../../core/types';
import { MIDDLEWARE_TYPE_INFO } from '../../constants/middlewares';
import { Badge } from '../ui/Badge';
import { ButtonCard } from '../ui/ButtonCard';
import { ButtonApp, CardApp } from '../..';

export interface AgentMiddlewareOption {
  middleware_id: number;
  name: string;
  description?: string;
  middleware_type: MiddlewareType;
}

interface AgentMiddlewaresCardProps {
  readonly middlewares: AgentMiddlewareOption[];
  /** Selected ids in execution order. */
  readonly selectedIds: number[];
  readonly hasMemory: boolean;
  readonly onChange: (ids: number[]) => void;
  /** Human approval needs conversation memory to pause and resume. */
  readonly onRequireMemory: () => void;
  readonly onManage: () => void;
}

/** Pick an agent's middlewares (one per type) and their execution order. */
function AgentMiddlewaresCard({
  middlewares, selectedIds, hasMemory, onChange, onRequireMemory, onManage,
}: AgentMiddlewaresCardProps) {
  const { t } = useTranslation('common');
  const byId = new Map(middlewares.map((m) => [m.middleware_id, m]));
  const selected = selectedIds.map((id) => byId.get(id)).filter((m): m is AgentMiddlewareOption => !!m);
  const selectedTypes = new Set(selected.map((m) => m.middleware_type));

  const toggle = (mw: AgentMiddlewareOption) => {
    if (selectedIds.includes(mw.middleware_id)) {
      onChange(selectedIds.filter((id) => id !== mw.middleware_id));
      return;
    }
    if (mw.middleware_type === 'human_in_the_loop' && !hasMemory) {
      onRequireMemory();
    }
    onChange([...selectedIds, mw.middleware_id]);
  };

  const move = (index: number, delta: -1 | 1) => {
    const next = selected.map((m) => m.middleware_id);
    const target = index + delta;
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  };

  return (
    <CardApp
      titulo={t('agentFormPage.middlewares.title')}
      icon={Layers}
      subtitulo={t('agentFormPage.middlewares.subtitle')}
    >
       {middlewares.length === 0 ? (
        <div className="text-center py-8">
          <div className="w-16 h-16 rounded-full bg-bronze-bg-soft dark:bg-bronze-bg-soft-dark  flex items-center justify-center mx-auto mb-4">
            <Layers className="w-8 h-8 text-bronze dark:text-bronze-dark" />
          </div>
          <h4 className="text-lg font-medium text-fg dark:text-fg-dark mb-2">
            {t('agentFormPage.middlewares.emptyTitle')}
          </h4>
          <p className="text-fg-tertiary dark:text-fg-tertiary-dark mb-4">
            {t('agentFormPage.middlewares.emptyDescription')}
          </p>
          <ButtonApp
            label={t('agentFormPage.middlewares.manage')}
            onClick={onManage}
            variant="primary"
            size="medium"
            icon={<Layers className="w-4 h-4" />}
            className="mx-auto mb-4"
          />
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {middlewares.map((mw) => {
              const isSelected = selectedIds.includes(mw.middleware_id);
              // LangChain allows one middleware of each type per agent.
              const blocked = !isSelected && selectedTypes.has(mw.middleware_type);
              const typeLabel = t(`middlewaresPage.types.${mw.middleware_type}.label`);
              const helpText = [
                blocked
                  ? t('agentFormPage.middlewares.onlyOnePerType')
                  : mw.description || t(`middlewaresPage.types.${mw.middleware_type}.description`),
                mw.middleware_type === 'human_in_the_loop' && !isSelected && !blocked && !hasMemory
                  ? t('agentFormPage.middlewares.memoryEnabled')
                  : undefined,
              ].filter(Boolean).join(' ');
              return (
                <ButtonCard
                  key={mw.middleware_id}
                  onClick={() => toggle(mw)}
                  ariaLabel={t('agentFormPage.middlewares.selectMiddleware', { name: mw.name })}
                  disabled={blocked}
                  variant="selectable-check"
                  selected={isSelected}
                  checkboxLabel={mw.name}
                  checkboxHelpText={helpText}
                  // Long names/descriptions without spaces wrap inside the card instead of overflowing.
                  className="min-w-0 [overflow-wrap:anywhere]"
                >
                  {mw.name !== MIDDLEWARE_TYPE_INFO[mw.middleware_type]?.label && (
                    <Badge label={typeLabel} variant="default" className="mt-2 self-start" />
                  )}
                </ButtonCard>
              );
            })}
          </div>

          {selected.length > 1 && (
            <div className="mt-6">
              <h4 className="text-sm font-semibold text-fg dark:text-fg-dark">
                {t('agentFormPage.middlewares.executionOrder')}
              </h4>
              <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark mb-2">
                {t('agentFormPage.middlewares.executionOrderHelp')}
              </p>
              <ol className="space-y-2">
                {selected.map((mw, index) => (
                  <li
                    key={mw.middleware_id}
                    className="flex items-center justify-between gap-2 rounded-lg bg-surface dark:bg-surface-dark border border-line dark:border-line-dark p-3"
                  >
                    <span className="text-sm text-fg dark:text-fg-dark min-w-0 truncate">
                      <span className="text-fg-secondary dark:text-fg-secondary-dark tabular-nums mr-2">{index + 1}.</span>
                      {mw.name}
                    </span>
                    <span className="flex shrink-0 gap-1">
                      <button
                        type="button"
                        onClick={() => move(index, -1)}
                        disabled={index === 0}
                        aria-label={t('agentFormPage.middlewares.moveUp', { name: mw.name })}
                        className="p-1 rounded text-fg-secondary dark:text-fg-secondary-dark  hover:bg-surface-hover disabled:opacity-30 disabled:hover:bg-transparent"
                      >
                        <ArrowUp className="w-4 h-4" />
                      </button>
                      <button
                        type="button"
                        onClick={() => move(index, 1)}
                        disabled={index === selected.length - 1}
                        aria-label={t('agentFormPage.middlewares.moveDown', { name: mw.name })}
                        className="p-1 rounded text-fg-secondary dark:text-fg-secondary-dark hover:bg-surface-hover disabled:opacity-30 disabled:hover:bg-transparent"
                      >
                        <ArrowDown className="w-4 h-4" />
                      </button>
                    </span>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </>
      )}
    </CardApp>
  );
}

export default AgentMiddlewaresCard;
