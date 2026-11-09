import React, { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { apiService } from '../services/api';
import SearchFilters from '../components/playground/SearchFilters';
import type { SearchFilterMetadataField } from '../components/playground/SearchFilters';
import Title from '../components/ui/Title';
import { FormField } from '../components/ui/FormField';
import ButtonApp from '../components/ui/ButtonApp';
import { Search } from 'lucide-react';
import Alert from '../components/ui/Alert';
import CardApp from '../components/ui/CardApp';
import HelpRow from '../components/ui/HelpRow';
import type { ServiceOptionLike } from '../utils/serviceLifecycle';

// Define the repository type
interface Repository {
  repository_id: number;
  name: string;
  created_at?: string;
  resources: unknown[];
  embedding_services: ServiceOptionLike[];
  embedding_service_id?: number;
  metadata_fields?: SearchFilterMetadataField[];
  vector_db_type?: string;
  silo_id?: number;
}

interface SearchResult {
  page_content: string;
  metadata: Record<string, unknown>;
  score?: number;
}

const RepositoryPlaygroundPage: React.FC = () => {
  const { appId, repositoryId } = useParams<{ appId: string; repositoryId: string }>();
  const { t, i18n } = useTranslation('common');
  {/*const navigate = useNavigate();*/}
  
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [repository, setRepository] = useState<Repository | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [filterMetadata, setFilterMetadata] = useState<Record<string, unknown> | undefined>(undefined);

  useEffect(() => {
    if (appId && repositoryId) {
      void loadRepositoryInfo();
    }
  }, [appId, repositoryId]);

  const loadRepositoryInfo = async () => {
    try {
      const repositoryData = await apiService.getRepository(Number.parseInt(appId!), Number.parseInt(repositoryId!));
      setRepository(repositoryData);
      
      // The metadata_fields should already be included in the repository response from the backend
      // If not available and there's a silo_id, we can try to load it separately
      if (!repositoryData.metadata_fields?.length && repositoryData.silo_id) {
        try {
          const siloData = await apiService.getSilo(Number.parseInt(appId!), repositoryData.silo_id);
          setRepository(prev => ({
            ...prev!,
            metadata_fields: siloData.metadata_fields || []
          }));
        } catch (siloErr) {
          console.warn('Could not load silo metadata fields:', siloErr);
        }
      }
    } catch (err) {
      console.error('Error loading repository info:', err);
      setError(t('repositoryPlayground.loadError'));
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();

    try {
      setSearching(true);
      setError(null);
      setResults([]);
      setHasSearched(true);

      const hasFilters = filterMetadata !== undefined && Object.keys(filterMetadata).length > 0;
      const searchFilters = hasFilters ? filterMetadata as Record<string, any> : undefined;

      // Use the repository search API with filters
      const response = await apiService.searchRepositoryDocuments(
        Number.parseInt(appId!), 
        Number.parseInt(repositoryId!), 
        query,
        10,
        searchFilters
      );
      
      setResults(response.results || []);

    } catch (err) {
      console.error('Error searching repository:', err);
      setError(t('repositoryPlayground.searchError'));
    } finally {
      setSearching(false);
    }
  };

  {/*const handleGoBack = () => {
    // Go back to the previous page in history
    navigate(-1);
  };*/}

  const handleFilterMetadataChange = useCallback((metadata: Record<string, unknown> | undefined) => {
    setFilterMetadata(metadata);
  }, []);

  useEffect(() => {
    const fields = repository?.metadata_fields;
    if ((!fields || fields.length === 0) && filterMetadata !== undefined) {
      setFilterMetadata(undefined);
    }
  }, [repository, filterMetadata]);

  const maxScore = results.reduce((max, result) => Math.max(max, result.score ?? 0), 0);

  return (
    <div className="container mx-auto px-4 pb-4">
      {/* Header */}
      <div className="flex justify-between items-start">
          <Title
            variant="titSecundario"
            titulo={t('repositoryPlayground.title')}
            subtitulo={t('repositoryPlayground.subtitle', {
              name: repository?.name || t('repositoryPlayground.repositoryFallback'),
            })}
            subtitleMarginBottom={20}
          />
      </div>

      <HelpRow title={t('repositoryPlayground.helpTitle')}>
        <p>{t('repositoryPlayground.helpDescription')}</p>
        <p className="mt-2 font-medium text-fg dark:text-fg-dark">
          {t('repositoryPlayground.tipsTitle')}
        </p>
        <ul className="mt-1 space-y-1">
          <li>• {t('repositoryPlayground.tipNaturalLanguage')}</li>
          <li>• {t('repositoryPlayground.tipBrowseAll')}</li>
          <li>• {t('repositoryPlayground.tipDifferentPhrasing')}</li>
          <li>• {t('repositoryPlayground.tipRelevance')}</li>
          <li>• {t('repositoryPlayground.tipMetadataFilters')}</li>
        </ul>
      </HelpRow>

      {/* Search Interface */}
      <section className="mb-6 mt-6" aria-labelledby="search-documents-title">
        <h2 id="search-documents-title" className="mb-3 font-display text-[20px] tracking-[-0.02em] text-ink dark:text-ink-dark">
          {t('repositoryPlayground.searchDocuments')}
        </h2>

        <form onSubmit={handleSearch} className="space-y-3">
          <div className="relative">
            <label htmlFor="searchQuery" className="sr-only">
              {t('repositoryPlayground.searchQuery')}
            </label>
            <div className="flex gap-2.5">
              <FormField
                type="text"
                id="searchQuery"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                autoComplete="off"
                placeholder={t('repositoryPlayground.searchPlaceholder')}
                className="min-w-0 flex-1"
                inputClassName="!px-[15px] !py-[13px] !text-[15px]"
                disabled={searching}
              />
              <ButtonApp
                type="submit"
                label={searching ? t('repositoryPlayground.searching') : t('repositoryPlayground.search')}
                loading={searching}
              />
            </div>
          </div>

          {repository?.metadata_fields && repository.metadata_fields.length > 0 && (
            <details className="group rounded-md border border-bg-soft bg-canvas-alt dark:border-bronze-border-dark dark:bg-canvas-alt-dark">
              <summary
                className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-md px-4 py-3 text-fg dark:text-fg-dark
                           [&::-webkit-details-marker]:hidden focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus dark:focus-visible:outline-focus-dark"
              >
                <span className="text-sm font-medium">{t('repositoryPlayground.metadataFilters')}</span>
                <span className="flex min-w-0 items-center gap-2.5 text-[12.5px] text-fg-secondary dark:text-fg-secondary-dark">
                  <span
                    aria-hidden="true"
                    className="text-lg leading-none text-fg-tertiary transition-transform duration-150 group-open:rotate-90 motion-reduce:transition-none dark:text-fg-tertiary-dark"
                  >
                    ›
                  </span>
                </span>
              </summary>
              <div className="border-t border-bg-soft p-4 dark:border-bronze-border-dark">
                <SearchFilters
                  metadataFields={repository.metadata_fields}
                  dbType={repository.vector_db_type?.toUpperCase()}
                  disabled={searching}
                  onFilterMetadataChange={handleFilterMetadataChange}
                />
              </div>
            </details>
          )}
        </form>
      </section>

      {/* Error Message */}
      {error && <Alert type="error" message={error} className="mb-6" />}

      {/* Search Results */}
      {results.length > 0 && (
        <div>
          <h2 className="mb-3 font-display text-[20px] tracking-[-0.02em] text-ink dark:text-ink-dark">
            {t('repositoryPlayground.searchResults', { count: results.length })}
          </h2>
          
          <div className="space-y-4">
            {results.map((result, index) => {
              const source = result.metadata.source as string | undefined;
              const page = result.metadata.page as number | undefined;
              const uniqueKey = `${source}-${page ?? 'no-page'}-${result.page_content.substring(0, 30).replaceAll(/\s+/g, '-').replaceAll(/[^a-zA-Z0-9-]/g, '')}`;
              const scoreDisplay = result.score != null && maxScore > 0
                ? {
                    barWidth: Math.min((result.score / maxScore) * 100, 100),
                    label: new Intl.NumberFormat(i18n.resolvedLanguage, {
                      minimumFractionDigits: 3,
                      maximumFractionDigits: 3,
                    }).format(result.score),
                  }
                : null;

              return (
                <article key={uniqueKey} className="rounded-lg border border-line px-4 py-3.5 dark:border-line-dark">
                  <div className="mb-2.5 flex items-start justify-between gap-2">
                    <span className="text-[13px] font-semibold text-fg dark:text-fg-dark">
                      {t('repositoryPlayground.result', { number: index + 1 })}
                    </span>
                  </div>

                  {scoreDisplay && (
                    <div className="mb-3 flex items-center gap-2">
                      <div className="h-1.5 flex-1 rounded bg-surface-hover dark:bg-surface-hover-dark">
                        <div
                          className="h-1.5 rounded bg-accent dark:bg-accent-dark"
                          style={{ width: `${scoreDisplay.barWidth}%` }}
                        />
                      </div>
                      <span className="shrink-0 text-xs text-fg-tertiary dark:text-fg-tertiary-dark">
                        {t('repositoryPlayground.score', { score: scoreDisplay.label })}
                      </span>
                    </div>
                  )}

                  <div className="mb-3">
                    <h3 className="mb-1 text-[13px] font-medium text-fg-secondary dark:text-fg-secondary-dark">
                      {t('repositoryPlayground.content')}
                    </h3>
                    <p className="m-0 whitespace-pre-wrap text-[13.5px] leading-[1.6] text-fg dark:text-fg-dark">
                      {result.page_content}
                    </p>
                  </div>

                  {Object.keys(result.metadata).length > 0 && (
                    <details className="group mt-2.5 border-t border-line pt-2.5 dark:border-line-dark">
                      <summary className="flex cursor-pointer list-none items-center gap-1.5 text-[13px] font-medium text-fg dark:text-fg-dark [&::-webkit-details-marker]:hidden">
                        <span
                          aria-hidden="true"
                          className="inline-block transition-transform duration-150 group-open:rotate-90 motion-reduce:transition-none"
                        >
                          ▸
                        </span>
                        {t('repositoryPlayground.metadata')}
                        <span className="font-normal text-fg-tertiary dark:text-fg-tertiary-dark">
                          · {t('repositoryPlayground.metadataFields', {
                            count: Object.keys(result.metadata).length,
                          })}
                        </span>
                      </summary>
                      <div className="mt-2.5">
                        <pre className="m-0 overflow-x-auto whitespace-pre-wrap break-all rounded-lg border border-line bg-surface-tint px-3.5 py-3 font-mono text-xs leading-relaxed text-fg-secondary dark:border-line-dark dark:bg-surface-tint-dark dark:text-fg-secondary-dark">
                          {JSON.stringify(result.metadata, null, 2)}
                        </pre>
                      </div>
                    </details>
                  )}
                </article>
              );
            })}
          </div>
        </div>
      )}

      {/* No Results State */}
      {!searching && results.length === 0 && hasSearched && (
        <CardApp variant="white" className="p-6">
          <div className="text-center">
            <Search className="w-10 h-10 text-fg-secondary dark:text-fg-secondary-dark mx-auto mb-4" />
            <h3 className="text-lg font-medium text-fg dark:text-fg-dark mb-2">
              {t('repositoryPlayground.noResultsFound')}
            </h3>
            <p className="text-fg-secondary dark:text-fg-secondary-dark">
              {query
                ? t('repositoryPlayground.noResultsWithQuery')
                : t('repositoryPlayground.noResultsWithoutQuery')}
            </p>
          </div>
        </CardApp>
      )}

    </div>
  );
};

export default RepositoryPlaygroundPage; 