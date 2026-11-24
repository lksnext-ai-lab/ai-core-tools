import { fireEvent, screen, waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import SiloForm from '../../src/components/forms/SiloForm';
import { apiMock } from './apiMock';
import { renderWithProviders, tr, trPattern } from './testUtils';

const DOMAIN_SILO = {
  silo_id: 5,
  name: 'silo for domain Docs',
  description: 'Crawled docs',
  type: 'DOMAIN',
  docs_count: 10,
  vector_db_type: 'PGVECTOR',
  embedding_service_id: 1,
  vector_db_options: [{ code: 'PGVECTOR', label: 'PGVector' }],
  chunk_size: 1000,
  chunk_overlap: 200,
  pdf_loader: 'pymupdf',
  pdf_loader_options: {},
  indexing_options: {
    pdf_loaders: [{ key: 'pymupdf', is_default: true, options: [] }],
    min_chunk_size: 200,
    max_chunk_size: 8000,
    default_chunk_size: 2000,
    default_chunk_overlap: 400,
    default_pdf_loader: 'pymupdf',
  },
};

describe('SiloForm', () => {
  it('editing keeps the silo type and sends the indexing settings', async () => {
    apiMock.getOutputParsers.mockResolvedValue([] as never);
    apiMock.getEmbeddingServices.mockResolvedValue([{ service_id: 1, name: 'Embeddings' }] as never);
    const onSubmit = vi.fn().mockResolvedValue(undefined);

    renderWithProviders(
      <Routes>
        <Route path="/apps/:appId/silos/:siloId" element={<SiloForm silo={DOMAIN_SILO} onSubmit={onSubmit} onCancel={vi.fn()} />} />
      </Routes>,
      { path: '/apps/7/silos/5' },
    );
    await waitFor(() => expect(apiMock.getEmbeddingServices).toHaveBeenCalled());

    fireEvent.change(screen.getByRole('spinbutton', { name: trPattern('siloFormPage.indexing.chunkSize') }), {
      target: { value: '1800' },
    });
    fireEvent.click(screen.getByRole('button', { name: tr('siloFormPage.actions.update') }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const payload = onSubmit.mock.calls[0][0];
    expect(payload).not.toHaveProperty('type');
    expect(payload).toMatchObject({ name: 'silo for domain Docs', chunk_size: 1800, chunk_overlap: 200, pdf_loader: 'pymupdf' });
  });
});
