import { memo, useCallback, useMemo, type Dispatch } from 'react';
import { useTranslation } from 'react-i18next';
import { Bot, BookOpen, Plug, Zap } from 'lucide-react';

import { CompactSelectPopover, type CompactSelectOption } from '../ui/CompactSelectPopover';
import { serviceOptionLabel } from '../../utils/serviceLifecycle';
import type { LifecycleStatus } from '../../types/services';
import type { ChatOptions, ChatSelection } from '../../types/appChat';
import type { ChatSelectionAction } from './chatSelection';

const NO_SILO = 'none';

export interface ChatSelectionBarProps {
  readonly options: ChatOptions;
  readonly selection: ChatSelection | null;
  readonly dispatch: Dispatch<ChatSelectionAction>;
  /** Locks the selectors, e.g. while a conversation is loading. */
  readonly disabled?: boolean;
}

function toLifecycleStatus(value: string): LifecycleStatus {
  return value === 'deprecated' || value === 'retired' ? value : 'active';
}

/**
 * Per-turn selection of model, knowledge source, skills and MCP configs. Whatever is selected when a
 * message is sent travels with that message. Chips wrap on narrow screens.
 */
function ChatSelectionBarComponent({ options, selection, dispatch, disabled = false }: Readonly<ChatSelectionBarProps>) {
  const { t } = useTranslation('common');

  const modelOptions = useMemo<readonly CompactSelectOption[]>(
    () =>
      options.ai_services
        .filter((service) => service.lifecycle_status !== 'retired' || service.service_id === selection?.ai_service_id)
        .map((service) => ({
          value: String(service.service_id),
          label: serviceOptionLabel({
            service_id: service.service_id,
            name: service.name,
            lifecycle_status: toLifecycleStatus(service.lifecycle_status),
            end_of_service_at: service.end_of_service_at,
          }),
          description: service.deprecation_notice ?? service.model_name ?? service.provider ?? undefined,
          disabled: service.lifecycle_status === 'retired',
          disabledReason: service.lifecycle_status === 'retired' ? t('appChat.selection.modelRetired') : undefined,
        })),
    [options.ai_services, selection?.ai_service_id, t],
  );

  const siloOptions = useMemo<readonly CompactSelectOption[]>(
    () => [
      { value: NO_SILO, label: t('appChat.selection.sourceNone') },
      ...options.silos.map((silo) => {
        const name = silo.name || silo.source_name || t('appChat.selection.unnamedSource', { id: silo.silo_id });
        return {
          value: String(silo.silo_id),
          label: name,
          description: silo.source_name && silo.source_name !== name ? silo.source_name : undefined,
          group: t(`appChat.sourceTypes.${silo.source_type}`),
          disabled: !!silo.disabled_reason,
          disabledReason: silo.disabled_reason ? t(`appChat.siloDisabled.${silo.disabled_reason}`) : undefined,
        };
      }),
    ],
    [options.silos, t],
  );

  const skillOptions = useMemo<readonly CompactSelectOption[]>(
    () =>
      options.skills.map((skill) => ({
        value: String(skill.skill_id),
        label: skill.name,
        description: skill.description ?? undefined,
        group: t(skill.is_system ? 'appChat.skillGroups.system' : 'appChat.skillGroups.app'),
      })),
    [options.skills, t],
  );

  const mcpOptions = useMemo<readonly CompactSelectOption[]>(
    () => options.mcp_configs.map((config) => ({ value: String(config.config_id), label: config.name })),
    [options.mcp_configs],
  );

  const skillValues = useMemo(() => (selection?.skill_ids ?? []).map(String), [selection?.skill_ids]);
  const mcpValues = useMemo(() => (selection?.mcp_config_ids ?? []).map(String), [selection?.mcp_config_ids]);

  const onModel = useCallback((value: string) => dispatch({ type: 'setModel', id: Number(value) }), [dispatch]);
  const onSilo = useCallback(
    (value: string) => dispatch({ type: 'setSilo', id: value === NO_SILO ? null : Number(value) }),
    [dispatch],
  );
  const onSkills = useCallback((values: string[]) => dispatch({ type: 'setSkills', ids: values.map(Number) }), [dispatch]);
  const onMcps = useCallback(
    (values: string[]) => dispatch({ type: 'setMcpConfigs', ids: values.map(Number) }),
    [dispatch],
  );

  const summarize = useCallback((labels: readonly string[]) => t('appChat.selection.nSelected', { count: labels.length }), [t]);
  const toggled = useCallback(
    (label: string, selected: boolean) => t(selected ? 'appChat.selection.added' : 'appChat.selection.removed', { name: label }),
    [t],
  );
  const results = useCallback((count: number) => t('appChat.selection.results', { count }), [t]);

  const siloValue = selection?.silo_id == null ? NO_SILO : String(selection.silo_id);
  const searchCommon = {
    searchable: true,
    searchPlaceholder: t('appChat.selection.search'),
    searchAriaLabel: t('appChat.selection.search'),
    emptyLabel: t('appChat.selection.noResults'),
    resultsLabel: results,
  } as const;

  return (
    <div role="group" aria-label={t('appChat.selection.groupLabel')} className="flex min-w-0 basis-full flex-wrap items-center gap-2 sm:flex-1">
      <CompactSelectPopover
        ariaLabel={t('appChat.selection.model')}
        label={t('appChat.selection.model')}
        icon={<Bot className="h-3.5 w-3.5" aria-hidden="true" />}
        options={modelOptions}
        value={selection ? String(selection.ai_service_id) : null}
        onChange={onModel}
        placeholder={disabled && !selection ? t('appChat.page.loading') : t('appChat.selection.modelPlaceholder')}
        emptyLabel={t('appChat.selection.noModels')}
        disabled={disabled}
      />
      <CompactSelectPopover
        ariaLabel={t('appChat.selection.source')}
        label={t('appChat.selection.source')}
        icon={<BookOpen className="h-3.5 w-3.5" aria-hidden="true" />}
        options={siloOptions}
        value={siloValue}
        onChange={onSilo}
        disabled={disabled || !selection}
        {...searchCommon}
      />
      <CompactSelectPopover
        multiple
        ariaLabel={t('appChat.selection.skills')}
        label={t('appChat.selection.skills')}
        icon={<Zap className="h-3.5 w-3.5" aria-hidden="true" />}
        options={skillOptions}
        value={skillValues}
        onChange={onSkills}
        placeholder={t('appChat.selection.nonePlural')}
        summarizeSelection={summarize}
        selectionChangeLabel={toggled}
        disabled={disabled || !selection}
        {...searchCommon}
      />
      <CompactSelectPopover
        multiple
        ariaLabel={t('appChat.selection.mcps')}
        label={t('appChat.selection.mcps')}
        icon={<Plug className="h-3.5 w-3.5" aria-hidden="true" />}
        options={mcpOptions}
        value={mcpValues}
        onChange={onMcps}
        placeholder={t('appChat.selection.nonePlural')}
        summarizeSelection={summarize}
        selectionChangeLabel={toggled}
        disabled={disabled || !selection}
        {...searchCommon}
      />
    </div>
  );
}

export const ChatSelectionBar = memo(ChatSelectionBarComponent);
export default ChatSelectionBar;
