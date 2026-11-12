import { useTranslation } from 'react-i18next';
import { getProvidersForKind } from '../providers';
import type { ServiceKind } from '../../../../types/services';
import { ButtonCard } from '../../../ui/ButtonCard';


interface ProviderStepProps {
  readonly kind: ServiceKind;
  readonly selected: string;
  readonly onSelect: (providerValue: string) => void;
}

function getProviderMonogram(label: string): string {
  const words = label.replace(/([a-z])([A-Z])/g, '$1 $2').match(/[A-Za-z0-9]+/g) ?? [];
  return words.length > 1
    ? words.slice(0, 2).map((word) => word[0]).join('').toUpperCase()
    : words[0]?.slice(0, 2).toUpperCase() ?? '';
}

function ProviderStep({
  kind,
  selected,
  onSelect,
}: Readonly<ProviderStepProps>) {
  const { t } = useTranslation('common');
  const providers = getProvidersForKind(kind);
  let subtitleKey = 'serviceWizard.providerStep.subtitleEmbedding';
  if (kind === 'ai') subtitleKey = 'serviceWizard.providerStep.subtitleAi';
  else if (kind === 'sandbox') subtitleKey = 'serviceWizard.providerStep.subtitleSandbox';

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold text-fg dark:text-fg-dark">{t('serviceWizard.providerStep.title')}</h3>
        <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark mt-1">{t(subtitleKey)}</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {providers.map((p) => {
          const isSelected = selected === p.value;
          return (
            <ButtonCard
              key={p.value}
              variant="selectable-radio-trailing"
              selected={isSelected}
              radioName="service-provider"
              radioValue={p.value}
              ariaLabel={p.label}
              onClick={() => onSelect(p.value)}
            >
              <div className="flex items-start gap-4">
                <span
                  aria-hidden="true"
                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-accent text-sm font-medium text-fg dark:border-accent-dark dark:text-fg-dark"
                >
                  {getProviderMonogram(p.label)}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-fg dark:text-fg-dark">{p.label}</p>
                  {!p.supportsModelListing && (
                    <p className="mt-1 inline-flex text-[10px] uppercase tracking-wide font-medium text-amber-700 bg-amber-50 border border-amber-200 px-1.5 py-0.5 rounded">
                      {t('serviceWizard.providerStep.manual')}
                    </p>
                  )}
                  <p className="mt-1 text-xs leading-5 text-fg-secondary dark:text-fg-secondary-dark line-clamp-2">
                    {p.description}
                  </p>
                </div>
              </div>
            </ButtonCard>
          );
        })}
      </div>
    </div>
  );
}

export default ProviderStep;
