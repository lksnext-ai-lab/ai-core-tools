import { useTranslation } from 'react-i18next';
import Alert from '../ui/Alert';
import { FormCheckbox, FormField, FormSelect } from '../ui/FormField';
import type { IndexingOptions, IndexingSettings, PdfLoaderOptionInfo } from '../../types/indexing';
import { indexingSettingsErrors, loaderDefaults } from '../../utils/indexingSettings';

export interface IndexingSettingsFieldsProps {
  readonly options: IndexingOptions;
  readonly value: IndexingSettings;
  readonly onChange: (value: IndexingSettings) => void;
  /** Editing an existing silo/repository: warn that changes only apply to newly indexed content. */
  readonly isEditing: boolean;
  /** Repositories configure the silo they own; silos configure themselves. */
  readonly scope: 'repository' | 'silo';
  readonly disabled?: boolean;
}

function parseNumber(raw: string): number | null {
  if (raw.trim() === '') return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * Chunk size / overlap (all content) and the PDF loader with its own options.
 * Stored on the silo, so a repository and its silo share the same settings.
 */
export function IndexingSettingsFields({
  options, value, onChange, isEditing, scope, disabled = false,
}: IndexingSettingsFieldsProps) {
  const { t } = useTranslation('common');
  const errors = indexingSettingsErrors(value, options);
  const selectedLoader = options.pdf_loaders.find((loader) => loader.key === value.pdf_loader);

  const setOption = (option: PdfLoaderOptionInfo, raw: boolean | string) => {
    let parsed: boolean | number | string = raw;
    if (option.type === 'integer' || option.type === 'number') {
      parsed = parseNumber(String(raw)) ?? option.default;
    }
    onChange({ ...value, pdf_loader_options: { ...value.pdf_loader_options, [option.name]: parsed } });
  };

  const optionLabel = (name: string) => t(`siloFormPage.indexing.loaderOptions.${name}.label`, { defaultValue: name });
  const optionHelp = (name: string) => t(`siloFormPage.indexing.loaderOptions.${name}.help`, { defaultValue: '' });

  return (
    <>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <FormField
          label={t('siloFormPage.indexing.chunkSize')}
          id="chunk_size"
          type="number"
          inputMode="numeric"
          min={options.min_chunk_size}
          max={options.max_chunk_size}
          step={100}
          value={value.chunk_size ?? ''}
          onChange={(e) => onChange({ ...value, chunk_size: parseNumber(e.target.value) })}
          disabled={disabled}
          required
          error={errors.chunk_size ? t(errors.chunk_size.key, errors.chunk_size.params) : undefined}
          helpText={t('siloFormPage.indexing.chunkSizeHelp', {
            min: options.min_chunk_size, max: options.max_chunk_size,
          })}
        />
        <FormField
          label={t('siloFormPage.indexing.chunkOverlap')}
          id="chunk_overlap"
          type="number"
          inputMode="numeric"
          min={0}
          step={50}
          value={value.chunk_overlap ?? ''}
          onChange={(e) => onChange({ ...value, chunk_overlap: parseNumber(e.target.value) })}
          disabled={disabled}
          required
          error={errors.chunk_overlap ? t(errors.chunk_overlap.key, errors.chunk_overlap.params) : undefined}
          helpText={t('siloFormPage.indexing.chunkOverlapHelp')}
        />
      </div>

      <FormSelect
        label={t('siloFormPage.indexing.pdfLoader')}
        id="pdf_loader"
        value={value.pdf_loader}
        onChange={(e) => {
          const loader = options.pdf_loaders.find((candidate) => candidate.key === e.target.value);
          // A different loader starts from its own option defaults (same rule as the backend).
          onChange({ ...value, pdf_loader: e.target.value, pdf_loader_options: loaderDefaults(loader) });
        }}
        options={options.pdf_loaders.map((loader) => ({
          value: loader.key,
          label: t(`siloFormPage.indexing.pdfLoaders.${loader.key}.label`, { defaultValue: loader.key }),
        }))}
        disabled={disabled}
        helpText={t(`siloFormPage.indexing.pdfLoaders.${value.pdf_loader}.description`, { defaultValue: '' })}
      />

      {selectedLoader?.options.map((option) => {
        const id = `pdf_loader_option_${option.name}`;
        const current = value.pdf_loader_options[option.name] ?? option.default;
        if (option.type === 'boolean') {
          return (
            <FormCheckbox
              key={option.name}
              id={id}
              variant="toggle"
              label={optionLabel(option.name)}
              helpText={optionHelp(option.name) || undefined}
              checked={Boolean(current)}
              onChange={(e) => setOption(option, e.target.checked)}
              disabled={disabled}
            />
          );
        }
        return (
          <FormField
            key={option.name}
            id={id}
            type={option.type === 'string' ? 'text' : 'number'}
            label={optionLabel(option.name)}
            helpText={optionHelp(option.name) || undefined}
            value={String(current)}
            onChange={(e) => setOption(option, e.target.value)}
            disabled={disabled}
          />
        );
      })}

      {isEditing && (
        <Alert
          type="info"
          polite
          message={scope === 'repository'
            ? t('siloFormPage.indexing.appliesToNewContentRepository')
            : t('siloFormPage.indexing.appliesToNewContentSilo')}
        />
      )}
    </>
  );
}
