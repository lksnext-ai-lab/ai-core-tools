import { useState, useEffect } from 'react';
import { Code2, KeyRound, Check } from 'lucide-react';
import { apiService } from '../../services/api';

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
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      {/* Header with API key picker */}
      <div className="flex items-center justify-between px-4 py-3 bg-gray-50 border-b border-gray-200">
        <div className="flex items-center gap-2 text-sm font-medium text-gray-700">
          <Code2 className="w-4 h-4" />
          {siloName ? `${siloName} — ` : ''}Public API Snippet —{' '}
          <span className="font-mono text-xs text-gray-500">{endpoint}</span>
        </div>
        <div className="flex items-center gap-2">
          <KeyRound className="w-4 h-4 text-gray-400" />
          <select
            value={selectedKeyId ?? ''}
            onChange={(e) => setSelectedKeyId(Number(e.target.value) || null)}
            className="border border-gray-300 rounded px-2 py-1 text-xs text-gray-700 bg-white"
            disabled={loadingKeys || apiKeys.length === 0}
          >
            <option value="">
              {loadingKeys ? 'Loading keys…' : ''}
              {!loadingKeys && apiKeys.length === 0 ? 'No API keys' : ''}
              {!loadingKeys && apiKeys.length > 0 ? '— select key —' : ''}
            </option>
            {apiKeys.map((k) => (
              <option key={k.key_id} value={k.key_id}>
                {k.name} ({k.key_preview})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-200 bg-white">
        {(['curl', 'python', 'js', 'ts'] as const).map((tab) => {
          const tabLabels: Record<string, string> = {
            curl: 'cURL',
            python: 'Python',
            js: 'JavaScript',
            ts: 'TypeScript',
          };
          return (
            <button
              key={tab}
              type="button"
              onClick={() => setSelectedTab(tab)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                selectedTab === tab
                  ? 'border-amber-500 text-amber-700'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {tabLabels[tab]}
            </button>
          );
        })}
      </div>

      {/* Code block */}
      <div className="relative">
        <pre className="text-xs p-4 overflow-x-auto leading-relaxed max-h-72 bg-gray-900 text-green-300">
          {snippets[selectedTab]}
        </pre>
        <button
          type="button"
          onClick={() => handleCopy(selectedTab)}
          className="absolute top-2 right-2 px-2 py-1 text-xs bg-gray-700 hover:bg-gray-600 text-gray-200 rounded flex items-center gap-1"
        >
          {copied === selectedTab ? (
            <>
              <Check className="w-3 h-3" /> Copied
            </>
          ) : (
            'Copy'
          )}
        </button>
      </div>
    </div>
  );
}

export default SiloAPISnippets;
