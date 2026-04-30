import { useState, useEffect } from 'react';
import { Loader2, Save } from 'lucide-react';
import { apiService } from '../../services/api';
import { TagInput } from '../ui/TagInput';
import ReadOnlyBanner from '../ui/ReadOnlyBanner';
import Alert from '../ui/Alert';
import { AppRole } from '../../types/roles';
import type { CrawlPolicy, CrawlPolicyInput } from '../../types/crawl';

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
      <div className="flex justify-center items-center py-12">
        <Loader2 className="w-6 h-6 animate-spin text-blue-600" />
        <span className="ml-2 text-gray-600">Loading crawl policy...</span>
      </div>
    );
  }

  return (
    <form onSubmit={e => { void handleSubmit(e); }} className="space-y-6">
      {error && <Alert type="error" message={error} onDismiss={() => setError(null)} />}
      {successMessage && <Alert type="success" message={successMessage} onDismiss={() => setSuccessMessage(null)} />}

      {!canEdit && <ReadOnlyBanner userRole={AppRole.VIEWER} minRole={AppRole.EDITOR} />}

      {/* ==================== DISCOVERY ==================== */}
      <details open className="border border-gray-200 rounded-lg overflow-hidden">
        <summary className="px-4 py-3 bg-gray-50 cursor-pointer font-medium text-gray-800 select-none">
          Discovery
        </summary>
        <div className="p-4 space-y-4">
          {/* Sitemap URL */}
          <div>
            <label htmlFor="sitemap_url" className="block text-sm font-medium text-gray-700 mb-1">
              Sitemap URL
            </label>
            <input
              id="sitemap_url"
              type="url"
              value={formData.sitemap_url ?? ''}
              onChange={e => setField('sitemap_url', e.target.value || null)}
              disabled={!canEdit}
              placeholder="https://example.com/sitemap.xml"
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100"
            />
            <p className="mt-1 text-xs text-gray-500">Leave empty to skip sitemap discovery.</p>
          </div>

          {/* Seed URL + max depth */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label htmlFor="seed_url" className="block text-sm font-medium text-gray-700 mb-1">
                Seed URL
              </label>
              <input
                id="seed_url"
                type="url"
                value={formData.seed_url ?? ''}
                onChange={e => setField('seed_url', e.target.value || null)}
                disabled={!canEdit}
                placeholder="https://example.com/"
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100"
              />
              <p className="mt-1 text-xs text-gray-500">Starting URL for link-following crawl.</p>
            </div>
            <div>
              <label htmlFor="max_depth" className="block text-sm font-medium text-gray-700 mb-1">
                Max depth
              </label>
              <input
                id="max_depth"
                type="number"
                min={0}
                max={5}
                value={formData.max_depth}
                onChange={e => setField('max_depth', Math.max(0, Math.min(5, Number(e.target.value))))}
                disabled={!canEdit}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100"
              />
              <p className="mt-1 text-xs text-gray-500">0–5 link-following levels from the seed URL.</p>
            </div>
          </div>

          {/* Manual URLs */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Manual URLs
            </label>
            <TagInput
              tags={formData.manual_urls}
              onChange={tags => setField('manual_urls', tags)}
              maxTags={200}
              placeholder="https://example.com/page — press Enter"
            />
            <p className="mt-1 text-xs text-gray-500">
              Individual URLs to always include. Duplicates are silently ignored.
            </p>
          </div>
        </div>
      </details>

      {/* ==================== FILTERS ==================== */}
      <details open className="border border-gray-200 rounded-lg overflow-hidden">
        <summary className="px-4 py-3 bg-gray-50 cursor-pointer font-medium text-gray-800 select-none">
          Filters
        </summary>
        <div className="p-4 space-y-4">
          <p className="text-xs text-gray-500">
            Patterns match against the URL path. Use <code className="bg-gray-100 px-1 rounded">**</code> to match
            any number of path segments (e.g. <code className="bg-gray-100 px-1 rounded">/docs/**</code>).
          </p>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Include globs</label>
            <TagInput
              tags={formData.include_globs}
              onChange={tags => setField('include_globs', tags)}
              maxTags={50}
              placeholder="/docs/** — press Enter"
            />
            <p className="mt-1 text-xs text-gray-500">Only crawl URLs that match at least one of these patterns. Leave empty to crawl everything.</p>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Exclude globs</label>
            <TagInput
              tags={formData.exclude_globs}
              onChange={tags => setField('exclude_globs', tags)}
              maxTags={50}
              placeholder="/admin/** — press Enter"
            />
            <p className="mt-1 text-xs text-gray-500">Skip URLs that match any of these patterns.</p>
          </div>
        </div>
      </details>

      {/* ==================== CRAWL BEHAVIOUR ==================== */}
      <details open className="border border-gray-200 rounded-lg overflow-hidden">
        <summary className="px-4 py-3 bg-gray-50 cursor-pointer font-medium text-gray-800 select-none">
          Crawl behaviour
        </summary>
        <div className="p-4 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label htmlFor="rate_limit_rps" className="block text-sm font-medium text-gray-700 mb-1">
                Rate limit (requests/second)
              </label>
              <input
                id="rate_limit_rps"
                type="number"
                min={0.1}
                max={10}
                step={0.1}
                value={formData.rate_limit_rps}
                onChange={e => setField('rate_limit_rps', parseFloat(e.target.value))}
                disabled={!canEdit}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100"
              />
              <p className="mt-1 text-xs text-gray-500">0.1–10 requests per second.</p>
            </div>
            <div>
              <label htmlFor="refresh_interval_hours" className="block text-sm font-medium text-gray-700 mb-1">
                Refresh interval (hours)
              </label>
              <input
                id="refresh_interval_hours"
                type="number"
                min={0}
                max={720}
                value={formData.refresh_interval_hours}
                onChange={e => setField('refresh_interval_hours', Number(e.target.value))}
                disabled={!canEdit}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100"
              />
              <p className="mt-1 text-xs text-gray-500">0 = disabled (never auto-crawl).</p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={formData.respect_robots_txt}
                onChange={e => setField('respect_robots_txt', e.target.checked)}
                disabled={!canEdit}
                className="h-4 w-4 text-blue-600 border-gray-300 rounded disabled:opacity-60"
              />
              <span className="text-sm font-medium text-gray-700">Respect robots.txt</span>
            </label>
          </div>

          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={formData.is_active}
                onChange={e => setField('is_active', e.target.checked)}
                disabled={!canEdit}
                className="h-4 w-4 text-blue-600 border-gray-300 rounded disabled:opacity-60"
              />
              <span className="text-sm font-medium text-gray-700">Enable scheduled crawls</span>
            </label>
          </div>
        </div>
      </details>

      {canEdit && (
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={saving}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white px-5 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            {saving ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            {saving ? 'Saving...' : 'Save policy'}
          </button>
        </div>
      )}
    </form>
  );
}
