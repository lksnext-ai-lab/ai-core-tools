import { useState, useEffect } from 'react';
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
          setError('Failed to load crawl policy');
        }
      } finally {
        setLoading(false);
      }
    };
    void fetchPolicy();
  }, [appId, domainId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canEdit) return;
    try {
      setSaving(true);
      setError(null);
      const saved = await apiService.updateCrawlPolicy(appId, domainId, formData);
      setSuccessMessage('Crawl policy saved successfully');
      setTimeout(() => setSuccessMessage(null), 3000);
      onSaved?.(saved);
    } catch (err: any) {
      setError(err?.message ?? 'Failed to save crawl policy');
    } finally {
      setSaving(false);
    }
  };

  const setField = <K extends keyof CrawlPolicyInput>(key: K, value: CrawlPolicyInput[K]) => {
    setFormData(prev => ({ ...prev, [key]: value }));
  };

  if (loading) {
    return (
      <LoadingState variant="section" message="Loading crawl policy..." />
    );
  }

  return (
    <form onSubmit={e => { void handleSubmit(e); }} className="space-y-6">
      {error && <Alert type="error" message={error} onDismiss={() => setError(null)} />}
      {successMessage && <Alert type="success" message={successMessage} onDismiss={() => setSuccessMessage(null)} />}

      {!canEdit && <ReadOnlyBanner userRole={AppRole.VIEWER} minRole={AppRole.EDITOR} />}

      {/* ==================== DISCOVERY ==================== */}
      <ExpansionDetails header="Discovery">
          {/* Sitemap URL */}
          <FormField
            id="sitemap_url"
            label="Sitemap URL"
            type="url"
            value={formData.sitemap_url ?? ''}
            onChange={e => setField('sitemap_url', e.target.value || null)}
            disabled={!canEdit}
            placeholder="https://example.com/sitemap.xml"
            helpText="Leave empty to skip sitemap discovery."
          />

          {/* Seed URL + max depth */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <FormField
              id="seed_url"
              label="Seed URL"
              type="url"
              value={formData.seed_url ?? ''}
              onChange={e => setField('seed_url', e.target.value || null)}
              disabled={!canEdit}
              placeholder="https://example.com/"
              helpText="Starting URL for link-following crawl."
            />
            <FormField
              id="max_depth"
              label="Max depth"
              type="number"
              min={0}
              max={5}
              value={formData.max_depth}
              onChange={e => setField('max_depth', Math.max(0, Math.min(5, Number(e.target.value))))}
              disabled={!canEdit}
              helpText="0–5 link-following levels from the seed URL."
            />
          </div>

          {/* Manual URLs */}
          <div>
            <label className="block text-sm font-medium text-fg dark:text-fg-dark mb-1">
              Manual URLs
            </label>
            <TagInput
              tags={formData.manual_urls}
              onChange={tags => setField('manual_urls', tags)}
              maxTags={200}
              placeholder="https://example.com/page — press Enter"
            />
            <p className="mt-1 text-xs text-fg-secondary dark:text-fg-secondary-dark">
              Individual URLs to always include. Duplicates are silently ignored.
            </p>
          </div>
      </ExpansionDetails>

      {/* ==================== FILTERS ==================== */}
      <ExpansionDetails header="Filters">
          <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark">
            Patterns match against the URL path. Use <code className="bg-tableCab dark:bg-tableCab-dark px-1 rounded">**</code> to match
            any number of path segments (e.g. <code className="bg-tableCab dark:bg-tableCab-dark px-1 rounded">/docs/**</code>).
          </p>
          <div>
            <label className="block text-sm font-medium text-fg dark:text-fg-dark mb-1">Include globs</label>
            <TagInput
              tags={formData.include_globs}
              onChange={tags => setField('include_globs', tags)}
              maxTags={50}
              placeholder="/docs/** — press Enter"
            />
            <p className="mt-1 text-xs text-fg-secondary dark:text-fg-secondary-dark">Only crawl URLs that match at least one of these patterns. Leave empty to crawl everything.</p>
          </div>
          <div>
            <label className="block text-sm font-medium text-fg dark:text-fg-dark mb-1">Exclude globs</label>
            <TagInput
              tags={formData.exclude_globs}
              onChange={tags => setField('exclude_globs', tags)}
              maxTags={50}
              placeholder="/admin/** — press Enter"
            />
            <p className="mt-1 text-xs text-fg-secondary dark:text-fg-secondary-dark">Skip URLs that match any of these patterns.</p>
          </div>
      </ExpansionDetails>

      {/* ==================== CRAWL BEHAVIOUR ==================== */}
      <ExpansionDetails header="Crawl behaviour">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <FormField
              id="rate_limit_rps"
              label="Rate limit (requests/second)"
              type="number"
              min={0.1}
              max={10}
              step={0.1}
              value={formData.rate_limit_rps}
              onChange={e => setField('rate_limit_rps', parseFloat(e.target.value))}
              disabled={!canEdit}
              helpText="0.1–10 requests per second."
            />
            <FormField
              id="refresh_interval_hours"
              label="Refresh interval (hours)"
              type="number"
              min={0}
              max={720}
              value={formData.refresh_interval_hours}
              onChange={e => setField('refresh_interval_hours', Number(e.target.value))}
              disabled={!canEdit}
              helpText="0 = disabled (never auto-crawl)."
            />
          </div>

          <FormCheckbox
            id="respect_robots_txt"
            label="Respect robots.txt"
            checked={formData.respect_robots_txt}
            onChange={e => setField('respect_robots_txt', e.target.checked)}
            disabled={!canEdit}
          />

          <FormCheckbox
            id="is_active"
            label="Enable scheduled crawls"
            checked={formData.is_active}
            onChange={e => setField('is_active', e.target.checked)}
            disabled={!canEdit}
          />
      </ExpansionDetails>

      {canEdit && (
        <div className="flex justify-end">
          <ButtonApp
            type="submit"
            label={saving ? 'Saving...' : 'Save policy'}
            loading={saving}
            icon={<Save className="w-4 h-4" />}
          />
        </div>
      )}
    </form>
  );
}
