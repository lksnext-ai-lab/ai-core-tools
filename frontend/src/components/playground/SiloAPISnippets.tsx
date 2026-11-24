import { useState, useEffect } from 'react';
import { KeyRound, Check } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { apiService } from '../../services/api';
import SegmentedTabs from '../ui/SegmentedTabs';
import { FormSelect } from '../ui/FormField';

interface SiloAPISnippetsProps {
  appId: string | number;
  siloId: string | number;
  siloName?: string;
  query?: string;
  limit?: number;
  filterMetadata?: Record<string, unknown>;
  searchType?: string;
  scoreThreshold?: number;
  fetchK?: number;
  lambdaMult?: number;
}

interface APIKeyItem {
  key_id: number;
  name: string;
  key_preview: string;
}

const languageTabs = [
  { id: 'curl', label: 'cURL' },
  { id: 'python', label: 'Python' },
  { id: 'js', label: 'JavaScript' },
  { id: 'ts', label: 'TypeScript' },
] as const;

function SiloAPISnippets({
  appId,
  siloId,
  siloName,
  query,
  limit,
  filterMetadata,
  searchType,
  scoreThreshold,
  fetchK,
  lambdaMult,
}: Readonly<SiloAPISnippetsProps>) {
  const { t } = useTranslation('common');
  const [selectedTab, setSelectedTab] = useState<'curl' | 'python' | 'js' | 'ts'>('curl');
  const [copied, setCopied] = useState<string | null>(null);
  const [apiKeys, setApiKeys] = useState<APIKeyItem[]>([]);
  const [selectedKeyId, setSelectedKeyId] = useState<number | null>(null);
  const [loadingKeys, setLoadingKeys] = useState(false);

  useEffect(() => {
    if (!appId) return;
    setLoadingKeys(true);
    apiService
      .getAPIKeys(Number(appId))
      .then((data) => {
        const keys = data as APIKeyItem[];
        setApiKeys(keys);
        if (keys.length > 0) {
          setSelectedKeyId(keys[0].key_id);
        }
      })
      .catch(() => {
        setApiKeys([]);
      })
      .finally(() => {
        setLoadingKeys(false);
      });
  }, [appId]);

  const baseUrl = globalThis.location.origin;
  const endpoint = `${baseUrl}/public/v1/app/${appId}/silos/${siloId}/search`;

  function buildBody() {
    const body: Record<string, unknown> = {
      query: query ?? '',
      limit: limit ?? 10,
    };
    if (filterMetadata && Object.keys(filterMetadata).length > 0) {
      body.filter_metadata = filterMetadata;
    }
    if (searchType && searchType !== 'similarity') {
      body.search_type = searchType;
    }
    if (searchType === 'similarity_score_threshold' && scoreThreshold !== undefined) {
      body.score_threshold = scoreThreshold;
    }
    if (searchType === 'mmr') {
      if (fetchK !== undefined) body.fetch_k = fetchK;
      if (lambdaMult !== undefined) body.lambda_mult = lambdaMult;
    }
    return body;
  }

  const selectedKey = apiKeys.find((k) => k.key_id === selectedKeyId);
  const apiKeyPlaceholder = selectedKey ? selectedKey.key_preview : 'YOUR_API_KEY';

  const body = buildBody();
  const bodyJson = JSON.stringify(body, null, 2);

  const snippets = {
    curl: `curl -X POST "${endpoint}" \\
  -H "X-API-KEY: ${apiKeyPlaceholder}" \\
  -H "Content-Type: application/json" \\
  -d '${bodyJson}'`,

    python: `import requests\n\nurl = "${endpoint}"\nheaders = {\n    "X-API-KEY": "${apiKeyPlaceholder}",\n    "Content-Type": "application/json",\n}\npayload = ${bodyJson}\n\nresponse = requests.post(url, headers=headers, json=payload)\ndata = response.json()\n\nfor result in data.get("results", []):\n    print(f"Score: {result['score']:.3f} — {result['page_content'][:120]}")`,

    js: `const response = await fetch("${endpoint}", {\n  method: "POST",\n  headers: {\n    "X-API-KEY": "${apiKeyPlaceholder}",\n    "Content-Type": "application/json",\n  },\n  body: JSON.stringify(${bodyJson}),\n});\nconst data = await response.json();\ndata.results.forEach(r => console.log(r.score, r.page_content.slice(0, 120)));`,

    ts: `interface SiloSearchResult {\n  page_content: string;\n  metadata: Record<string, unknown>;\n  score: number;\n}\ninterface SiloSearchResponse {\n  results: SiloSearchResult[];\n  total: number;\n}\n\nconst response = await fetch("${endpoint}", {\n  method: "POST",\n  headers: {\n    "X-API-KEY": "${apiKeyPlaceholder}",\n    "Content-Type": "application/json",\n  },\n  body: JSON.stringify(${bodyJson}),\n});\nconst data: SiloSearchResponse = await response.json();\ndata.results.forEach(r => console.log(r.score, r.page_content.slice(0, 120)));`,
  };

  function handleCopy(tab: string) {
    void navigator.clipboard.writeText(snippets[tab as keyof typeof snippets]);
    setCopied(tab);
    setTimeout(() => setCopied(null), 2000);
  }

  return (
    <div className="space-y-3">
      {/* Language pills + API key picker */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SegmentedTabs
          tabs={languageTabs}
          activeTab={selectedTab}
          onChange={setSelectedTab}
          ariaLabel={t('siloApiSnippets.language')}
          className="max-w-[360px]"
        />
        <div className="flex items-center gap-2">
          <KeyRound className="h-4 w-4 text-fg-tertiary dark:text-fg-tertiary-dark" aria-hidden="true" />
          <FormSelect
            label={t('siloApiSnippets.apiKey')}
            id="silo-api-key-select"
            value={selectedKeyId ?? ''}
            onChange={(e) => setSelectedKeyId(Number(e.target.value) || null)}
            disabled={loadingKeys || apiKeys.length === 0}
            className="relative min-w-[180px]"
            labelClassName="sr-only"
            options={[
              {
                value: '',
                label: loadingKeys
                  ? t('siloApiSnippets.loadingKeys')
                  : apiKeys.length === 0
                    ? t('siloApiSnippets.noApiKeys')
                    : t('siloApiSnippets.selectKey'),
              },
              ...apiKeys.map((key) => ({
                value: key.key_id,
                label: `${key.name} (${key.key_preview})`,
              })),
            ]}
          />
        </div>
      </div>

      {/* Code block (dark in both themes) */}
      <div className="overflow-hidden rounded-lg border border-[#33302a] bg-[#1c1b18] text-[#f2efe9]">
        <div className="flex items-center justify-between gap-2.5 border-b border-[#33302a] py-2 pl-3.5 pr-2.5 text-[11.5px] text-[#b9b3a4]">
          <span className="min-w-0 truncate font-mono" title={siloName ? `${siloName} — ${t('siloApiSnippets.publicApi')}` : undefined}>
            POST {endpoint}
          </span>
          <button
            type="button"
            onClick={() => handleCopy(selectedTab)}
            className="flex shrink-0 items-center gap-1 rounded-md border border-[#5a564b] px-[11px] py-[5px] text-xs text-[#f2efe9] hover:bg-[#2c2a24]"
          >
            {copied === selectedTab ? (
              <>
                <Check className="h-3 w-3" aria-hidden="true" /> {t('siloApiSnippets.copied')}
              </>
            ) : (
              t('siloApiSnippets.copy')
            )}
          </button>
        </div>
        <pre className="m-0 max-h-72 overflow-auto whitespace-pre-wrap break-all px-3.5 py-3 font-mono text-[13px] leading-relaxed">
          {snippets[selectedTab]}
        </pre>
      </div>
    </div>
  );
}

export default SiloAPISnippets;
