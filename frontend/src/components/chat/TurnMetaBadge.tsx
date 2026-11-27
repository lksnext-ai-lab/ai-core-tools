import { memo, useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { MessageMetaBadge, type MessageMetaLabels } from '../ui/MessageMetaBadge';
import type { ChatTurnConfig, ChatTurnInfo } from '../../types/appChat';
import { buildTurnMeta } from './chatSelection';

export interface TurnMetaBadgeProps {
  readonly turn?: ChatTurnInfo | null;
  readonly turnConfig?: ChatTurnConfig | null;
}

/** Model / source / skills / MCPs used by one assistant message, as text (never colour only). */
function TurnMetaBadgeComponent({ turn, turnConfig }: Readonly<TurnMetaBadgeProps>) {
  const { t } = useTranslation('common');

  const labels = useMemo<MessageMetaLabels>(
    () => ({
      source: t('appChat.meta.source'),
      skills: t('appChat.meta.skills'),
      mcps: t('appChat.meta.mcps'),
      deleted: t('appChat.meta.deleted'),
      toggle: (model) => t('appChat.meta.toggle', { model }),
    }),
    [t],
  );

  const meta = useMemo(
    () => buildTurnMeta(turn, turnConfig, (id) => t('appChat.selection.unnamedSource', { id })),
    [turn, turnConfig, t],
  );
  if (!meta) return null;

  return (
    <MessageMetaBadge
      model={meta.model}
      source={meta.source}
      skills={meta.skills}
      mcps={meta.mcps}
      labels={labels}
    />
  );
}

export const TurnMetaBadge = memo(TurnMetaBadgeComponent);
export default TurnMetaBadge;
