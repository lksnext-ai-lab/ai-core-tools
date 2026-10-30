import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { ExternalLink, RefreshCw } from 'lucide-react';
import { apiService } from '../../services/api';
import Modal from '../ui/Modal';
import Alert from '../ui/Alert';
import type { DomainUrlDetail, DomainUrlStatus, DiscoverySource } from '../../types/crawl';
import { ButtonApp } from '../ui/ButtonApp';
import { LoadingState } from '../ui/LoadingState';
import { Spinner } from '../ui/Spinner';
import { Badge, type BadgeVariant } from '../ui/Badge';

interface DomainUrlDrawerProps {
  appId: number;
  domainId: number;
  urlId: number | null;
  canEdit: boolean;
  onClose: () => void;
}

function statusBadgeVariant(status: DomainUrlStatus): BadgeVariant {
  switch (status) {
    case 'INDEXED': return 'success';
    case 'CRAWLING': return 'info';
    case 'PENDING': return 'warning';
    case 'FAILED': return 'error';
    case 'SKIPPED':
    case 'REMOVED': return 'default';
    case 'EXCLUDED': return 'secondary';
    default: return 'default';
  }
}

function formatDate(iso: string | null | undefined, language?: string): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(language);
}

function Field({ label, value }: Readonly<{ label: string; value: React.ReactNode }>) {
  return (
    <div>
      <dt className="text-xs font-medium text-fg-secondary dark:text-fg-secondary-dark uppercase tracking-wide">{label}</dt>
      <dd className="mt-0.5 text-sm text-fg dark:text-fg-dark">{value ?? '—'}</dd>
    </div>
  );
}

export default function DomainUrlDrawer({
  appId,
  domainId,
  urlId,
  canEdit,
  onClose,
}: Readonly<DomainUrlDrawerProps>) {
  const { t, i18n } = useTranslation('common');
  const [urlDetail, setUrlDetail] = useState<DomainUrlDetail | null>(null);
  const [content, setContent] = useState<string | null>(null);
  const [loadingMeta, setLoadingMeta] = useState(false);
  const [loadingContent, setLoadingContent] = useState(false);
  const [recrawling, setRecrawling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!urlId) {
      setUrlDetail(null);
      setContent(null);
      return;
    }

    const fetchData = async () => {
      try {
        setLoadingMeta(true);
        setLoadingContent(true);
        setError(null);

        const [detail, contentResp] = await Promise.allSettled([
          apiService.getDomainUrl(appId, domainId, urlId),
          apiService.getUrlContent(appId, domainId, urlId),
        ]);

        if (detail.status === 'fulfilled') {
          setUrlDetail(detail.value);
        } else {
          setError(t('domainDetailPage.urlDrawer.errors.loadDetail'));
        }

        if (contentResp.status === 'fulfilled') {
          setContent((contentResp.value as any)?.content ?? null);
        }
      } finally {
        setLoadingMeta(false);
        setLoadingContent(false);
      }
    };

    void fetchData();
  }, [appId, domainId, urlId, t]);

  const handleRecrawl = async () => {
    if (!urlId || recrawling) return;
    try {
      setRecrawling(true);
      await apiService.recrawlDomainUrl(appId, domainId, urlId);
      // Re-fetch to show updated next_crawl_at
      const updated = await apiService.getDomainUrl(appId, domainId, urlId);
      setUrlDetail(updated);
    } catch (err: any) {
      setError(err?.message ?? t('domainDetailPage.urls.errors.recrawl'));
    } finally {
      setRecrawling(false);
    }
  };

  if (!urlId) return null;

  return (
    <Modal
      isOpen={urlId !== null}
      onClose={onClose}
      title={t('domainDetailPage.urlDrawer.title')}
      size="xlarge"
    >
      <div className="p-6 overflow-y-auto max-h-[70vh] space-y-6">
        {error && <Alert type="error" message={error} />}

        {loadingMeta ? (
          <LoadingState variant="section" message={t('domainDetailPage.urlDrawer.loading')} />
        ) : urlDetail ? (
          <>
            {/* URL + Status */}
            <div className="flex items-start gap-3">
              <div className="flex-1 min-w-0">
                <a
                  href={urlDetail.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-sm text-bronze  dark:text-bronze-dark inline-block font-mono text-sm break-all"
                >
                  {urlDetail.url}
                  <ExternalLink className="w-3 h-3 flex-shrink-0" />
                </a>
              </div>
              <Badge
                label={t(`domainDetailPage.urls.statuses.${urlDetail.status.toLowerCase()}`, { defaultValue: urlDetail.status })}
                variant={statusBadgeVariant(urlDetail.status as DomainUrlStatus)}
                className={`flex-shrink-0 ${urlDetail.status === 'REMOVED' ? 'line-through opacity-70' : ''}`}
              />
            </div>

            {/* Core metadata */}
            <dl className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <Field label={t('domainDetailPage.urlDrawer.discoveredVia')} value={t(`domainDetailPage.urls.sources.${String(urlDetail.discovered_via).toLowerCase()}`, { defaultValue: urlDetail.discovered_via as DiscoverySource })} />
              <Field label={t('domainDetailPage.urlDrawer.depth')} value={urlDetail.depth} />
              <Field label={t('domainDetailPage.urlDrawer.lastCrawled')} value={formatDate(urlDetail.last_crawled_at, i18n.resolvedLanguage)} />
              <Field label={t('domainDetailPage.urlDrawer.lastIndexed')} value={formatDate(urlDetail.last_indexed_at, i18n.resolvedLanguage)} />
              <Field label={t('domainDetailPage.urlDrawer.nextCrawl')} value={
                <span title={urlDetail.consecutive_skips > 1 ? t('domainDetailPage.urlDrawer.backoffTooltip', { count: urlDetail.consecutive_skips }) : undefined}>
                  {formatDate(urlDetail.next_crawl_at, i18n.resolvedLanguage)}
                  {urlDetail.consecutive_skips > 1 && (
                    <span className="ml-1 text-orange-500 text-xs">{t('domainDetailPage.urlDrawer.backoffShort', { count: urlDetail.consecutive_skips })}</span>
                  )}
                </span>
              } />
              <Field label={t('domainDetailPage.urlDrawer.failureCount')} value={
                urlDetail.failure_count > 0
                  ? <span className="text-error font-medium">{urlDetail.failure_count}</span>
                  : urlDetail.failure_count
              } />
            </dl>

            {/* Last error */}
            {urlDetail.last_error && (
              <Alert type="error" title={t('domainDetailPage.urlDrawer.lastError')} message={urlDetail.last_error} />
            )}

            {/* HTTP cache hints */}
            <div>
              <p className="text-xs font-medium text-fg dark:text-fg-dark uppercase tracking-wide mb-2">{t('domainDetailPage.urlDrawer.httpCacheHints')}</p>
              <dl className="grid grid-cols-2 md:grid-cols-3 gap-4">
                <Field label="ETag" value={urlDetail.http_etag ?? '—'} />
                <Field label="Last-Modified" value={urlDetail.http_last_modified ?? '—'} />
                <Field label={t('domainDetailPage.urlDrawer.sitemapLastmod')} value={formatDate(urlDetail.sitemap_lastmod, i18n.resolvedLanguage)} />
              </dl>
            </div>

            {/* Actions */}
            {canEdit && (
              <div>
                <ButtonApp
                  label={recrawling ? t('domainDetailPage.urlDrawer.marking') : t('domainDetailPage.urls.actions.forceRecrawl')}
                  onClick={() => { void handleRecrawl(); }}
                  loading={recrawling}
                  size="small"
                  icon={<RefreshCw className="w-4 h-4" />}
                />
              </div>
            )}
          </>
        ) : null}

        {/* Content preview */}
        <div>
          <p className="text-xs font-medium text-fg dark:text-fg-dark uppercase tracking-wide mb-2">{t('domainDetailPage.urlDrawer.contentPreview')}</p>
          {loadingContent ? (
            <div className="flex items-center gap-2 text-sm text-fg-secondary dark:text-fg-secondary-dark">
              <Spinner size="sm" tone="muted" />
              {t('domainDetailPage.urlDrawer.loadingContent')}
            </div>
          ) : content ? (
            <pre className="text-xs text-fg dark:text-fg-dark bg-bg dark:bg-bg-dark border border-border dark:border-border-dark rounded p-3 whitespace-pre-wrap max-h-64 overflow-y-auto">
              {content}
            </pre>
          ) : (
            <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark italic">{t('domainDetailPage.urlDrawer.noContent')}</p>
          )}
        </div>
      </div>
    </Modal>
  );
}
