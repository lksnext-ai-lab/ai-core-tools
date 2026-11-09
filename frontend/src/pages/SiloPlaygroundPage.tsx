import type { Dispatch, ReactNode, SetStateAction } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Search, Clock, Bot } from 'lucide-react';
import SearchControls from '../components/playground/SearchControls';
import SiloAPISnippets from '../components/playground/SiloAPISnippets';
import SearchFilters from '../components/playground/SearchFilters';
import ResultCard from '../components/playground/ResultCard';
import Modal from '../components/ui/Modal';
import { FormField } from '../components/ui/FormField';
import ServiceLifecycleAlert from '../components/services/ServiceLifecycleAlert';
import { useSiloSearch } from '../hooks/useSiloSearch';
import type { PanelState } from '../hooks/useSiloSearch';
import { LoadingState } from '../components/ui/LoadingState';
import { ButtonApp } from '../components/ui/ButtonApp';
import Alert from '../components/ui/Alert';
import Title from '../components/ui/Title';
import CardApp from '../components/ui/CardApp';
import HelpRow from '../components/ui/HelpRow';
import BackgroundImage from '../components/ui/BackgroundImage';

interface PlaygroundSectionProps {
  readonly title: string;
  /** Short text shown on the right of the header (e.g. current value). */
  readonly summary?: ReactNode;
  readonly children: ReactNode;
}

/**
 * Collapsible section of the playground search area (filters, settings, API, history, compare).
 * Single place for its look — same border/background as HelpRow, full width, starts closed.
 */
function PlaygroundSection({ title, summary, children }: PlaygroundSectionProps) {
  return (
    <details className="group rounded-md border border-bg-soft bg-canvas-alt dark:border-bronze-border-dark dark:bg-canvas-alt-dark">
      <summary
        className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-md px-4 py-3 text-fg dark:text-fg-dark
                   [&::-webkit-details-marker]:hidden focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus dark:focus-visible:outline-focus-dark"
      >
        <span className="text-sm font-medium">{title}</span>
        <span className="flex min-w-0 items-center gap-2.5 text-[12.5px] text-fg-secondary dark:text-fg-secondary-dark">
          {summary && <span className="truncate">{summary}</span>}
          <span
            aria-hidden="true"
            className="text-lg leading-none text-fg-tertiary transition-transform duration-150 group-open:rotate-90 motion-reduce:transition-none dark:text-fg-tertiary-dark"
          >
            ›
          </span>
        </span>
      </summary>
      <div className="border-t border-bg-soft p-4 dark:border-bronze-border-dark">
        {children}
      </div>
    </details>
  );
}

function SiloPlaygroundPage() {
  const { appId, siloId } = useParams();
  const { t, i18n } = useTranslation('common');
  const {
    silo,
    loading,
    error,
    systemDBConfig,
    searchQuery,
    setSearchQuery,
    searchResults,
    isSearching,
    searchError,
    hasSearched,
    filterMetadata,
    minContentLength,
    setMinContentLength,
    maxContentLength,
    setMaxContentLength,
    searchControls,
    setSearchControls,
    selectedIds,
    setSelectedIds,
    deletingId,
    showBulkDeleteModal,
    setShowBulkDeleteModal,
    bulkDeleteLoading,
    deleteTarget,
    setDeleteTarget,
    showDeleteByFilterModal,
    setShowDeleteByFilterModal,
    deleteByFilterCount,
    deleteByFilterLoading,
    deleteByFilterConfirmName,
    setDeleteByFilterConfirmName,
    reindexLoading,
    reindexMessage,
    queryHistory,
    lastClientMs,
    lastServerMs,
    showAgentShortcut,
    setShowAgentShortcut,
    appAgentsForSilo,
    compareMode,
    panelA,
    setPanelA,
    panelB,
    setPanelB,
    maxScore,
    sharedIds,
    handleSearch,
    handleBack,
    handleFilterMetadataChange,
    handleDeleteDocument,
    handleDeleteConfirmed,
    handleSelectResult,
    handleBulkDelete,
    handleOpenDeleteByFilter,
    handleDeleteByFilterConfirmed,
    handleReindex,
    searchPanel,
    deleteHistoryEntry,
    rerunHistoryEntry,
    handleNavigateToAgent,
  } = useSiloSearch(appId, siloId);

  if (loading) {
    return (
      <div className="space-y-6">
        <LoadingState variant="page" message={t('siloPlayground.loadingSilo')} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <Alert
          type="error"
          title={t('siloPlayground.loadErrorTitle')}
          message={(
            <>
              {error}
              <button type="button" onClick={handleBack} className="mt-2 block underline">
                {t('siloPlayground.backToSilos')}
              </button>
            </>
          )}
        />
      </div>
    );
  }

  if (!silo) {
    return (
      <div className="space-y-6">
        <Alert
          type="warning"
          title={t('siloPlayground.notFoundTitle')}
          message={(
            <>
              <span className="block">{t('siloPlayground.notFoundMessage')}</span>
              <button type="button" onClick={handleBack} className="mt-2 block underline">
                {t('siloPlayground.backToSilos')}
              </button>
            </>
          )}
        />
      </div>
    );
  }

  function renderComparePanel(
    label: string,
    panel: PanelState,
    setter: Dispatch<SetStateAction<PanelState>>,
  ) {
    const panelMax = panel.results.length > 0 ? Math.max(...panel.results.map((r) => r.score ?? 0)) : 0;
    return (
      <div className="flex flex-col gap-3 rounded-md border border-line bg-surface p-4 dark:border-line-dark dark:bg-surface-dark">
        <div className="flex items-center gap-2">
          <span className="rounded bg-bronze-bg px-2 py-0.5 text-xs font-medium text-bronze dark:bg-bronze-bg-dark dark:text-bronze-dark">
            {t('siloPlayground.panelLabel', { label })}
          </span>
          {panel.clientMs !== null && (
            <span className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark">{panel.clientMs} ms</span>
          )}
        </div>

        <div className="flex gap-2">
          <input
            type="text"
            value={panel.query}
            onChange={(e) => setter((p) => ({ ...p, query: e.target.value }))}
            onKeyDown={(e) => { if (e.key === 'Enter') void searchPanel(panel.query, setter); }}
            placeholder={t('siloPlayground.queryPlaceholder')}
            aria-label={t('siloPlayground.queryForPanel', { label })}
            className="min-w-0 flex-1 rounded-md border border-line bg-surface px-3 py-1.5 text-sm text-fg placeholder:text-fg-tertiary outline-none focus:border-accent disabled:opacity-60 dark:border-line-dark dark:bg-surface-dark dark:text-fg-dark dark:placeholder:text-fg-tertiary-dark dark:focus:border-accent-dark"
            disabled={panel.isSearching}
          />
          <ButtonApp
            label={t('siloPlayground.search')}
            onClick={() => void searchPanel(panel.query, setter)}
            loading={panel.isSearching}
            size="small"
          />
        </div>

        {panel.error && <p className="text-xs text-error dark:text-error-dark">{panel.error}</p>}

        {panel.results.length === 0 && !panel.isSearching && (
          <p className="text-xs italic text-fg-tertiary dark:text-fg-tertiary-dark">{t('siloPlayground.noResultsYet')}</p>
        )}

        <div className="space-y-2 overflow-y-auto max-h-[60vh]">
          {panel.results.map((result, idx) => {
            const isShared = result.id ? sharedIds.has(result.id) : false;
            return (
              <div key={result.id ?? idx} className={isShared ? 'rounded-lg ring-2 ring-accent dark:ring-accent-dark' : ''}>
                <ResultCard
                  result={result}
                  index={idx}
                  maxScore={panelMax}
                  appId={appId ?? ''}
                  siloId={siloId ?? ''}
                />
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <div className="mt-2">
      {/* Header */}
      <div className="flex items-center justify-between">
        <Title variant='titPrincipal' titulo={t('siloPlayground.title', { name: silo.name })} subtitulo={t('siloPlayground.subtitle')} />
      </div>

        <HelpRow title={t('siloPlayground.helpTitle')}>
          <p>
            {t('siloPlayground.helpDescription')}
          </p>
          <p className="mt-2 font-medium text-fg dark:text-fg-dark">{t('siloPlayground.tipsTitle')}</p>
          <ul className="mt-1 space-y-1">
            <li>• {t('siloPlayground.tipNaturalLanguage')}</li>
            <li>• {t('siloPlayground.tipBrowseAll')}</li>
            <li>• {t('siloPlayground.tipDifferentPhrasing')}</li>
            <li>• {t('siloPlayground.tipRelevance')}</li>
        </ul>
      </HelpRow>

      <ServiceLifecycleAlert warnings={silo.lifecycle_warnings} variant="full" className="max-h-48 overflow-y-auto" />

      {/* Silo Info */}
      <CardApp variant="canvas" className="p-6 mt-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <h3 className="text-xs text-bronze-dark uppercase tracking-wider mb-1">{t('siloPlayground.siloType')}</h3>
            <p className="text-md font-semibold text-fg dark:text-fg-dark">
              {silo.type || t('siloPlayground.custom')}
            </p>
          </div>
          <div>
            <h3 className="text-xs text-bronze-dark uppercase tracking-wider mb-1">{t('siloPlayground.documents')}</h3>
            <p className="text-md font-semibold text-fg dark:text-fg-dark">
              {silo.docs_count.toLocaleString(i18n.resolvedLanguage)}
            </p>
          </div>
          <div>
            <h3 className="text-xs text-bronze-dark uppercase tracking-wider mb-1">{t('siloPlayground.created')}</h3>
            <p className="text-md font-semibold text-fg dark:text-fg-dark">
              {silo.created_at ? new Date(silo.created_at).toLocaleDateString(i18n.resolvedLanguage) : t('siloPlayground.unknown')}
            </p>
          </div>
        </div>
      </CardApp>

      {/* Search Interface */}
      <section className="mb-6 mt-6" aria-labelledby="search-documents-title">
        <h2 id="search-documents-title" className="mb-3 font-display text-[20px] tracking-[-0.02em] text-ink dark:text-ink-dark">
          {t('siloPlayground.searchDocuments')}
        </h2>

        <form onSubmit={handleSearch} className="space-y-3">
          {/* Search Query */}
          <div className="relative">
            <label htmlFor="searchQuery" className="sr-only">
              {t('siloPlayground.searchQuery')}
            </label>
            <div className="flex gap-2.5">
              <FormField
                type="text"
                id="searchQuery"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                autoComplete="off"
                placeholder={t('siloPlayground.searchPlaceholder')}
                className="min-w-0 flex-1"
                inputClassName="!px-[15px] !py-[13px] !text-[15px]"
                disabled={isSearching}
              />
              <ButtonApp
                type="submit"
                label={isSearching ? t('siloPlayground.searching') : t('siloPlayground.search')}
                loading={isSearching}
              />
            </div>
          </div>

          {/* Response time + agent shortcut */}
          {(lastClientMs !== null || appAgentsForSilo.length > 0) && (
            <div className="flex min-h-[18px] flex-wrap items-center gap-3.5 text-[12.5px] text-fg-tertiary dark:text-fg-tertiary-dark">
              {lastClientMs !== null && (
                <div className="flex items-center gap-1.5">
                  <Clock className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>{t('siloPlayground.clientTime')}: <strong className="font-medium text-fg-secondary dark:text-fg-secondary-dark">{lastClientMs} ms</strong></span>
                  {lastServerMs !== null && (
                    <span>· {t('siloPlayground.serverTime')}: <strong className="font-medium text-fg-secondary dark:text-fg-secondary-dark">{lastServerMs} ms</strong></span>
                  )}
                </div>
              )}
              
              {appAgentsForSilo.length > 0 && (
                <div className="relative">
                  <button
                    type="button"
                    onClick={() => setShowAgentShortcut((v) => !v)}
                    className="flex items-center gap-1 rounded-md border border-line px-2 py-1 text-fg-secondary hover:text-fg dark:border-line-dark dark:text-fg-secondary-dark dark:hover:text-fg-dark"
                  >
                    <Bot className="h-3.5 w-3.5" aria-hidden="true" />
                    {t('siloPlayground.testAgainstAgent')}
                  </button>
                  {showAgentShortcut && (
                    <div className="absolute left-0 top-full z-10 mt-1 min-w-44 rounded-md border border-line bg-surface shadow-md dark:border-line-dark dark:bg-surface-dark">
                      {appAgentsForSilo.map((agent) => (
                        <button
                          key={agent.id}
                          type="button"
                          onClick={() => handleNavigateToAgent(agent.id)}
                          className="block w-full truncate px-3 py-2 text-left text-sm text-fg hover:bg-surface-hover dark:text-fg-dark dark:hover:bg-surface-hover-dark"
                        >
                          {agent.name}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Metadata Filters */}
          {(silo.metadata_fields?.length ?? 0) > 0 && (
            <PlaygroundSection title={t('siloPlayground.metadataFilters')}>
              <SearchFilters
                metadataFields={silo.metadata_fields}
                dbType={systemDBConfig}
                disabled={isSearching}
                onFilterMetadataChange={handleFilterMetadataChange}
                appId={appId}
                siloId={siloId}
                siloStorageKey={siloId}
              />
            </PlaygroundSection>
          )}

          {/* Search settings: controls + content-length filter */}
          <PlaygroundSection title={t('siloPlayground.searchSettings')} summary={t('siloPlayground.topKSummary', { count: searchControls.limit })}>
            <div className="space-y-5">
              <SearchControls
                siloId={siloId ?? ''}
                value={searchControls}
                onChange={setSearchControls}
                disabled={isSearching}
              />

              <div>
              <p className="mb-2 text-[13px] font-medium text-fg dark:text-fg-dark">
                {t('siloPlayground.contentLength')} <span className="font-normal text-fg-tertiary dark:text-fg-tertiary-dark">({t('siloPlayground.characters')})</span>
              </p>
              <div className="flex flex-wrap items-center gap-2.5">
                <div className="flex shrink-0 items-center gap-1">
                  <FormField
                    label={t('siloPlayground.min')}
                    labelClassName="text-[13px] text-fg-secondary dark:text-fg-secondary-dark mb-0 whitespace-nowrap"
                    type="number"
                    id="minContentLength"
                    min={0}
                    placeholder="–"
                    value={minContentLength ?? ''}
                    onChange={(e) => setMinContentLength(e.target.value === '' ? null : Number(e.target.value))}
                    className="flex shrink-0 items-center gap-1"
                    inputClassName="!w-20 px-2 py-1"
                    disabled={isSearching}
                  />
                </div>
                <FormField
                  label={t('siloPlayground.max')}
                  labelClassName="text-[13px] text-fg-secondary dark:text-fg-secondary-dark mb-0 whitespace-nowrap"
                  type="number"
                  id="maxContentLength"
                  min={0}
                  placeholder="–"
                  value={maxContentLength ?? ''}
                  onChange={(e) => setMaxContentLength(e.target.value === '' ? null : Number(e.target.value))}
                  className="flex shrink-0 items-center gap-1"
                  inputClassName="!w-20 px-2 py-1"
                  disabled={isSearching}
                />
                {(minContentLength != null || maxContentLength != null) && (
                  <ButtonApp
                    type="button"
                    onClick={() => { setMinContentLength(null); setMaxContentLength(null); }}
                    label={t('siloPlayground.clear')}
                    variant="secondary"
                    size="medium"
                  />
                )}
              </div>
              </div>
            </div>
          </PlaygroundSection>
        </form>

        {/* Sections outside the form so Enter in the compare inputs never submits the main search */}
        <div className="mt-3 space-y-3">
          <PlaygroundSection title={t('siloPlayground.apiSnippet')}>
            <SiloAPISnippets
              appId={appId ?? ''}
              siloId={siloId ?? ''}
              siloName={silo?.name}
              query={searchQuery}
              limit={searchControls.limit}
              filterMetadata={filterMetadata as Record<string, unknown> | undefined}
              searchType={searchControls.searchType}
              scoreThreshold={searchControls.searchType === 'similarity_score_threshold' ? searchControls.scoreThreshold : undefined}
              fetchK={searchControls.searchType === 'mmr' ? searchControls.fetchK : undefined}
              lambdaMult={searchControls.searchType === 'mmr' ? searchControls.lambdaMult : undefined}
            />
          </PlaygroundSection>

          {queryHistory.length > 0 && (
            <PlaygroundSection title={t('siloPlayground.history')} summary={t('siloPlayground.recentQueries', { count: queryHistory.length })}>
              <ul className="space-y-1">
                {queryHistory.map((entry, i) => (
                  <li key={entry.timestamp} className="flex items-center gap-2 text-sm">
                    <button
                      type="button"
                      onClick={() => rerunHistoryEntry(entry)}
                      className="flex-1 truncate text-left text-fg hover:text-accent hover:underline dark:text-fg-dark dark:hover:text-accent-dark"
                      title={entry.query}
                    >
                      {entry.query || t('siloPlayground.emptyQuery')}
                    </button>
                    <span className="shrink-0 text-xs text-fg-tertiary dark:text-fg-tertiary-dark">
                      {new Date(entry.timestamp).toLocaleTimeString(i18n.resolvedLanguage)}
                    </span>
                    <button
                      type="button"
                      onClick={() => deleteHistoryEntry(i)}
                      className="shrink-0 text-base leading-none text-fg-tertiary hover:text-error dark:text-fg-tertiary-dark dark:hover:text-error-dark"
                      title={t('siloPlayground.remove')}
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            </PlaygroundSection>
          )}

          <PlaygroundSection title={t('siloPlayground.compareSearches')}>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {renderComparePanel('A', panelA, setPanelA)}
              {renderComparePanel('B', panelB, setPanelB)}
            </div>
          </PlaygroundSection>

          {/* Search Error */}
          {searchError && <Alert type="error" title={t('siloPlayground.searchError')} message={searchError} />}
        </div>
      </section>

      {/* Search Results (single panel) */}
      {!compareMode && searchResults.length > 0 && (
        <div>
          <h2 className="mb-3 font-display text-[20px] tracking-[-0.02em] text-ink dark:text-ink-dark">
            {t('siloPlayground.searchResults', { count: searchResults.length })}
          </h2>

          {/* Curator toolbar */}
          <div className="mb-3.5 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-surface-tint px-3.5 py-2.5 dark:border-line-dark dark:bg-surface-tint-dark">
            <label className="flex cursor-pointer select-none items-center gap-[9px] text-[13px] text-fg dark:text-fg-dark">
              <input
                type="checkbox"
                checked={selectedIds.size > 0 && selectedIds.size === searchResults.length}
                onChange={(e) => {
                  if (e.target.checked) {
                    setSelectedIds(new Set(searchResults.map((r) => r.id ?? '').filter(Boolean)));
                  } else {
                    setSelectedIds(new Set());
                  }
                }}
                className="h-4 w-4 cursor-pointer accent-ink dark:accent-ink-dark"
              />
              {selectedIds.size > 0 ? t('siloPlayground.selectedCount', { count: selectedIds.size }) : t('siloPlayground.selectAll')}
            </label>
            <div className="flex flex-wrap items-center gap-2.5">
              {reindexMessage && (
                <span className={`text-xs font-medium ${reindexMessage.type === 'success' ? 'text-success dark:text-success-dark' : 'text-error dark:text-error-dark'}`}>
                  {reindexMessage.text}
                </span>
              )}
              {filterMetadata && Object.keys(filterMetadata).length > 0 && (
                <button
                  onClick={handleOpenDeleteByFilter}
                  className="rounded-md border border-error bg-transparent px-[13px] py-[7px] font-display text-[13px] text-error transition-colors hover:bg-error-bg dark:border-error-dark dark:text-error-dark dark:hover:bg-error-bg-dark"
                >
                  {t('siloPlayground.deleteByFilter')}
                </button>
              )}
              {selectedIds.size > 0 && (
                <button
                  onClick={() => setShowBulkDeleteModal(true)}
                  className="rounded-md border border-error bg-transparent px-[13px] py-[7px] font-display text-[13px] text-error transition-colors hover:bg-error-bg dark:border-error-dark dark:text-error-dark dark:hover:bg-error-bg-dark"
                >
                  {t('siloPlayground.deleteSelected', { count: selectedIds.size })}
                </button>
              )}
            </div>
          </div>
          
          <div className="space-y-4">
            {searchResults.map((result, index) => (
              <ResultCard
                key={result.id ?? `result-${index}`}
                result={result}
                index={index}
                maxScore={maxScore}
                onDelete={handleDeleteDocument}
                isDeleting={deletingId === result.id}
                appId={appId ?? ''}
                siloId={siloId ?? ''}
                isSelected={selectedIds.has(result.id ?? '')}
                onSelect={handleSelectResult}
                onReindex={reindexLoading === null ? handleReindex : undefined}
              />
            ))}
          </div>
        </div>
      )}

      {/* Empty State */}
      {!compareMode && !isSearching && searchResults.length === 0 && hasSearched && !searchError && (
        <CardApp className="p-6">
          <div className="text-center">
            <BackgroundImage icon={Search} size={64} iconSize={32} className="mx-auto" />
            <p className="font-display text-lg font-normal tracking-[-0.02em] text-fg dark:text-fg-dark">{t('siloPlayground.noResultsFound')}</p>
            <div className="text-sm text-fg-tertiary dark:text-fg-tertiary-dark space-y-1 max-w-md mx-auto text-center">
              {searchControls.searchType === 'similarity_score_threshold' && (
                <p className="text-sm mt-1">{t('siloPlayground.lowerScoreThreshold', { threshold: searchControls.scoreThreshold })}</p>
              )}
              {filterMetadata && Object.keys(filterMetadata).length > 0 && (
                <p className="text-sm mt-1">{t('siloPlayground.relaxMetadataFilters')}</p>
              )}
              {searchControls.limit < 20 && (
                <p className="text-sm mt-1">{t('siloPlayground.increaseTopK', { count: searchControls.limit })}</p>
              )}
              <p className="text-sm mt-1">
                {searchQuery
                  ? t('siloPlayground.noDocumentsMatched')
                  : t('siloPlayground.emptySiloOrRestrictiveFilters')}
              </p>
            </div>
          </div>
        </CardApp>
      )}

      {/* Single delete confirmation modal */}
      <Modal
        isOpen={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        title={t('siloPlayground.deleteDocumentTitle')}
        size="small"
      >
        <p className="text-sm text-gray-700 mb-4">
          {t('siloPlayground.deleteDocumentConfirmation')}
        </p>
        <div className="flex gap-2 justify-end">
          <button
            onClick={() => setDeleteTarget(null)}
            className="px-4 py-2 text-sm border border-gray-300 rounded hover:bg-gray-50"
          >
            {t('cancel')}
          </button>
          <button
            onClick={() => void handleDeleteConfirmed()}
            className="px-4 py-2 text-sm bg-red-600 text-white rounded hover:bg-red-700"
          >
            {t('delete')}
          </button>
        </div>
      </Modal>

      {/* Bulk delete confirmation modal */}
      <Modal
        isOpen={showBulkDeleteModal}
        onClose={() => setShowBulkDeleteModal(false)}
        title={t('siloPlayground.bulkDeleteTitle', { count: selectedIds.size })}
        size="small"
      >
        <p className="text-sm text-gray-700 mb-4">
          {t('siloPlayground.bulkDeleteConfirmation', { count: selectedIds.size })}
        </p>
        <div className="flex gap-2 justify-end">
          <button
            onClick={() => setShowBulkDeleteModal(false)}
            className="px-4 py-2 text-sm border border-gray-300 rounded hover:bg-gray-50"
          >
            {t('cancel')}
          </button>
          <button
            onClick={() => void handleBulkDelete()}
            disabled={bulkDeleteLoading}
            className="px-4 py-2 text-sm bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
          >
            {bulkDeleteLoading ? t('siloPlayground.deleting') : t('siloPlayground.deleteCount', { count: selectedIds.size })}
          </button>
        </div>
      </Modal>

      {/* Delete by filter modal */}
      <Modal
        isOpen={showDeleteByFilterModal}
        onClose={() => { setShowDeleteByFilterModal(false); setDeleteByFilterConfirmName(''); }}
        title={t('siloPlayground.deleteByFilterTitle')}
        size="small"
      >
        {deleteByFilterLoading ? (
          <p className="text-sm text-gray-600">{t('siloPlayground.countingMatchingDocuments')}</p>
        ) : deleteByFilterCount === -1 ? (
          <p className="text-sm text-red-600">{t('siloPlayground.countMatchingFailed')}</p>
        ) : (
          <>
            <p className="text-sm text-gray-700 mb-3">
              {deleteByFilterCount === null
                ? t('siloPlayground.deleteByFilterCountUnknown')
                : t('siloPlayground.deleteByFilterConfirmation', { count: deleteByFilterCount })}
            </p>
            <p className="text-sm text-gray-600 mb-2">
              {t('siloPlayground.typeSiloNameToConfirm')} <strong>{silo.name}</strong>:
            </p>
            <input
              type="text"
              value={deleteByFilterConfirmName}
              onChange={(e) => setDeleteByFilterConfirmName(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded text-sm mb-4 focus:outline-none focus:ring-2 focus:ring-red-400"
              placeholder={silo.name}
            />
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => { setShowDeleteByFilterModal(false); setDeleteByFilterConfirmName(''); }}
                className="px-4 py-2 text-sm border border-gray-300 rounded hover:bg-gray-50"
              >
                {t('cancel')}
              </button>
              <button
                onClick={() => void handleDeleteByFilterConfirmed()}
                disabled={deleteByFilterConfirmName !== silo.name || bulkDeleteLoading}
                className="px-4 py-2 text-sm bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
              >
                {bulkDeleteLoading ? t('siloPlayground.deleting') : t('siloPlayground.deleteAllMatching')}
              </button>
            </div>
          </>
        )}
      </Modal>
    </div>
  );
}

export default SiloPlaygroundPage;