import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Save } from 'lucide-react';
import { apiService } from '../../services/api';
import { TagInput } from '../ui/TagInput';
import ReadOnlyBanner from '../ui/ReadOnlyBanner';
import Alert from '../ui/Alert';
import { AppRole } from '../../types/roles';
import type { CrawlPolicy, CrawlPolicyInput } from '../../types/crawl';
import { ButtonApp } from '../ui/ButtonApp';
import { LoadingState } from '../ui/LoadingState';
import ExpansionDetails from '../ui/ExpansionDetails';
import { FormCheckbox, FormField } from '../ui/FormField';

interface CrawlPolicyFormProps {
  appId: number;
  domainId: number;
  canEdit: boolean;
  onSaved?: (policy: CrawlPolicy) => void;
}

const DEFAULT_POLICY: CrawlPolicyInput = {
  seed_url: null,
  sitemap_url: null,
  manual_urls: [],
  max_depth: 2,
  include_globs: [],
  exclude_globs: [],
  rate_limit_rps: 1.0,
  refresh_interval_hours: 168,
  respect_robots_txt: true,
  is_active: false,
};

export default function CrawlPolicyForm({ appId, domainId, canEdit, onSaved }: Readonly<CrawlPolicyFormProps>) {
  const { t } = useTranslation('common');
  const [formData, setFormData] = useState<CrawlPolicyInput>(DEFAULT_POLICY);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    const fetchPolicy = async () => {
      try {
        setLoading(true);
        setError(null);
        const policy = await apiService.getCrawlPolicy(appId, domainId);
        setFormData({
          seed_url: policy.seed_url,
          sitemap_url: policy.sitemap_url,
          manual_urls: policy.manual_urls ?? [],
          max_depth: policy.max_depth,
          include_globs: policy.include_globs ?? [],
          exclude_globs: policy.exclude_globs ?? [],
          rate_limit_rps: policy.rate_limit_rps,
          refresh_interval_hours: policy.refresh_interval_hours,
          respect_robots_txt: policy.respect_robots_txt,
          is_active: policy.is_active,
        });
      } catch (err: any) {
        // 404 means no policy yet — use defaults silently
        if (!String(err?.message ?? '').includes('404')) {
          setError(t('domainDetailPage.policyForm.errors.load'));
        }
      } finally {
        setLoading(false);
      }
    };
    void fetchPolicy();
  }, [appId, domainId, t]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canEdit) return;
    try {
      setSaving(true);
      setError(null);
      const saved = await apiService.updateCrawlPolicy(appId, domainId, formData);
      setSuccessMessage(t('domainDetailPage.policyForm.saved'));
      setTimeout(() => setSuccessMessage(null), 3000);
      onSaved?.(saved);
    } catch (err: any) {
      setError(err?.message ?? t('domainDetailPage.policyForm.errors.save'));
    } finally {
      setSaving(false);
    }
  };

  const setField = <K extends keyof CrawlPolicyInput>(key: K, value: CrawlPolicyInput[K]) => {
    setFormData(prev => ({ ...prev, [key]: value }));
  };

  if (loading) {
    return (
      <LoadingState variant="section" message={t('domainDetailPage.policyForm.loading')} />
    );
  }

  return (
    <form onSubmit={e => { void handleSubmit(e); }} className="space-y-6">
      {error && <Alert type="error" message={error} onDismiss={() => setError(null)} />}
      {successMessage && <Alert type="success" message={successMessage} onDismiss={() => setSuccessMessage(null)} />}

      {!canEdit && <ReadOnlyBanner userRole={AppRole.VIEWER} minRole={AppRole.EDITOR} />}

      {/* ==================== DISCOVERY ==================== */}
      <ExpansionDetails header={t('domainDetailPage.policyForm.discovery')}>
          {/* Sitemap URL */}
          <FormField
            id="sitemap_url"
            label={t('domainDetailPage.policyForm.sitemapUrl')}
            type="url"
            value={formData.sitemap_url ?? ''}
            onChange={e => setField('sitemap_url', e.target.value || null)}
            disabled={!canEdit}
            placeholder="https://example.com/sitemap.xml"
            helpText={t('domainDetailPage.policyForm.sitemapHelp')}
          />

          {/* Seed URL + max depth */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <FormField
              id="seed_url"
              label={t('domainDetailPage.policyForm.seedUrl')}
              type="url"
              value={formData.seed_url ?? ''}
              onChange={e => setField('seed_url', e.target.value || null)}
              disabled={!canEdit}
              placeholder="https://example.com/"
              helpText={t('domainDetailPage.policyForm.seedHelp')}
            />
            <FormField
              id="max_depth"
              label={t('domainDetailPage.policyForm.maxDepth')}
              type="number"
              min={0}
              max={5}
              value={formData.max_depth}
              onChange={e => setField('max_depth', Math.max(0, Math.min(5, Number(e.target.value))))}
              disabled={!canEdit}
              helpText={t('domainDetailPage.policyForm.maxDepthHelp')}
            />
          </div>

          {/* Manual URLs */}
          <div>
            <label className="block text-sm font-medium text-fg dark:text-fg-dark mb-1">
              {t('domainDetailPage.policyForm.manualUrls')}
            </label>
            <TagInput
              tags={formData.manual_urls}
              onChange={tags => setField('manual_urls', tags)}
              maxTags={200}
              placeholder={t('domainDetailPage.policyForm.manualUrlsPlaceholder')}
            />
            <p className="mt-1 text-xs text-fg-secondary dark:text-fg-secondary-dark">
              {t('domainDetailPage.policyForm.manualUrlsHelp')}
            </p>
          </div>
      </ExpansionDetails>

      {/* ==================== FILTERS ==================== */}
      <ExpansionDetails header={t('domainDetailPage.policyForm.filters')}>
          <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
        {t('domainDetailPage.policyForm.filterPatternsBefore')} <code className="bg-tableCab dark:bg-tableCab-dark px-1 rounded">**</code>{t('domainDetailPage.policyForm.filterPatternsAfter')} <code className="bg-tableCab dark:bg-tableCab-dark px-1 rounded">/docs/**</code>).
          </p>
          <div>
            <label className="block text-sm font-medium text-fg dark:text-fg-dark mb-1">{t('domainDetailPage.policyForm.includeGlobs')}</label>
            <TagInput
              tags={formData.include_globs}
              onChange={tags => setField('include_globs', tags)}
              maxTags={50}
              placeholder={t('domainDetailPage.policyForm.includeGlobsPlaceholder')}
            />
            <p className="mt-1 text-xs text-fg-secondary dark:text-fg-secondary-dark">{t('domainDetailPage.policyForm.includeGlobsHelp')}</p>
          </div>
          <div>
            <label className="block text-sm font-medium text-fg dark:text-fg-dark mb-1">{t('domainDetailPage.policyForm.excludeGlobs')}</label>
            <TagInput
              tags={formData.exclude_globs}
              onChange={tags => setField('exclude_globs', tags)}
              maxTags={50}
              placeholder={t('domainDetailPage.policyForm.excludeGlobsPlaceholder')}
            />
            <p className="mt-1 text-xs text-fg-secondary dark:text-fg-secondary-dark">{t('domainDetailPage.policyForm.excludeGlobsHelp')}</p>
          </div>
      </ExpansionDetails>

      {/* ==================== CRAWL BEHAVIOUR ==================== */}
      <ExpansionDetails header={t('domainDetailPage.policyForm.crawlBehaviour')}>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <FormField
              id="rate_limit_rps"
              label={t('domainDetailPage.policyForm.rateLimit')}
              type="number"
              min={0.1}
              max={10}
              step={0.1}
              value={formData.rate_limit_rps}
              onChange={e => setField('rate_limit_rps', parseFloat(e.target.value))}
              disabled={!canEdit}
              helpText={t('domainDetailPage.policyForm.rateLimitHelp')}
            />
            <FormField
              id="refresh_interval_hours"
              label={t('domainDetailPage.policyForm.refreshInterval')}
              type="number"
              min={0}
              max={720}
              value={formData.refresh_interval_hours}
              onChange={e => setField('refresh_interval_hours', Number(e.target.value))}
              disabled={!canEdit}
              helpText={t('domainDetailPage.policyForm.refreshIntervalHelp')}
            />
          </div>

          <FormCheckbox
            id="respect_robots_txt"
            label={t('domainDetailPage.policyForm.respectRobots')}
            checked={formData.respect_robots_txt}
            onChange={e => setField('respect_robots_txt', e.target.checked)}
            disabled={!canEdit}
          />

          <FormCheckbox
            id="is_active"
            label={t('domainDetailPage.policyForm.enableScheduled')}
            checked={formData.is_active}
            onChange={e => setField('is_active', e.target.checked)}
            disabled={!canEdit}
          />
      </ExpansionDetails>

      {canEdit && (
        <div className="flex justify-end">
          <ButtonApp
            type="submit"
            label={saving ? t('domainDetailPage.policyForm.saving') : t('domainDetailPage.policyForm.save')}
            loading={saving}
            icon={<Save className="w-4 h-4" />}
          />
        </div>
      )}
    </form>
  );
}
