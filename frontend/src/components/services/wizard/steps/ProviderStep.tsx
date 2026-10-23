import { getProvidersForKind } from '../providers';
import type { ServiceKind } from '../../../../types/services';
import { ButtonCard } from '../../../ui/ButtonCard';
import { ProviderBadge } from '../../../ui/Badge';


interface ProviderStepProps {
  readonly kind: ServiceKind;
  readonly selected: string;
  readonly onSelect: (providerValue: string) => void;
}

function ProviderStep({
  kind,
  selected,
  onSelect,
}: Readonly<ProviderStepProps>) {
  const providers = getProvidersForKind(kind);
  const subtitle =
    kind === 'ai'
      ? 'Pick the provider that hosts the chat, vision or audio model you want to use.'
      : 'Pick the provider for the embedding model that will index your data.';

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold text-fg dark:text-fg-dark">Choose a provider</h3>
        <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark mt-1">{subtitle}</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {providers.map((p) => {
          const isSelected = selected === p.value;
          return (
            <ButtonCard
              key={p.value}
              variant="selectable"
              selected={isSelected}
              ariaLabel={p.label}
              onClick={() => onSelect(p.value)}
            >
              <div className="flex items-center justify-between gap-2">
                <ProviderBadge provider={p.value} label={p.label} className="text-md" />
                {!p.supportsModelListing && (
                  <span className="text-[10px] uppercase tracking-wide font-medium text-amber-700 bg-amber-50 border border-amber-200 px-1.5 py-0.5 rounded">
                    Manual
                  </span>
                )}
              </div>
              <p className="mt-2 text-xs text-fg-secondary dark:text-fg-secondary-dark line-clamp-2">
                {p.description}
              </p>
            </ButtonCard>
          );
        })}
      </div>
    </div>
  );
}

export default ProviderStep;
