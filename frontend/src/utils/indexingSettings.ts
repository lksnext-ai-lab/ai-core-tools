import type {
  IndexingDetailFields,
  IndexingOptions,
  IndexingSettings,
  IndexingSettingsPayload,
  PdfLoaderInfo,
  PdfLoaderOptionValue,
} from '../types/indexing';

/** Translation key + params of a field error (translated by the component). */
export interface IndexingFieldError {
  readonly key: string;
  readonly params?: Readonly<Record<string, number>>;
}

export interface IndexingSettingsErrors {
  readonly chunk_size?: IndexingFieldError;
  readonly chunk_overlap?: IndexingFieldError;
}

export function loaderDefaults(loader: PdfLoaderInfo | undefined): Record<string, PdfLoaderOptionValue> {
  return Object.fromEntries((loader?.options ?? []).map((option) => [option.name, option.default]));
}

/** Form state from a silo/repository detail; null when the API sent no indexing catalog. */
export function initialIndexingSettings(detail: IndexingDetailFields | undefined): IndexingSettings | null {
  const options = detail?.indexing_options;
  if (!options) return null;
  const pdfLoader = detail.pdf_loader ?? options.default_pdf_loader;
  const loader = options.pdf_loaders.find((candidate) => candidate.key === pdfLoader);
  return {
    chunk_size: detail.chunk_size ?? options.default_chunk_size,
    chunk_overlap: detail.chunk_overlap ?? options.default_chunk_overlap,
    pdf_loader: pdfLoader,
    pdf_loader_options: { ...loaderDefaults(loader), ...(detail.pdf_loader_options ?? {}) },
  };
}

/** Same rules as the backend (tools/document_loaders.validate_chunking). */
export function indexingSettingsErrors(value: IndexingSettings, options: IndexingOptions): IndexingSettingsErrors {
  const errors: { chunk_size?: IndexingFieldError; chunk_overlap?: IndexingFieldError } = {};
  const size = value.chunk_size;
  if (size === null || !Number.isInteger(size) || size < options.min_chunk_size || size > options.max_chunk_size) {
    errors.chunk_size = {
      key: 'siloFormPage.indexing.validation.chunkSizeRange',
      params: { min: options.min_chunk_size, max: options.max_chunk_size },
    };
  }
  const overlap = value.chunk_overlap;
  const maxOverlap = Math.floor((size ?? options.default_chunk_size) / 2);
  if (overlap === null || !Number.isInteger(overlap) || overlap < 0 || overlap > maxOverlap) {
    errors.chunk_overlap = { key: 'siloFormPage.indexing.validation.chunkOverlapRange', params: { max: maxOverlap } };
  }
  return errors;
}

export function hasIndexingErrors(errors: IndexingSettingsErrors): boolean {
  return Boolean(errors.chunk_size || errors.chunk_overlap);
}

/** Request fields; call only when there are no validation errors. */
export function toIndexingPayload(value: IndexingSettings): IndexingSettingsPayload {
  return {
    chunk_size: value.chunk_size ?? undefined,
    chunk_overlap: value.chunk_overlap ?? undefined,
    pdf_loader: value.pdf_loader,
    pdf_loader_options: { ...value.pdf_loader_options },
  };
}
