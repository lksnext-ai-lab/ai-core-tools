/**
 * Indexing settings of a silo (also edited from its repository). Mirrors
 * backend/schemas/indexing_schemas.py; limits and defaults come from the API
 * (`indexing_options`), never hardcoded here.
 */
export type PdfLoaderOptionValue = boolean | number | string;

export interface PdfLoaderOptionInfo {
  readonly name: string;
  readonly type: 'boolean' | 'integer' | 'number' | 'string';
  readonly default: PdfLoaderOptionValue;
}

export interface PdfLoaderInfo {
  readonly key: string;
  readonly is_default: boolean;
  readonly options: readonly PdfLoaderOptionInfo[];
}

export interface IndexingOptions {
  readonly pdf_loaders: readonly PdfLoaderInfo[];
  readonly min_chunk_size: number;
  readonly max_chunk_size: number;
  readonly default_chunk_size: number;
  readonly default_chunk_overlap: number;
  readonly default_pdf_loader: string;
}

export interface IndexingSettings {
  /** null while the input is empty (invalid until filled). */
  readonly chunk_size: number | null;
  readonly chunk_overlap: number | null;
  readonly pdf_loader: string;
  readonly pdf_loader_options: Readonly<Record<string, PdfLoaderOptionValue>>;
}

/** Fields of a silo/repository detail response that carry the indexing settings. */
export interface IndexingDetailFields {
  chunk_size?: number;
  chunk_overlap?: number;
  pdf_loader?: string;
  pdf_loader_options?: Record<string, PdfLoaderOptionValue>;
  indexing_options?: IndexingOptions;
}

/** Indexing fields of a create/update request (omitted = keep the stored value). */
export interface IndexingSettingsPayload {
  chunk_size?: number;
  chunk_overlap?: number;
  pdf_loader?: string;
  pdf_loader_options?: Record<string, PdfLoaderOptionValue>;
}
