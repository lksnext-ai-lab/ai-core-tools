import { memo, useId, useState } from 'react';
import { ChevronDown, Trash2 } from 'lucide-react';

import { Badge } from './Badge';

export interface MessageMetaItem {
  readonly id: string | number;
  readonly label: string;
  /** The referenced resource no longer exists; it is rendered with the "deleted" marker. */
  readonly deleted?: boolean;
}

export interface MessageMetaLabels {
  /** Heading of the source row (e.g. "Source"). */
  readonly source: string;
  readonly skills: string;
  readonly mcps: string;
  /** Marker text for deleted resources, already formatted by the caller (e.g. "(deleted)"). */
  readonly deleted: string;
  /** Accessible name of the details toggle for a model (e.g. `Details of ${model}`). */
  readonly toggle: (model: string) => string;
}

export interface MessageMetaBadgeProps {
  readonly model: MessageMetaItem;
  readonly source?: MessageMetaItem | null;
  readonly skills?: readonly MessageMetaItem[];
  readonly mcps?: readonly MessageMetaItem[];
  readonly labels: MessageMetaLabels;
  readonly className?: string;
}

const NO_ITEMS: readonly MessageMetaItem[] = [];

function ItemText({ item, deletedLabel }: Readonly<{ item: MessageMetaItem; deletedLabel: string }>) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className={item.deleted ? 'line-through' : undefined}>{item.label}</span>
      {item.deleted && (
        <span className="inline-flex items-center gap-0.5 text-bronze dark:text-bronze-dark">
          <Trash2 aria-hidden="true" className="h-3 w-3" />
          <span>{deletedLabel}</span>
        </span>
      )}
    </span>
  );
}

function DetailRow({
  heading,
  items,
  deletedLabel,
}: Readonly<{ heading: string; items: readonly MessageMetaItem[]; deletedLabel: string }>) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-2">
      <dt className="font-medium text-fg-secondary dark:text-fg-secondary-dark">{heading}</dt>
      <dd>
        <ul className="flex flex-wrap gap-x-2">
          {items.map((item) => (
            <li key={item.id}>
              <ItemText item={item} deletedLabel={deletedLabel} />
            </li>
          ))}
        </ul>
      </dd>
    </div>
  );
}

/**
 * Discreet badge with the model that produced an assistant message. When the turn also used a
 * source, skills or MCP servers, the badge becomes a disclosure button (aria-expanded) that
 * reveals them. Deleted resources keep their name and carry a textual "deleted" marker, so the
 * state is never conveyed by color alone.
 */
function MessageMetaBadgeComponent({
  model,
  source = null,
  skills = NO_ITEMS,
  mcps = NO_ITEMS,
  labels,
  className = '',
}: Readonly<MessageMetaBadgeProps>) {
  const [expanded, setExpanded] = useState(false);
  const detailsId = useId();
  const hasDetails = source !== null || skills.length > 0 || mcps.length > 0;

  const badgeLabel = model.deleted ? `${model.label} ${labels.deleted}` : model.label;
  const badge = (
    <Badge
      label={badgeLabel}
      variant={model.deleted ? 'warning' : 'default'}
      icon={model.deleted ? <Trash2 aria-hidden="true" className="h-3 w-3" /> : undefined}
    />
  );

  return (
    <div className={`inline-flex max-w-full flex-col items-start gap-1 ${className}`}>
      {hasDetails ? (
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls={detailsId}
          aria-label={labels.toggle(badgeLabel)}
          onClick={() => setExpanded((v) => !v)}
          className="inline-flex min-h-6 items-center gap-0.5 rounded-full px-0.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-focus dark:focus-visible:ring-focus-dark"
        >
          {badge}
          <ChevronDown
            aria-hidden="true"
            className={`h-3 w-3 text-fg-tertiary transition-transform motion-reduce:transition-none dark:text-fg-tertiary-dark ${
              expanded ? 'rotate-180' : ''
            }`}
          />
        </button>
      ) : (
        badge
      )}
      {hasDetails && (
        <dl
          id={detailsId}
          hidden={!expanded}
          className="max-w-full space-y-0.5 rounded-md border border-line bg-surface px-2.5 py-1.5 text-xs text-fg-secondary dark:border-line-dark dark:bg-surface-dark dark:text-fg-secondary-dark"
        >
          {source && <DetailRow heading={labels.source} items={[source]} deletedLabel={labels.deleted} />}
          {skills.length > 0 && (
            <DetailRow heading={labels.skills} items={skills} deletedLabel={labels.deleted} />
          )}
          {mcps.length > 0 && <DetailRow heading={labels.mcps} items={mcps} deletedLabel={labels.deleted} />}
        </dl>
      )}
    </div>
  );
}

export const MessageMetaBadge = memo(MessageMetaBadgeComponent);

export default MessageMetaBadge;
