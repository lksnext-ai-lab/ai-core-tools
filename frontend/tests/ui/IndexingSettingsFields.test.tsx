import { fireEvent, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { IndexingSettingsFields } from '../../src/components/forms/IndexingSettingsFields';
import type { IndexingOptions, IndexingSettings } from '../../src/types/indexing';
import { renderWithProviders, tr, trPattern } from './testUtils';

const OPTIONS: IndexingOptions = {
  pdf_loaders: [
    { key: 'pymupdf', is_default: true, options: [] },
    {
      key: 'pymupdf4llm',
      is_default: false,
      options: [
        { name: 'section_prefix', type: 'boolean', default: true },
        { name: 'remove_headers_footers', type: 'boolean', default: true },
      ],
    },
  ],
  min_chunk_size: 200,
  max_chunk_size: 8000,
  default_chunk_size: 2000,
  default_chunk_overlap: 400,
  default_pdf_loader: 'pymupdf',
};

const INITIAL: IndexingSettings = { chunk_size: 2000, chunk_overlap: 400, pdf_loader: 'pymupdf', pdf_loader_options: {} };

function Harness({ onChange, isEditing = false }: Readonly<{ onChange: (v: IndexingSettings) => void; isEditing?: boolean }>) {
  const [value, setValue] = useState<IndexingSettings>(INITIAL);
  return (
    <IndexingSettingsFields
      options={OPTIONS}
      value={value}
      isEditing={isEditing}
      scope="silo"
      onChange={(next) => { setValue(next); onChange(next); }}
    />
  );
}

describe('IndexingSettingsFields', () => {
  it('switching to the structured loader shows its options with their defaults', () => {
    const onChange = vi.fn();
    renderWithProviders(<Harness onChange={onChange} />);

    expect(screen.queryByLabelText(tr('siloFormPage.indexing.loaderOptions.section_prefix.label'))).toBeNull();
    fireEvent.change(screen.getByLabelText(tr('siloFormPage.indexing.pdfLoader')), { target: { value: 'pymupdf4llm' } });

    expect(onChange).toHaveBeenLastCalledWith({
      ...INITIAL,
      pdf_loader: 'pymupdf4llm',
      pdf_loader_options: { section_prefix: true, remove_headers_footers: true },
    });
    const prefix = screen.getByLabelText(tr('siloFormPage.indexing.loaderOptions.section_prefix.label'));
    expect(prefix).toBeChecked();
    fireEvent.click(prefix);
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({
      pdf_loader_options: { section_prefix: false, remove_headers_footers: true },
    }));
  });

  it('shows range errors under the chunk fields', () => {
    renderWithProviders(<Harness onChange={vi.fn()} />);

    fireEvent.change(screen.getByLabelText(trPattern('siloFormPage.indexing.chunkSize')), { target: { value: '50' } });
    expect(screen.getByText(tr('siloFormPage.indexing.validation.chunkSizeRange', { min: 200, max: 8000 }))).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(trPattern('siloFormPage.indexing.chunkSize')), { target: { value: '1000' } });
    fireEvent.change(screen.getByLabelText(trPattern('siloFormPage.indexing.chunkOverlap')), { target: { value: '600' } });
    expect(screen.getByText(tr('siloFormPage.indexing.validation.chunkOverlapRange', { max: 500 }))).toBeInTheDocument();
  });

  it('warns when editing that changes only apply to new content', () => {
    renderWithProviders(<Harness onChange={vi.fn()} isEditing />);

    expect(screen.getByText(tr('siloFormPage.indexing.appliesToNewContentSilo'))).toBeInTheDocument();
  });
});
